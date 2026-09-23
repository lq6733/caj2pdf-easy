"""Check GitHub for a newer version and replace local files if needed."""

from __future__ import annotations

import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from app import __version__

ROOT = Path(__file__).resolve().parents[1]
REPO = "lq6733/caj2pdf-easy"
BRANCH = "main"
SKIP_ENV = "CAJ2PDF_SKIP_UPDATE"
JUST_UPDATED_ENV = "CAJ2PDF_JUST_UPDATED"

VERSION_URLS = (
    f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/app/__init__.py",
    f"https://cdn.jsdelivr.net/gh/{REPO}@{BRANCH}/app/__init__.py",
    f"https://hub.gitmirror.com/https://raw.githubusercontent.com/{REPO}/{BRANCH}/app/__init__.py",
)
ZIP_URLS = (
    f"https://github.com/{REPO}/archive/refs/heads/{BRANCH}.zip",
    f"https://codeload.github.com/{REPO}/zip/refs/heads/{BRANCH}",
    f"https://hub.gitmirror.com/https://github.com/{REPO}/archive/refs/heads/{BRANCH}.zip",
)
GIT_URLS = (
    f"https://github.com/{REPO}.git",
    f"https://hub.gitmirror.com/https://github.com/{REPO}.git",
)
OVERLAY_SKIP = {".git", ".venv", "__pycache__", ".caj2pdf-ready"}


@dataclass
class UpdateInfo:
    current: str
    latest: str = ""
    newer: bool = False
    error: str = ""
    source: str = ""


def parse_version(text: str) -> tuple[int, ...]:
    parts = [int(p) for p in re.findall(r"\d+", text or "")]
    return tuple(parts) if parts else (0,)


def version_from_init(text: str) -> str:
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
    return match.group(1).strip() if match else ""


def _user_agent() -> str:
    return f"caj2pdf-easy/{__version__}"


def _http_get(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _user_agent()})
    context = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
        return resp.read()


def _first_bytes(urls: tuple[str, ...], timeout: float) -> tuple[bytes, str]:
    errors: list[str] = []
    for url in urls:
        try:
            data = _http_get(url, timeout=timeout)
            if data:
                return data, url
        except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError("；".join(errors[:2]) or "无法联网")


def fetch_latest_version(timeout: float = 5.0) -> UpdateInfo:
    info = UpdateInfo(current=__version__)
    try:
        data, url = _first_bytes(VERSION_URLS, timeout=timeout)
        latest = version_from_init(data.decode("utf-8", errors="replace"))
        if not latest:
            info.error = "网上的版本号读不出来。"
            return info
        info.latest = latest
        info.source = url
        info.newer = parse_version(latest) > parse_version(info.current)
        return info
    except Exception as exc:
        info.error = f"暂时连不上更新服务器：{exc}"
        return info


def _git(*args: str, timeout: int = 40) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _has_git_repo() -> bool:
    return (ROOT / ".git").is_dir() and shutil.which("git") is not None


def git_is_dirty() -> bool:
    if not _has_git_repo():
        return False
    result = _git("status", "--porcelain")
    return result.returncode == 0 and bool(result.stdout.strip())


def _git_fetch() -> bool:
    result = _git("fetch", "--quiet", "origin", BRANCH)
    if result.returncode == 0:
        return True
    for url in GIT_URLS:
        result = _git("fetch", "--quiet", url, BRANCH)
        if result.returncode == 0:
            return True
    return False


def _apply_git_update() -> None:
    if not _git_fetch():
        raise RuntimeError("用 Git 拉取失败，可能是网络不通。")
    merged = _git("merge", "--ff-only", "FETCH_HEAD")
    if merged.returncode != 0:
        raise RuntimeError((merged.stderr or merged.stdout or "无法快进合并").strip())


def _extract_zip_root(extracted: Path) -> Path:
    children = [p for p in extracted.iterdir() if p.is_dir() and not p.name.startswith(".")]
    if len(children) == 1:
        return children[0]
    return extracted


def _overlay_tree(src: Path, dest: Path) -> None:
    for item in src.iterdir():
        if item.name in OVERLAY_SKIP or item.name.endswith(".pyc"):
            continue
        target = dest / item.name
        if item.is_dir():
            if target.exists() and target.is_dir():
                _overlay_tree(item, target)
            else:
                if target.exists():
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink()
                shutil.copytree(item, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def _chmod_launchers() -> None:
    if os.name == "nt":
        return
    for name in ("caj-to-pdf", "install-desktop.sh", "开始转换.sh", "开始转换.command", "安装到桌面.sh", "安装到桌面.command"):
        path = ROOT / name
        if path.is_file():
            try:
                path.chmod(path.stat().st_mode | 0o111)
            except OSError:
                pass


def _apply_zip_update() -> None:
    data, _url = _first_bytes(ZIP_URLS, timeout=45.0)
    with tempfile.TemporaryDirectory(prefix="caj2pdf-update-") as tmp:
        tmpdir = Path(tmp)
        archive = tmpdir / "src.zip"
        archive.write_bytes(data)
        extracted = tmpdir / "extracted"
        extracted.mkdir()
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(extracted)
        _overlay_tree(_extract_zip_root(extracted), ROOT)
    _chmod_launchers()


def apply_update() -> None:
    if _has_git_repo():
        _apply_git_update()
        return
    _apply_zip_update()


def _restart() -> None:
    os.environ[SKIP_ENV] = "1"
    argv = [sys.executable, "-m", "app", *sys.argv[1:]]
    os.execv(sys.executable, argv)


def maybe_update(*, force: bool = False, restart: bool = False) -> UpdateInfo:
    """Check and install a newer version. Never overwrites a dirty git tree."""
    info = UpdateInfo(current=__version__)
    if not force and os.environ.get(SKIP_ENV):
        return info
    if git_is_dirty():
        info.error = "本地文件有未保存的修改，已跳过自动更新，以免覆盖你的改动。"
        return info
    info = fetch_latest_version()
    if info.error and not info.latest:
        return info
    if not info.newer:
        return info
    try:
        from app.bootstrap import show_info

        show_info(f"发现新版本 {info.latest}，正在更新，请稍等…")
    except Exception:
        print(f"发现新版本 {info.latest}，正在更新…", flush=True)
    try:
        apply_update()
    except Exception as exc:
        info.error = f"更新失败：{exc}"
        return info
    os.environ[JUST_UPDATED_ENV] = info.latest
    if restart:
        _restart()
    return info
