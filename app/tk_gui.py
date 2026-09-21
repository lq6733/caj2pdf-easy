"""Cross-platform Chinese GUI using tkinter."""

from __future__ import annotations

import sys
import threading
import traceback
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

from app.engine import KIND_LABELS, ConvertResult, collect_files, convert_file
from app.tools import open_path

APP_TITLE = "CAJ 转 PDF"


@dataclass
class Job:
    path: Path
    status: str = "等待转换"
    ok: bool | None = None
    message: str = ""
    output: Path | None = None
    format_name: str = ""
    kind: str = ""
    detail: str = ""


def _ui_font() -> tuple[str, int]:
    if sys.platform == "win32":
        return ("Microsoft YaHei UI", 10)
    if sys.platform == "darwin":
        return ("PingFang SC", 13)
    return ("Noto Sans CJK SC", 10)


def _filetypes() -> list[tuple[str, str]]:
    if sys.platform == "win32":
        patterns = "*.caj;*.kdh;*.hn;*.nh;*.c8"
    else:
        patterns = "*.caj *.kdh *.hn *.nh *.c8"
    return [("知网文件", patterns), ("所有文件", "*.*")]


class CajTkWindow:
    def __init__(self, initial_files: list[Path], auto_start: bool) -> None:
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("760x620")
        self.root.minsize(560, 480)
        self.jobs: list[Job] = []
        self.busy = False
        self._auto_start = auto_start
        self._font = _ui_font()
        self._build()
        if initial_files:
            self.add_paths(initial_files)
            if auto_start:
                self.root.after(200, self.start_convert)

    def _build(self) -> None:
        pad = {"padx": 16, "pady": 6}
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(outer, text=APP_TITLE, font=(_ui_font()[0], 18))
        title.pack(anchor="w", **pad)
        hint = ttk.Label(
            outer,
            text="选择知网下载的 CAJ 文件，点「开始转换」。\n转换后的 PDF 会保存在原文件旁边，原来的 CAJ 不会被删除。",
            justify="left",
        )
        hint.pack(anchor="w", padx=16, pady=(0, 8))

        buttons = ttk.Frame(outer)
        buttons.pack(fill=tk.X, padx=16, pady=4)
        ttk.Button(buttons, text="选择文件", command=self._choose_files).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(buttons, text="选择文件夹", command=self._choose_folder).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(buttons, text="清空列表", command=self.clear_jobs).pack(side=tk.LEFT)

        list_frame = ttk.Frame(outer)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)
        self.tree = ttk.Treeview(
            list_frame,
            columns=("status", "message"),
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("status", text="状态")
        self.tree.heading("message", text="说明")
        self.tree.column("status", width=160, stretch=False)
        self.tree.column("message", width=420, stretch=True)
        scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Show file name as the tree item text by using a hidden first column via displaycolumns
        self.tree["show"] = "tree headings"
        self.tree.heading("#0", text="文件")
        self.tree.column("#0", width=220, stretch=True)

        action = ttk.Frame(outer)
        action.pack(fill=tk.X, padx=16, pady=4)
        self.btn_convert = ttk.Button(action, text="开始转换", command=self.start_convert)
        self.btn_convert.pack(side=tk.LEFT)
        self.btn_open = ttk.Button(action, text="打开输出文件夹", command=self._open_results, state=tk.DISABLED)
        self.btn_open.pack(side=tk.LEFT, padx=8)

        self.progress = ttk.Progressbar(outer, mode="determinate")
        self.progress.pack(fill=tk.X, padx=16, pady=(8, 4))
        self.progress_text = ttk.Label(outer, text="准备就绪")
        self.progress_text.pack(anchor="w", padx=16)
        self.summary = ttk.Label(outer, text="", wraplength=700, justify="left")
        self.summary.pack(anchor="w", padx=16, pady=(4, 8))

        try:
            self.root.option_add("*Font", self._font)
        except tk.TclError:
            pass
        self.btn_convert.state(["disabled"])

    def _choose_files(self) -> None:
        paths = filedialog.askopenfilenames(title="选择要转换的 CAJ 文件", filetypes=_filetypes())
        if paths:
            self.add_paths([Path(p) for p in paths])

    def _choose_folder(self) -> None:
        folder = filedialog.askdirectory(title="选择包含 CAJ 文件的文件夹")
        if folder:
            self.add_paths([Path(folder)])

    def add_paths(self, paths: list[Path]) -> None:
        files = collect_files(paths)
        existing = {job.path for job in self.jobs}
        added = 0
        for path in files:
            if path in existing:
                continue
            self.jobs.append(Job(path=path))
            added += 1
        if added:
            self.refresh_list()
        elif not files:
            self.summary.configure(text="没有找到 CAJ/KDH 文件。请确认选的是知网下载的论文文件。")

    def clear_jobs(self) -> None:
        if self.busy:
            return
        self.jobs.clear()
        self.btn_open.state(["disabled"])
        self.summary.configure(text="")
        self.progress["value"] = 0
        self.progress_text.configure(text="准备就绪")
        self.refresh_list()

    def refresh_list(self) -> None:
        self.tree.delete(*self.tree.get_children())
        if not self.jobs:
            self.btn_convert.state(["disabled"])
            return
        for job in self.jobs:
            status = job.status
            extras = [x for x in (job.format_name, KIND_LABELS.get(job.kind, "")) if x]
            if extras:
                status = f"{status}  ·  " + "  ·  ".join(extras)
            self.tree.insert("", tk.END, text=job.path.name, values=(status, job.message))
        if not self.busy:
            self.btn_convert.state(["!disabled"])

    def start_convert(self) -> None:
        if self.busy or not self.jobs:
            return
        self.busy = True
        self.btn_convert.state(["disabled"])
        self.btn_open.state(["disabled"])
        self.summary.configure(text="正在转换，请稍等，不要关闭窗口。")
        for job in self.jobs:
            job.status = "等待转换"
            job.ok = None
            job.message = ""
            job.output = None
            job.kind = ""
            job.detail = ""
        self.refresh_list()
        threading.Thread(target=self._convert_worker, daemon=True).start()

    def _convert_worker(self) -> None:
        total = len(self.jobs)
        for index, job in enumerate(self.jobs, start=1):
            self.root.after(0, self._mark_running, job, index, total)
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
            self.root.after(0, self._mark_done, job, result, index, total)
        self.root.after(0, self._finish_all)

    def _mark_running(self, job: Job, index: int, total: int) -> None:
        job.status = "正在转换"
        self.progress["maximum"] = total
        self.progress["value"] = index - 1
        self.progress_text.configure(text=f"正在转换 {index}/{total}：{job.path.name}")
        self.refresh_list()

    def _mark_done(self, job: Job, result: ConvertResult, index: int, total: int) -> None:
        job.ok = result.ok
        job.status = "转换成功" if result.ok else "转换失败"
        job.message = result.message
        job.output = result.output
        job.format_name = result.format_name
        job.kind = result.kind
        job.detail = result.detail
        self.progress["value"] = index
        self.refresh_list()

    def _finish_all(self) -> None:
        self.busy = False
        ok_n = sum(1 for job in self.jobs if job.ok)
        fail_n = sum(1 for job in self.jobs if job.ok is False)
        self.btn_convert.state(["!disabled"])
        if ok_n > 0:
            self.btn_open.state(["!disabled"])
        if fail_n == 0:
            self.progress_text.configure(text="全部完成")
            self.summary.configure(
                text=f"已经全部转好，共 {ok_n} 个 PDF。文件就在原来的 CAJ 旁边，用文档阅读器打开即可。"
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
    CajTkWindow(initial_files, auto_start).run()
