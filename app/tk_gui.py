"""Cross-platform Chinese GUI using tkinter."""

from __future__ import annotations

import os
import sys
import threading
import traceback
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

from app.engine import (
    KIND_LABELS,
    ConvertResult,
    collect_files,
    collect_pdfs,
    convert_file,
    ocr_image_pdf,
)
from app.scan import tesseract_install_message, tesseract_languages
from app.tk_theme import (
    apply_theme,
    apply_window_icon,
    draw_drop_card,
    enable_dpi,
    header_icon_photo,
    ui_fonts,
)
from app.tools import open_path

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


def _filetypes() -> list[tuple[str, str]]:
    if sys.platform == "win32":
        patterns = "*.caj;*.kdh;*.hn;*.nh;*.c8;*.epub"
    else:
        patterns = "*.caj *.kdh *.hn *.nh *.c8 *.epub"
    return [("可转换文件", patterns), ("所有文件", "*.*")]


def _pdf_filetypes() -> list[tuple[str, str]]:
    if sys.platform == "win32":
        patterns = "*.pdf"
    else:
        patterns = "*.pdf"
    return [("PDF 文件", patterns), ("所有文件", "*.*")]


class CajTkWindow:
    def __init__(self, initial_files: list[Path], auto_start: bool) -> None:
        enable_dpi()
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("820x680")
        self.root.minsize(640, 540)
        self.jobs: list[Job] = []
        self.busy = False
        self._active_task = "convert"
        self._auto_start = auto_start
        self._fonts = ui_fonts()
        self._colors = apply_theme(self.root)
        self._icon_photos = apply_window_icon(self.root)
        self._header_icon = header_icon_photo(48)
        self._drop_hover = False
        self._build()
        if initial_files:
            self.add_paths(initial_files)
            if auto_start:
                if any(job.task == "convert" for job in self.jobs):
                    self.root.after(200, self.start_convert)
                elif any(job.task == "ocr" for job in self.jobs):
                    self.root.after(200, self.start_ocr)

    def _build(self) -> None:
        colors = self._colors
        outer = ttk.Frame(self.root, padding=(22, 18, 22, 16))
        outer.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(outer)
        header.pack(fill=tk.X, pady=(0, 12))
        if self._header_icon is not None:
            icon = ttk.Label(header, image=self._header_icon)
            icon.pack(side=tk.LEFT, padx=(0, 12))
        titles = ttk.Frame(header)
        titles.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(titles, text=APP_TITLE, style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            titles,
            text="选文件，点一下，就能转成谁都能打开的 PDF",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        self.drop_canvas = tk.Canvas(
            outer,
            height=96,
            highlightthickness=0,
            bd=0,
            bg=colors["bg"],
            cursor="hand2",
        )
        self.drop_canvas.pack(fill=tk.X, pady=(0, 12))
        self.drop_canvas.bind("<Configure>", lambda _e: self._paint_drop())
        self.drop_canvas.bind("<Enter>", self._on_drop_enter)
        self.drop_canvas.bind("<Leave>", self._on_drop_leave)
        self.drop_canvas.bind("<Button-1>", lambda _e: self._choose_files())

        buttons = ttk.Frame(outer)
        buttons.pack(fill=tk.X, pady=(0, 8))
        self.btn_files = ttk.Button(buttons, text="选择文件", style="Accent.TButton", command=self._choose_files)
        self.btn_files.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_folder = ttk.Button(buttons, text="选择文件夹", command=self._choose_folder)
        self.btn_folder.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_clear = ttk.Button(buttons, text="清空列表", command=self.clear_jobs)
        self.btn_clear.pack(side=tk.LEFT)

        ttk.Label(outer, text="文件列表", style="Heading.TLabel").pack(anchor="w", pady=(8, 4))

        list_wrap = ttk.Frame(outer, style="Card.TFrame")
        list_wrap.pack(fill=tk.BOTH, expand=True)
        self.list_frame = list_wrap
        self.tree = ttk.Treeview(
            list_wrap,
            columns=("status", "message"),
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="文件", anchor="w")
        self.tree.heading("status", text="状态", anchor="w")
        self.tree.heading("message", text="说明", anchor="w")
        self.tree.column("#0", width=240, stretch=True)
        self.tree.column("status", width=210, stretch=False)
        self.tree.column("message", width=320, stretch=True)
        scroll = ttk.Scrollbar(list_wrap, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.tag_configure("ok", foreground=colors["success"])
        self.tree.tag_configure("fail", foreground=colors["danger"])
        self.tree.tag_configure("run", foreground=colors["accent"])
        self.tree.tag_configure("wait", foreground=colors["muted"])
        self.tree.tag_configure("skip", foreground=colors["warn"])
        self.tree.tag_configure("odd", background=colors["stripe"])
        self.empty = ttk.Label(
            list_wrap,
            text="还没有文件。点上面的蓝色按钮，或点虚线框选择。",
            style="Muted.TLabel",
            justify="center",
        )

        action = ttk.Frame(outer)
        action.pack(fill=tk.X, pady=(14, 6))
        self.btn_convert = ttk.Button(action, text="开始转换", style="Accent.TButton", command=self.start_convert)
        self.btn_convert.pack(side=tk.LEFT)
        self.btn_ocr = ttk.Button(action, text="识别图片 PDF", command=self.start_ocr)
        self.btn_ocr.pack(side=tk.LEFT, padx=8)
        self.btn_open = ttk.Button(action, text="打开输出文件夹", command=self._open_results, state=tk.DISABLED)
        self.btn_open.pack(side=tk.LEFT, padx=8)

        self.progress = ttk.Progressbar(outer, mode="determinate")
        self.progress.pack(fill=tk.X, pady=(6, 4))
        self.progress_text = ttk.Label(outer, text="准备就绪", style="Status.TLabel")
        self.progress_text.pack(anchor="w")
        self.summary = ttk.Label(outer, text="", style="Summary.TLabel", wraplength=760, justify="left")
        self.summary.pack(anchor="w", pady=(6, 0))
        just = os.environ.get("CAJ2PDF_JUST_UPDATED", "").strip()
        if just:
            self.summary.configure(text=f"已自动更新到 {just}。")

        self.root.bind("<Configure>", self._on_resize)
        self.btn_convert.state(["disabled"])
        self._paint_drop()
        self._show_empty(True)

    def _on_resize(self, event) -> None:
        if event.widget is self.root:
            self.summary.configure(wraplength=max(event.width - 80, 360))

    def _paint_drop(self) -> None:
        draw_drop_card(self.drop_canvas, self._drop_hover, self._fonts, self._colors)

    def _on_drop_enter(self, _event=None) -> None:
        self._drop_hover = True
        self._paint_drop()

    def _on_drop_leave(self, _event=None) -> None:
        self._drop_hover = False
        self._paint_drop()

    def _show_empty(self, show: bool) -> None:
        if show:
            self.empty.place(relx=0.5, rely=0.55, anchor="center")
        else:
            self.empty.place_forget()

    def _choose_files(self) -> None:
        paths = filedialog.askopenfilenames(title="选择要转换的 CAJ 或 EPUB 文件", filetypes=_filetypes())
        if paths:
            self.add_paths([Path(p) for p in paths])

    def _choose_folder(self) -> None:
        folder = filedialog.askdirectory(title="选择包含 CAJ、EPUB 或 PDF 的文件夹")
        if folder:
            self.add_paths([Path(folder)])

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
            self.summary.configure(text="没有找到可以转换的文件。请选择 CAJ、EPUB，或图片版 PDF。")
            return
        bits: list[str] = []
        if added_caj:
            bits.append(f"已加入 {added_caj} 个文件，点「开始转换」。")
        if added_pdf:
            bits.append(f"已加入 {added_pdf} 个 PDF，点「识别图片 PDF」识别文字。")
        if bits:
            self.summary.configure(text=" ".join(bits))
        if start_ocr:
            self.start_ocr()

    def clear_jobs(self) -> None:
        if self.busy:
            return
        self.jobs.clear()
        self.btn_open.state(["disabled"])
        self.summary.configure(text="")
        self.progress["value"] = 0
        self.progress_text.configure(text="准备就绪")
        self.refresh_list()

    def _pending(self, task: str) -> list[Job]:
        if task == "ocr":
            return [job for job in self.jobs if job.task == "ocr" and job.ok is None]
        return [job for job in self.jobs if job.task == "convert"]

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        state = ["disabled"] if busy else ["!disabled"]
        self.btn_files.state(state)
        self.btn_folder.state(state)
        self.btn_clear.state(state)
        self.btn_ocr.state(state)
        if busy:
            self.btn_convert.state(["disabled"])
            self.btn_open.state(["disabled"])
        elif any(job.task == "convert" for job in self.jobs):
            self.btn_convert.state(["!disabled"])
        else:
            self.btn_convert.state(["disabled"])

    def _row_tags(self, job: Job, index: int) -> tuple[str, ...]:
        tags: list[str] = []
        if job.ok is True and job.skipped:
            tags.append("skip")
        elif job.ok is True:
            tags.append("ok")
        elif job.ok is False:
            tags.append("fail")
        elif "正在" in job.status:
            tags.append("run")
        else:
            tags.append("wait")
        if index % 2 == 1:
            tags.append("odd")
        return tuple(tags)

    def refresh_list(self) -> None:
        self.tree.delete(*self.tree.get_children())
        if not self.jobs:
            self._show_empty(True)
            self.btn_convert.state(["disabled"])
            return
        self._show_empty(False)
        for index, job in enumerate(self.jobs):
            status = job.status
            extras = [x for x in (job.format_name, KIND_LABELS.get(job.kind, "")) if x]
            if extras:
                status = f"{status}  ·  " + "  ·  ".join(extras)
            self.tree.insert(
                "",
                tk.END,
                text=job.path.name,
                values=(status, job.message),
                tags=self._row_tags(job, index),
            )
        if not self.busy:
            if any(job.task == "convert" for job in self.jobs):
                self.btn_convert.state(["!disabled"])
            else:
                self.btn_convert.state(["disabled"])

    def start_convert(self) -> None:
        if self.busy:
            return
        jobs = self._pending("convert")
        if not jobs:
            self.summary.configure(text="请先选择要转换的 CAJ 或 EPUB 文件。图片版 PDF 请点「识别图片 PDF」。")
            return
        self._run_jobs("convert", jobs)

    def start_ocr(self) -> None:
        if self.busy:
            return
        if not tesseract_languages():
            messagebox.showwarning(APP_TITLE, tesseract_install_message())
            return
        jobs = self._pending("ocr")
        if not jobs:
            paths = filedialog.askopenfilenames(title="选择要识别的图片版 PDF", filetypes=_pdf_filetypes())
            if not paths:
                return
            self.add_paths([Path(p) for p in paths], start_ocr=True)
            return
        self._run_jobs("ocr", jobs)

    def _run_jobs(self, task: str, jobs: list[Job]) -> None:
        self._active_task = task
        self._set_busy(True)
        if task == "ocr":
            self.summary.configure(text="正在识别文字，请稍等，不要关闭窗口。每一页大约需要几秒钟。")
            for job in jobs:
                job.status = "等待识别"
                job.ok = None
                job.message = ""
                job.output = None
                job.kind = ""
                job.detail = ""
                job.skipped = False
        else:
            self.summary.configure(text="正在转换，请稍等，不要关闭窗口。")
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
            self.root.after(0, self._mark_running, job, task, index, total)

            def progress(page: int, pages: int, job=job, index=index, total=total) -> None:
                self.root.after(0, self._mark_page, job, page, pages, index, total)

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
            self.root.after(0, self._mark_done, job, task, result, index, total)
        self.root.after(0, self._finish_all, task, jobs)

    def _mark_running(self, job: Job, task: str, index: int, total: int) -> None:
        job.status = "正在识别" if task == "ocr" else "正在转换"
        self.progress["maximum"] = max(total, 1)
        self.progress["value"] = index - 1
        verb = "正在识别" if task == "ocr" else "正在转换"
        self.progress_text.configure(text=f"{verb} {index}/{total}：{job.path.name}")
        self.refresh_list()

    def _mark_page(self, job: Job, page: int, pages: int, index: int, total: int) -> None:
        self.progress["maximum"] = 1000
        fraction = ((index - 1) + (page / max(pages, 1))) / max(total, 1)
        self.progress["value"] = min(1000, fraction * 1000)
        verb = "正在识别" if self._active_task == "ocr" else "正在转换"
        self.progress_text.configure(text=f"{verb} {page}/{pages} 页：{job.path.name}")

    def _status_for(self, task: str, result: ConvertResult) -> str:
        if task == "ocr":
            if result.skipped:
                return "无需识别"
            return "识别成功" if result.ok else "识别失败"
        return "转换成功" if result.ok else "转换失败"

    def _mark_done(self, job: Job, task: str, result: ConvertResult, index: int, total: int) -> None:
        job.ok = result.ok
        job.status = self._status_for(task, result)
        job.message = result.message
        job.output = result.output
        job.format_name = result.format_name
        job.kind = result.kind
        job.detail = result.detail
        job.skipped = result.skipped
        self.progress["maximum"] = max(total, 1)
        self.progress["value"] = index
        self.refresh_list()

    def _finish_all(self, task: str, jobs: list[Job]) -> None:
        self._set_busy(False)
        ok_n = sum(1 for job in jobs if job.ok)
        fail_n = sum(1 for job in jobs if job.ok is False)
        skip_n = sum(1 for job in jobs if job.skipped)
        done_n = ok_n - skip_n
        if any(job.ok and job.output is not None for job in self.jobs):
            self.btn_open.state(["!disabled"])
        if task == "ocr":
            if fail_n == 0 and skip_n == ok_n and ok_n:
                self.progress_text.configure(text="全部完成")
                self.summary.configure(text="这些 PDF 已经可以选中文字，不用再识别。")
            elif fail_n == 0:
                self.progress_text.configure(text="全部完成")
                self.summary.configure(
                    text=f"已经识别好 {done_n} 个 PDF。新文件在原 PDF 旁边，文件名带「已识别」；原来的 PDF 没有改动。"
                )
            elif ok_n == 0:
                self.progress_text.configure(text="识别失败")
                self.summary.configure(text="这次没有识别成功。请看列表里的失败原因。")
            else:
                self.progress_text.configure(text="部分完成")
                self.summary.configure(
                    text=f"成功 {ok_n} 个，失败 {fail_n} 个。识别后的文件在原 PDF 旁边；失败的请看列表说明。"
                )
        elif fail_n == 0:
            self.progress_text.configure(text="全部完成")
            self.summary.configure(
                text=f"已经全部转好，共 {ok_n} 个 PDF。文件就在原来的文件旁边，用文档阅读器打开即可。"
            )
        elif ok_n == 0:
            self.progress_text.configure(text="转换失败")
            self.summary.configure(text="这次没有成功。请看列表里的失败原因。")
        else:
            self.progress_text.configure(text="部分完成")
            self.summary.configure(
                text=f"成功 {ok_n} 个，失败 {fail_n} 个。成功的 PDF 在原文件旁边；失败的请看列表说明。"
            )

    def _open_results(self) -> None:
        for job in self.jobs:
            if job.ok and job.output is not None:
                try:
                    open_path(job.output.parent)
                except Exception as exc:
                    messagebox.showerror(APP_TITLE, f"打不开文件夹：{exc}")
                return

    def run(self) -> None:
        self.root.mainloop()


def run_tk(initial_files: list[Path], auto_start: bool) -> None:
    enable_dpi()
    CajTkWindow(initial_files, auto_start).run()
