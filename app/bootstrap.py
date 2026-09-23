"""Create the local virtualenv, install Python deps, and build native libs."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def venv_dir() -> Path:
    return ROOT / ".venv"


def ready_marker() -> Path:
    return venv_dir() / ".caj2pdf-ready"


def venv_python() -> Path:
    if os.name == "nt":
        return venv_dir() / "Scripts" / "python.exe"
    return venv_dir() / "bin" / "python"


def venv_pythonw() -> Path:
    if os.name == "nt":
        candidate = venv_dir() / "Scripts" / "pythonw.exe"
        if candidate.is_file():
            return candidate
    return venv_python()


def in_project_venv() -> bool:
    try:
        return Path(sys.prefix).resolve() == venv_dir().resolve()
    except OSError:
        return False


def _print(msg: str) -> None:
    print(msg, flush=True)


def _run(cmd: list[str], **kwargs) -> None:
    subprocess.run(cmd, check=True, **kwargs)


def create_venv() -> None:
    py = venv_python()
    if py.is_file():
        return
    _print("正在创建本地 Python 环境（只需这一次）…")
    args = [sys.executable, "-m", "venv"]
    if sys.platform.startswith("linux"):
        args.append("--system-site-packages")
    args.append(str(venv_dir()))
    _run(args)


def reexec_into_venv() -> None:
    if in_project_venv():
        return
    create_venv()
    py = venv_python()
    argv = [str(py), "-m", "app", *sys.argv[1:]]
    os.execv(str(py), argv)


def deps_ready() -> bool:
    try:
        import imagesize  # noqa: F401
        import PIL  # noqa: F401
        import pypdf  # noqa: F401
        import pymupdf  # noqa: F401
        return True
    except Exception:
        return False


def install_deps() -> None:
    if deps_ready():
        return
    _print("正在安装转换所需的 Python 组件（只需这一次，需要联网）…")
    pip = [sys.executable, "-m", "pip"]
    try:
        _run(pip + ["install", "-U", "pip"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    _run(pip + ["install", "-r", str(ROOT / "requirements.txt")])


def ensure_native(optional: bool = True) -> None:
    from app.build_native import build, libraries_exist

    if libraries_exist():
        return
    _print("正在编译图片解码库（只需这一次）…")
    try:
        build()
    except Exception as exc:
        message = f"图片解码库编译失败：{exc}"
        if optional:
            _print(message)
            _print("普通 CAJ/KDH 仍可转换；含扫描图片的 HN/C8 可能失败。")
            return
        raise RuntimeError(message) from exc


def ensure_runtime(optional_native: bool = True) -> None:
    os.chdir(ROOT)
    create_venv()
    reexec_into_venv()
    install_deps()
    ensure_native(optional=optional_native)
    try:
        ready_marker().write_text("ok\n", encoding="utf-8")
    except OSError:
        pass


def _dialog(message: str, title: str, error: bool) -> None:
    stream = sys.stderr if error else sys.stdout
    print(message, file=stream, flush=True)
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, message, title, 0x10 if error else 0x40)
            return
        except Exception:
            pass
    if sys.platform == "darwin":
        try:
            safe = message.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.run(
                ["osascript", "-e", f'display dialog "{safe}" with title "{title}" buttons {{"好"}} default button 1'],
                check=False,
            )
            return
        except Exception:
            pass
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", title, message], check=False)


def show_error(message: str, title: str = "CAJ 转 PDF") -> None:
    _dialog(message, title, error=True)


def show_info(message: str, title: str = "CAJ 转 PDF") -> None:
    _dialog(message, title, error=False)
