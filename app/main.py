"""Command-line entry: choose GUI toolkit or run headless conversion."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from app.engine import collect_files, convert_file
from app.tools import has_display


def parse_args(argv: list[str]) -> tuple[list[Path], bool, bool, bool, str, bool, Path | None]:
    files: list[Path] = []
    auto = False
    headless = False
    install = False
    gui = ""
    selftest = False
    out_dir: Path | None = None
    skip_next = False
    for index, arg in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if arg in {"-h", "--help"}:
            print("CAJ 转 PDF")
            print("用法: python -m app [选项] [文件或文件夹...]")
            print("  --auto        打开窗口后自动开始转换")
            print("  --headless    不打开窗口，直接在终端转换")
            print("  --install     安装桌面快捷方式")
            print("  --selftest    自测转换准确率（结果写到临时目录，不覆盖原 PDF）")
            print("  --out 目录    自测输出目录")
            print("  --gui tk      使用 tkinter 界面（Windows / macOS 默认）")
            print("  --gui gtk     使用 GTK 界面（Linux 默认）")
            print("  --version     显示版本")
            raise SystemExit(0)
        if arg in {"-V", "--version"}:
            from app import __version__

            print(__version__)
            raise SystemExit(0)
        if arg in {"--auto", "--start"}:
            auto = True
        elif arg in {"--headless", "--cli"}:
            headless = True
        elif arg in {"--install"}:
            install = True
        elif arg in {"--selftest", "--check"}:
            selftest = True
        elif arg in {"--out", "--output"}:
            if index + 1 >= len(argv):
                raise SystemExit("请在 --out 后面写输出目录")
            out_dir = Path(argv[index + 1])
            skip_next = True
        elif arg.startswith("--out="):
            out_dir = Path(arg.split("=", 1)[1])
        elif arg in {"--gui"}:
            gui = "tk"
        elif arg.startswith("--gui="):
            gui = arg.split("=", 1)[1].strip().lower()
        elif arg in {"tk", "gtk"} and gui == "tk" and not files:
            # allow `--gui tk` parsed as two tokens; if previous was --gui
            gui = arg
        elif arg.startswith("-"):
            continue
        else:
            files.append(Path(arg))
    if headless:
        auto = True
    return files, auto, headless, install, gui, selftest, out_dir


def run_headless(paths: list[Path]) -> int:
    files = collect_files(paths)
    if not files:
        print("没有找到可以转换的 CAJ/KDH 文件。")
        return 1
    failed = 0
    for src in files:
        print(f"正在转换：{src}")
        result = convert_file(src)
        print(("成功" if result.ok else "失败") + f"：{result.message}")
        if not result.ok:
            failed += 1
            if result.detail:
                print(result.detail)
    return 1 if failed else 0


def _gui_order(pref: str) -> list[str]:
    pref = (pref or "").strip().lower()
    if pref in {"tk", "tkinter"}:
        return ["tk", "gtk"]
    if pref in {"gtk", "adw", "adwaita"}:
        return ["gtk", "tk"]
    if sys.platform in {"win32", "darwin"}:
        return ["tk", "gtk"]
    return ["gtk", "tk"]


def launch_gui(files: list[Path], auto: bool, pref: str) -> None:
    errors: list[str] = []
    for name in _gui_order(pref):
        try:
            if name == "gtk":
                from app.gui import run_gtk

                run_gtk(files, auto)
                return
            from app.tk_gui import run_tk

            run_tk(files, auto)
            return
        except SystemExit:
            raise
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    print("无法打开图形界面。")
    print("Windows / macOS 请确认安装 Python 时勾选 tcl/tk。")
    print("Linux 可安装：python3-gi gir1.2-gtk-4.0 gir1.2-adw-1  或  python3-tk")
    for item in errors:
        print(" ", item)
    raise SystemExit(1)


def main() -> None:
    os.chdir(Path(__file__).resolve().parents[1])
    argv = sys.argv[1:]
    # Support `--gui tk` as two tokens.
    normalized: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--gui" and i + 1 < len(argv) and not argv[i + 1].startswith("-"):
            normalized.append("--gui=" + argv[i + 1].strip().lower())
            i += 2
            continue
        normalized.append(argv[i])
        i += 1

    files, auto, headless, install, gui, selftest, out_dir = parse_args(normalized)
    if install:
        from app.install import install_shortcuts

        raise SystemExit(install_shortcuts())
    if selftest:
        from app.selftest import run_selftest

        raise SystemExit(run_selftest(files, out_dir))

    no_display = not has_display()
    if headless or (no_display and files):
        if no_display and not headless:
            print("没有图形界面，改为命令行转换。")
        raise SystemExit(run_headless(files))
    if no_display:
        print("没有图形界面。请加上要转换的文件，或使用 --headless。")
        raise SystemExit(1)
    launch_gui(files, auto, gui)


if __name__ == "__main__":
    main()
