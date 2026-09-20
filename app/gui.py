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

from app.engine import ConvertResult, collect_files, convert_file

APP_ID = "io.github.caj2pdf.easy"
APP_TITLE = "CAJ 转 PDF"


@dataclass
class Job:
    path: Path
    status: str = "等待转换"
    ok: bool | None = None
    message: str = ""
    output: Path | None = None
    format_name: str = ""
    detail: str = ""
    row: Gtk.ListBoxRow | None = field(default=None, repr=False)


class CajWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application, initial_files: list[Path], auto_start: bool) -> None:
        super().__init__(application=app, title=APP_TITLE)
        self.set_default_size(760, 640)
        self.jobs: list[Job] = []
        self.busy = False
        self._auto_start = auto_start
        self._build_ui()
        if initial_files:
            self.add_paths(initial_files)
            if auto_start:
                GLib.idle_add(self.start_convert)

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
            label="把知网下载的 CAJ 文件拖进来，或点按钮选择。\n转换后的 PDF 会保存在原文件旁边，文件名几乎一样。"
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
        drop_title = Gtk.Label(label="把 CAJ 文件或文件夹拖到这里")
        drop_title.add_css_class("title-3")
        drop_sub = Gtk.Label(label="也可以一次拖很多个")
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

        list_label = Gtk.Label(label="待转换文件")
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
        self.empty_row = Gtk.Label(label="还没有文件。请先选择或拖入 CAJ。")
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
        self.btn_open = Gtk.Button(label="打开结果所在文件夹")
        self.btn_open.add_css_class("pill")
        self.btn_open.set_sensitive(False)
        self.btn_open.connect("clicked", self._open_results)
        action.append(self.btn_convert)
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
        dialog = Gtk.FileDialog(title="选择包含 CAJ 文件的文件夹")
        dialog.select_folder(self, None, self._on_folder_chosen)

    def _on_folder_chosen(self, dialog: Gtk.FileDialog, result) -> None:
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        loc = folder.get_path()
        if loc:
            self.add_paths([Path(loc)])

    def add_paths(self, paths: list[Path]) -> None:
        files = collect_files(paths)
        existing = {job.path for job in self.jobs}
        added = 0
        skipped_pdf = 0
        for path in files:
            if path in existing:
                continue
            if path.with_suffix(".pdf").exists():
                skipped_pdf += 0  # still allow reconvert
            self.jobs.append(Job(path=path))
            added += 1
        if added:
            self.refresh_list()
        elif not files:
            self.summary.set_text("没有找到 CAJ/KDH 文件。请确认选的是知网下载的论文文件。")
        _ = skipped_pdf

    def clear_jobs(self) -> None:
        if self.busy:
            return
        self.jobs.clear()
        self.btn_open.set_sensitive(False)
        self.summary.set_text("")
        self.progress.set_fraction(0)
        self.progress.set_text("准备就绪")
        self.refresh_list()

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
            if job.format_name:
                status = f"{status}  ·  {job.format_name}"
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

        self.btn_convert.set_sensitive(not self.busy)

    def start_convert(self) -> None:
        if self.busy or not self.jobs:
            return
        self.busy = True
        self.btn_convert.set_sensitive(False)
        self.btn_files.set_sensitive(False)
        self.btn_folder.set_sensitive(False)
        self.btn_clear.set_sensitive(False)
        self.btn_open.set_sensitive(False)
        self.summary.set_text("正在转换，请稍等，不要关闭窗口。")
        for job in self.jobs:
            job.status = "等待转换"
            job.ok = None
            job.message = ""
            job.output = None
            job.detail = ""
        self.refresh_list()
        threading.Thread(target=self._convert_worker, daemon=True).start()
        return False

    def _convert_worker(self) -> None:
        total = len(self.jobs)
        for index, job in enumerate(self.jobs, start=1):
            GLib.idle_add(self._mark_running, job, index, total)
            try:
                result = convert_file(job.path)
            except Exception as exc:
                result = ConvertResult(
                    source=job.path,
                    output=None,
                    ok=False,
                    format_name="",
                    message=f"转换失败：{exc}",
                    detail=traceback.format_exc(),
                )
            GLib.idle_add(self._mark_done, job, result, index, total)
        GLib.idle_add(self._finish_all)

    def _mark_running(self, job: Job, index: int, total: int) -> None:
        job.status = "正在转换"
        self.progress.set_fraction((index - 1) / total)
        self.progress.set_text(f"正在转换 {index}/{total}：{job.path.name}")
        self.refresh_list()

    def _mark_done(self, job: Job, result: ConvertResult, index: int, total: int) -> None:
        job.ok = result.ok
        job.status = "转换成功" if result.ok else "转换失败"
        job.message = result.message
        job.output = result.output
        job.format_name = result.format_name
        job.detail = result.detail
        self.progress.set_fraction(index / total)
        self.refresh_list()

    def _finish_all(self) -> None:
        self.busy = False
        self.btn_files.set_sensitive(True)
        self.btn_folder.set_sensitive(True)
        self.btn_clear.set_sensitive(True)
        ok_n = sum(1 for job in self.jobs if job.ok)
        fail_n = sum(1 for job in self.jobs if job.ok is False)
        self.btn_convert.set_sensitive(True)
        self.btn_open.set_sensitive(ok_n > 0)
        if fail_n == 0:
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
