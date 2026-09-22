#!/usr/bin/env python3
"""Simple Chinese GUI for converting CAJ files to PDF."""

from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass, field
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango

from app.engine import (
    KIND_LABELS,
    ConvertResult,
    collect_files,
    collect_pdfs,
    convert_file,
    ocr_image_pdf,
)
from app.scan import tesseract_install_message, tesseract_languages

APP_ID = "io.github.caj2pdf.easy"
APP_TITLE = "CAJ 转 PDF"


@dataclass
class Job:
    path: Path
    task: str = "convert"
    status: str = "等待转换"
    ok: bool | None = None
    message: str = ""
    output: Path | None = None
    format_name: str = ""
    kind: str = ""
    detail: str = ""
    skipped: bool = False
    row: Gtk.ListBoxRow | None = field(default=None, repr=False)


class CajWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application, initial_files: list[Path], auto_start: bool) -> None:
        super().__init__(application=app, title=APP_TITLE)
        self.set_default_size(760, 640)
        self.jobs: list[Job] = []
        self.busy = False
        self._active_task = "convert"
        self._auto_start = auto_start
        self._build_ui()
        if initial_files:
            self.add_paths(initial_files)
            if auto_start:
                if any(job.task == "convert" for job in self.jobs):
                    GLib.idle_add(self.start_convert)
                elif any(job.task == "ocr" for job in self.jobs):
                    GLib.idle_add(self.start_ocr)

    def _build_ui(self) -> None:
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Gtk.Label(label=APP_TITLE))
        toolbar.add_top_bar(header)
        self.set_content(toolbar)

        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        page.set_margin_top(18)
        page.set_margin_bottom(18)
        page.set_margin_start(20)
        page.set_margin_end(20)

        hint = Gtk.Label(
            label=(
                "把知网下载的 CAJ 拖进来，点「开始转换」。\n"
                "已经是图片版 PDF、没法选中文字时，点「识别图片 PDF」。\n"
                "转换结果在原文件旁边；识别结果另存为「原名-已识别.pdf」，原来的 PDF 不会改。"
            )
        )
        hint.set_wrap(True)
        hint.set_xalign(0)
        hint.add_css_class("dim-label")
        page.append(hint)

        self.drop_zone = Gtk.Frame()
        self.drop_zone.add_css_class("drop-zone")
        drop_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        drop_box.set_margin_top(28)
        drop_box.set_margin_bottom(28)
        drop_box.set_margin_start(16)
        drop_box.set_margin_end(16)
        drop_title = Gtk.Label(label="把 CAJ 或图片版 PDF 拖到这里")
        drop_title.add_css_class("title-3")
        drop_sub = Gtk.Label(label="CAJ 用来转换成 PDF，图片 PDF 用来识别文字")
        drop_sub.add_css_class("dim-label")
        drop_box.append(drop_title)
        drop_box.append(drop_sub)
        self.drop_zone.set_child(drop_box)
        page.append(self.drop_zone)

        drop_target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop_target.connect("drop", self._on_drop)
        drop_target.connect("enter", self._on_drop_enter)
        drop_target.connect("leave", self._on_drop_leave)
        self.drop_zone.add_controller(drop_target)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.btn_files = Gtk.Button(label="选择文件")
        self.btn_files.add_css_class("suggested-action")
        self.btn_files.add_css_class("pill")
        self.btn_files.connect("clicked", self._choose_files)
        self.btn_folder = Gtk.Button(label="选择文件夹")
        self.btn_folder.add_css_class("pill")
        self.btn_folder.connect("clicked", self._choose_folder)
        self.btn_clear = Gtk.Button(label="清空列表")
        self.btn_clear.add_css_class("pill")
        self.btn_clear.connect("clicked", lambda *_: self.clear_jobs())
        buttons.append(self.btn_files)
        buttons.append(self.btn_folder)
        buttons.append(self.btn_clear)
        page.append(buttons)

        list_label = Gtk.Label(label="文件列表")
        list_label.set_xalign(0)
        list_label.add_css_class("heading")
        page.append(list_label)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(220)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.listbox.add_css_class("boxed-list")
        self.empty_row = Gtk.Label(label="还没有文件。请选择 CAJ 转换，或点「识别图片 PDF」。")
        self.empty_row.add_css_class("dim-label")
        self.empty_row.set_margin_top(24)
        self.empty_row.set_margin_bottom(24)
        placeholder = Gtk.ListBoxRow()
        placeholder.set_activatable(False)
        placeholder.set_selectable(False)
        placeholder.set_child(self.empty_row)
        self.placeholder_row = placeholder
        self.listbox.append(placeholder)
        scrolled.set_child(self.listbox)
        page.append(scrolled)

        self.progress = Gtk.ProgressBar()
        self.progress.set_show_text(True)
        self.progress.set_text("准备就绪")
        page.append(self.progress)

        action = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.btn_convert = Gtk.Button(label="开始转换")
        self.btn_convert.add_css_class("suggested-action")
        self.btn_convert.add_css_class("pill")
        self.btn_convert.set_sensitive(False)
        self.btn_convert.connect("clicked", lambda *_: self.start_convert())
        self.btn_ocr = Gtk.Button(label="识别图片 PDF")
        self.btn_ocr.add_css_class("pill")
        self.btn_ocr.connect("clicked", lambda *_: self.start_ocr())
        self.btn_open = Gtk.Button(label="打开结果所在文件夹")
        self.btn_open.add_css_class("pill")
        self.btn_open.set_sensitive(False)
        self.btn_open.connect("clicked", self._open_results)
        action.append(self.btn_convert)
        action.append(self.btn_ocr)
        action.append(self.btn_open)
        page.append(action)

        self.summary = Gtk.Label(label="")
        self.summary.set_wrap(True)
        self.summary.set_xalign(0)
        page.append(self.summary)

        css = Gtk.CssProvider()
        css.load_from_data(
            b"""
            .drop-zone {
                border: 2px dashed alpha(@accent_color, 0.55);
                border-radius: 18px;
                background: alpha(@accent_bg_color, 0.08);
            }
            .drop-zone.hover {
                border-color: @accent_color;
                background: alpha(@accent_bg_color, 0.18);
            }
            """
        )
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        toolbar.set_content(page)

    def _alert(self, heading: str, body: str) -> None:
        dialog = Adw.AlertDialog(heading=heading, body=body)
        dialog.add_response("ok", "知道了")
        dialog.set_default_response("ok")
        dialog.present(self)

    def _on_drop_enter(self, *_args) -> int:
        self.drop_zone.add_css_class("hover")
        return Gdk.DragAction.COPY

    def _on_drop_leave(self, *_args) -> None:
        self.drop_zone.remove_css_class("hover")

    def _on_drop(self, _target, value, _x, _y) -> bool:
        self.drop_zone.remove_css_class("hover")
        paths: list[Path] = []
        files = value.get_files() if hasattr(value, "get_files") else []
        for gio_file in files:
            loc = gio_file.get_path()
            if loc:
                paths.append(Path(loc))
        self.add_paths(paths)
        return True

    def _caj_filters(self) -> Gio.ListStore:
        store = Gio.ListStore.new(Gtk.FileFilter)
        caj = Gtk.FileFilter()
        caj.set_name("知网文件（CAJ/KDH/NH）")
        for suffix in ("caj", "kdh", "nh", "hn", "c8"):
            caj.add_suffix(suffix)
        store.append(caj)
        all_files = Gtk.FileFilter()
        all_files.set_name("所有文件")
        all_files.add_pattern("*")
        store.append(all_files)
        return store

    def _pdf_filters(self) -> Gio.ListStore:
        store = Gio.ListStore.new(Gtk.FileFilter)
        pdf = Gtk.FileFilter()
        pdf.set_name("PDF 文件")
        pdf.add_suffix("pdf")
        pdf.add_mime_type("application/pdf")
        store.append(pdf)
        all_files = Gtk.FileFilter()
        all_files.set_name("所有文件")
        all_files.add_pattern("*")
        store.append(all_files)
        return store

    def _choose_files(self, *_args) -> None:
        dialog = Gtk.FileDialog(title="选择要转换的 CAJ 文件")
        filters = self._caj_filters()
        dialog.set_filters(filters)
        dialog.set_default_filter(filters.get_item(0))
        dialog.open_multiple(self, None, self._on_files_chosen)

    def _on_files_chosen(self, dialog: Gtk.FileDialog, result) -> None:
        try:
            files = dialog.open_multiple_finish(result)
        except GLib.Error:
            return
        paths = []
        for i in range(files.get_n_items()):
            gio_file = files.get_item(i)
            loc = gio_file.get_path()
            if loc:
                paths.append(Path(loc))
        self.add_paths(paths)

    def _choose_folder(self, *_args) -> None:
        dialog = Gtk.FileDialog(title="选择包含 CAJ 或 PDF 的文件夹")
        dialog.select_folder(self, None, self._on_folder_chosen)

    def _on_folder_chosen(self, dialog: Gtk.FileDialog, result) -> None:
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        loc = folder.get_path()
        if loc:
            self.add_paths([Path(loc)])

    def _choose_ocr_pdfs(self) -> None:
        dialog = Gtk.FileDialog(title="选择要识别的图片版 PDF")
        filters = self._pdf_filters()
        dialog.set_filters(filters)
        dialog.set_default_filter(filters.get_item(0))
        dialog.open_multiple(self, None, self._on_ocr_files_chosen)

    def _on_ocr_files_chosen(self, dialog: Gtk.FileDialog, result) -> None:
        try:
            files = dialog.open_multiple_finish(result)
        except GLib.Error:
            return
        paths = []
        for i in range(files.get_n_items()):
            gio_file = files.get_item(i)
            loc = gio_file.get_path()
            if loc:
                paths.append(Path(loc))
        self.add_paths(paths, start_ocr=True)

    def _add_job(self, path: Path, task: str) -> bool:
        for job in self.jobs:
            if job.path == path:
                if task == "ocr" and job.task == "ocr":
                    job.ok = None
                    job.status = "等待识别"
                    job.message = ""
                    job.output = None
                    job.kind = ""
                    job.detail = ""
                    job.skipped = False
                    return True
                return False
        if task == "ocr":
            self.jobs.append(Job(path=path, task="ocr", status="等待识别", format_name="图片 PDF"))
        else:
            self.jobs.append(Job(path=path, task="convert", status="等待转换"))
        return True

    def add_paths(self, paths: list[Path], start_ocr: bool = False) -> None:
        cajs = collect_files(paths)
        pdfs = collect_pdfs(paths)
        added_caj = 0
        added_pdf = 0
        for path in cajs:
            if self._add_job(path, "convert"):
                added_caj += 1
        for path in pdfs:
            if self._add_job(path, "ocr"):
                added_pdf += 1
        if added_caj or added_pdf:
            self.refresh_list()
        if not cajs and not pdfs:
            self.summary.set_text("没有找到 CAJ 或 PDF 文件。请确认选的是知网下载的论文，或图片版 PDF。")
            return
        bits: list[str] = []
        if added_caj:
            bits.append(f"已加入 {added_caj} 个 CAJ，点「开始转换」。")
        if added_pdf:
            bits.append(f"已加入 {added_pdf} 个 PDF，点「识别图片 PDF」识别文字。")
        if bits:
            self.summary.set_text(" ".join(bits))
        if start_ocr:
            self.start_ocr()

    def clear_jobs(self) -> None:
        if self.busy:
            return
        self.jobs.clear()
        self.btn_open.set_sensitive(False)
        self.summary.set_text("")
        self.progress.set_fraction(0)
        self.progress.set_text("准备就绪")
        self.refresh_list()

    def _pending(self, task: str) -> list[Job]:
        if task == "ocr":
            return [job for job in self.jobs if job.task == "ocr" and job.ok is None]
        return [job for job in self.jobs if job.task == "convert"]

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.btn_files.set_sensitive(not busy)
        self.btn_folder.set_sensitive(not busy)
        self.btn_clear.set_sensitive(not busy)
        self.btn_ocr.set_sensitive(not busy)
        convert_ok = (not busy) and any(job.task == "convert" for job in self.jobs)
        self.btn_convert.set_sensitive(convert_ok)
        if busy:
            self.btn_open.set_sensitive(False)

    def refresh_list(self) -> None:
        while True:
            row = self.listbox.get_row_at_index(0)
            if row is None:
                break
            self.listbox.remove(row)

        if not self.jobs:
            self.listbox.append(self.placeholder_row)
            self.btn_convert.set_sensitive(False)
            return

        for job in self.jobs:
            row = Gtk.ListBoxRow()
            row.set_activatable(False)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.set_margin_top(8)
            box.set_margin_bottom(8)
            box.set_margin_start(12)
            box.set_margin_end(12)
            name = Gtk.Label(label=job.path.name)
            name.set_xalign(0)
            name.set_ellipsize(Pango.EllipsizeMode.END)
            status = job.status
            extras = [x for x in (job.format_name, KIND_LABELS.get(job.kind, "")) if x]
            if extras:
                status = f"{status}  ·  " + "  ·  ".join(extras)
            sub = Gtk.Label(label=status)
            sub.set_xalign(0)
            sub.add_css_class("caption")
            sub.add_css_class("dim-label")
            if job.ok is True:
                sub.add_css_class("success")
            elif job.ok is False:
                sub.add_css_class("error")
            box.append(name)
            box.append(sub)
            if job.message:
                msg = Gtk.Label(label=job.message)
                msg.set_xalign(0)
                msg.set_wrap(True)
                msg.add_css_class("caption")
                box.append(msg)
            row.set_child(box)
            job.row = row
            self.listbox.append(row)

        if not self.busy:
            self.btn_convert.set_sensitive(any(job.task == "convert" for job in self.jobs))

    def start_convert(self) -> None:
        if self.busy:
            return
        jobs = self._pending("convert")
        if not jobs:
            self.summary.set_text("请先选择要转换的 CAJ 文件。图片版 PDF 请点「识别图片 PDF」。")
            return
        self._run_jobs("convert", jobs)
        return False

    def start_ocr(self) -> None:
        if self.busy:
            return
        if not tesseract_languages():
            self._alert("还不能识别文字", tesseract_install_message())
            return
        jobs = self._pending("ocr")
        if not jobs:
            self._choose_ocr_pdfs()
            return
        self._run_jobs("ocr", jobs)

    def _run_jobs(self, task: str, jobs: list[Job]) -> None:
        self._active_task = task
        self._set_busy(True)
        if task == "ocr":
            self.summary.set_text("正在识别文字，请稍等，不要关闭窗口。每一页大约需要几秒钟。")
            for job in jobs:
                job.status = "等待识别"
                job.ok = None
                job.message = ""
                job.output = None
                job.kind = ""
                job.detail = ""
                job.skipped = False
        else:
            self.summary.set_text("正在转换，请稍等，不要关闭窗口。")
            for job in jobs:
                job.status = "等待转换"
                job.ok = None
                job.message = ""
                job.output = None
                job.kind = ""
                job.detail = ""
                job.skipped = False
        self.refresh_list()
        threading.Thread(target=self._worker, args=(task, jobs), daemon=True).start()

    def _worker(self, task: str, jobs: list[Job]) -> None:
        total = len(jobs)
        for index, job in enumerate(jobs, start=1):
            GLib.idle_add(self._mark_running, job, task, index, total)

            def progress(page: int, pages: int, job=job, index=index, total=total) -> None:
                GLib.idle_add(self._mark_page, job, page, pages, index, total)

            try:
                if task == "ocr":
                    result = ocr_image_pdf(job.path, progress=progress)
                else:
                    result = convert_file(job.path, progress=progress)
            except Exception as exc:
                verb = "识别失败" if task == "ocr" else "转换失败"
                result = ConvertResult(
                    source=job.path,
                    output=None,
                    ok=False,
                    format_name="PDF" if task == "ocr" else "",
                    message=f"{verb}：{exc}",
                    detail=traceback.format_exc(),
                )
            GLib.idle_add(self._mark_done, job, task, result, index, total)
        GLib.idle_add(self._finish_all, task, jobs)

    def _mark_running(self, job: Job, task: str, index: int, total: int) -> bool:
        job.status = "正在识别" if task == "ocr" else "正在转换"
        self.progress.set_fraction((index - 1) / total)
        verb = "正在识别" if task == "ocr" else "正在转换"
        self.progress.set_text(f"{verb} {index}/{total}：{job.path.name}")
        self.refresh_list()
        return False

    def _mark_page(self, job: Job, page: int, pages: int, index: int, total: int) -> bool:
        fraction = ((index - 1) + (page / max(pages, 1))) / max(total, 1)
        self.progress.set_fraction(min(1.0, fraction))
        self.progress.set_text(f"正在识别 {page}/{pages} 页：{job.path.name}")
        return False

    def _status_for(self, task: str, result: ConvertResult) -> str:
        if task == "ocr":
            if result.skipped:
                return "无需识别"
            return "识别成功" if result.ok else "识别失败"
        return "转换成功" if result.ok else "转换失败"

    def _mark_done(self, job: Job, task: str, result: ConvertResult, index: int, total: int) -> bool:
        job.ok = result.ok
        job.status = self._status_for(task, result)
        job.message = result.message
        job.output = result.output
        job.format_name = result.format_name
        job.kind = result.kind
        job.detail = result.detail
        job.skipped = result.skipped
        self.progress.set_fraction(index / total)
        self.refresh_list()
        return False

    def _finish_all(self, task: str, jobs: list[Job]) -> bool:
        self._set_busy(False)
        ok_n = sum(1 for job in jobs if job.ok)
        fail_n = sum(1 for job in jobs if job.ok is False)
        skip_n = sum(1 for job in jobs if job.skipped)
        done_n = ok_n - skip_n
        self.btn_open.set_sensitive(any(job.ok and job.output is not None for job in self.jobs))
        if task == "ocr":
            if fail_n == 0 and skip_n == ok_n and ok_n:
                self.progress.set_text("全部完成")
                self.summary.set_text("这些 PDF 已经可以选中文字，不用再识别。")
            elif fail_n == 0:
                self.progress.set_text("全部完成")
                self.summary.set_text(
                    f"已经识别好 {done_n} 个 PDF。"
                    "新文件在原 PDF 旁边，文件名带「已识别」；原来的 PDF 没有改动。"
                )
            elif ok_n == 0:
                self.progress.set_text("识别失败")
                self.summary.set_text("这次没有识别成功。请看列表里的失败原因。")
            else:
                self.progress.set_text("部分完成")
                self.summary.set_text(
                    f"成功 {ok_n} 个，失败 {fail_n} 个。识别后的文件在原 PDF 旁边；失败的请看列表说明。"
                )
        elif fail_n == 0:
            self.progress.set_text("全部完成")
            self.summary.set_text(
                f"已经全部转好，共 {ok_n} 个 PDF。文件就在原来的 CAJ 旁边，用文档阅读器打开即可。"
            )
        elif ok_n == 0:
            self.progress.set_text("转换失败")
            self.summary.set_text(
                "这次没有成功。请看列表里的失败原因。如果方便，把失败文件发给帮你安装的人。"
            )
        else:
            self.progress.set_text("部分完成")
            self.summary.set_text(
                f"成功 {ok_n} 个，失败 {fail_n} 个。成功的 PDF 在原文件旁边；失败的请看列表说明。"
            )
        return False

    def _open_results(self, *_args) -> None:
        for job in self.jobs:
            if job.ok and job.output is not None:
                folder = job.output.parent.as_uri()
                Gio.AppInfo.launch_default_for_uri(folder, None)
                return


class CajApp(Adw.Application):
    def __init__(self, initial_files: list[Path], auto_start: bool) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
        self._initial_files = initial_files
        self._auto_start = auto_start
        self.connect("activate", self._on_activate)

    def _on_activate(self, _app) -> None:
        win = CajWindow(self, self._initial_files, self._auto_start)
        win.present()


def run_gtk(initial_files: list[Path], auto_start: bool) -> None:
    Adw.init()
    app = CajApp(initial_files, auto_start)
    app.run([])
