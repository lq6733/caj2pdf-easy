#!/usr/bin/env python3
"""Compile JBIG decoder libraries for the current platform."""

from __future__ import annotations

import os
import platform
import ssl
import urllib.error
import urllib.request
import zipfile
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "caj2pdf"
LIB_DIR = VENDOR / "lib"
JBIG2DEC = ROOT / "vendor" / "jbig2dec"

JBIG2_SOURCES = (
    "jbig2.c",
    "jbig2_arith.c",
    "jbig2_arith_int.c",
    "jbig2_arith_iaid.c",
    "jbig2_huffman.c",
    "jbig2_hufftab.c",
    "jbig2_segment.c",
    "jbig2_page.c",
    "jbig2_symbol_dict.c",
    "jbig2_text.c",
    "jbig2_generic.c",
    "jbig2_refinement.c",
    "jbig2_mmr.c",
    "jbig2_halftone.c",
    "jbig2_image.c",
)


def is_64bit() -> bool:
    return sys.maxsize > 2**32


def library_names() -> tuple[str, str]:
    if sys.platform == "win32":
        tag = "w64" if is_64bit() else "w32"
        return f"libjbigdec-{tag}.dll", f"libjbig2codec-{tag}.dll"
    if sys.platform == "darwin":
        return "libjbigdec.dylib", "libjbig2codec.dylib"
    return "libjbigdec.so", "libjbig2codec.so"


def library_paths() -> tuple[Path, Path]:
    dec, codec = library_names()
    return VENDOR / dec, VENDOR / codec


def libraries_exist() -> bool:
    dec, codec = library_paths()
    return dec.is_file() and codec.is_file()


def _run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=cwd, env=env)


def _enable_msvc_env() -> bool:
    if shutil.which("cl"):
        return True
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    vswhere = Path(pf86) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.is_file():
        return False
    try:
        inst = subprocess.check_output(
            [
                str(vswhere),
                "-latest",
                "-products",
                "*",
                "-requires",
                "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                "-property",
                "installationPath",
            ],
            text=True,
            errors="ignore",
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return False
    if not inst:
        return False
    vcvars = Path(inst) / "VC" / "Auxiliary" / "Build" / "vcvarsall.bat"
    if not vcvars.is_file():
        return False
    arch = "x64" if is_64bit() else "x86"
    try:
        output = subprocess.check_output(
            f'"{vcvars}" {arch} && set',
            shell=True,
            text=True,
            errors="ignore",
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key:
            os.environ[key] = value
    return shutil.which("cl") is not None


def _compiler() -> tuple[str, str]:
    """Return (kind, executable). kind is 'msvc' or 'gnu'."""
    if sys.platform == "win32":
        _enable_msvc_env()
        if shutil.which("cl"):
            return "msvc", "cl"
    for name in ("g++", "clang++", "c++"):
        path = shutil.which(name)
        if path:
            return "gnu", path
    if shutil.which("cl"):
        return "msvc", "cl"
    raise FileNotFoundError(_compiler_help())


def _compiler_help() -> str:
    if sys.platform == "win32":
        return (
            "找不到 C++ 编译器。Windows 可安装：\n"
            "1) Visual Studio Build Tools，勾选「使用 C++ 的桌面开发」\n"
            "   https://visualstudio.microsoft.com/visual-cpp-build-tools/\n"
            "2) 或安装 MSYS2/MinGW，保证 g++ 在 PATH 里"
        )
    if sys.platform == "darwin":
        return "找不到 C++ 编译器。请在终端运行：xcode-select --install"
    return "找不到 C++ 编译器。Debian/Ubuntu 可安装：sudo apt install build-essential"


def _gnu_shared_flag() -> str:
    if sys.platform == "darwin":
        return "-dynamiclib"
    return "-shared"


def build() -> tuple[Path, Path]:
    VENDOR.mkdir(parents=True, exist_ok=True)
    kind, cxx = _compiler()
    dec_out, codec_out = library_paths()
    jbig2_srcs = [str(JBIG2DEC / name) for name in JBIG2_SOURCES]
    missing = [src for src in jbig2_srcs if not Path(src).is_file()]
    if missing:
        raise FileNotFoundError("缺少 jbig2dec 源码：" + ", ".join(missing))

    if kind == "msvc":
        _build_msvc(dec_out, codec_out, jbig2_srcs)
    else:
        _build_gnu(cxx, dec_out, codec_out, jbig2_srcs)

    if not dec_out.is_file() or not codec_out.is_file():
        raise RuntimeError("编译完成但没有找到生成的解码库")
    print(f"已生成 {dec_out}")
    print(f"已生成 {codec_out}")
    return dec_out, codec_out


def _build_gnu(cxx: str, dec_out: Path, codec_out: Path, jbig2_srcs: list[str]) -> None:
    common = ["-Wall", "-O2", "-fPIC", _gnu_shared_flag()]
    _run(
        [
            cxx,
            *common,
            "-o",
            str(dec_out),
            str(LIB_DIR / "jbigdec.cc"),
            str(LIB_DIR / "JBigDecode.cc"),
        ]
    )
    cmd = [
        cxx,
        *common,
        "-o",
        str(codec_out),
        str(LIB_DIR / "decode_jbig2data_x.cc"),
        *jbig2_srcs,
        "-I",
        str(JBIG2DEC),
    ]
    if sys.platform != "win32":
        cmd.append("-lm")
    _run(cmd)


def _build_msvc(dec_out: Path, codec_out: Path, jbig2_srcs: list[str]) -> None:
    env = os.environ.copy()
    with tempfile.TemporaryDirectory(prefix="caj2pdf-build-") as tmp:
        work = Path(tmp)
        _run(
            [
                "cl",
                "/nologo",
                "/O2",
                "/EHsc",
                "/LD",
                "/D_CRT_SECURE_NO_WARNINGS",
                f"/Fe:{dec_out}",
                str(LIB_DIR / "jbigdec.cc"),
                str(LIB_DIR / "JBigDecode.cc"),
            ],
            cwd=work,
            env=env,
        )
        _run(
            [
                "cl",
                "/nologo",
                "/O2",
                "/EHsc",
                "/LD",
                "/D_CRT_SECURE_NO_WARNINGS",
                f"/I{JBIG2DEC}",
                f"/Fe:{codec_out}",
                str(LIB_DIR / "decode_jbig2data_x.cc"),
                *jbig2_srcs,
            ],
            cwd=work,
            env=env,
        )


def compiler_available() -> bool:
    try:
        _compiler()
        return True
    except FileNotFoundError:
        return False




def artifact_name() -> str:
    os_name = {"linux": "Linux", "win32": "Windows", "darwin": "macOS"}.get(sys.platform, "Linux")
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64", "x64"}:
        arch = "X64"
    elif machine in {"arm64", "aarch64"}:
        arch = "ARM64"
    else:
        arch = "X64"
    return f"native-{os_name}-{arch}"


def _http_get(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "caj2pdf-easy"})
    context = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
        return resp.read()


def download_prebuilt() -> tuple[Path, Path]:
    """Fetch CI-built libraries when this computer has no compiler."""
    name = artifact_name()
    urls = (
        f"https://nightly.link/lq6733/caj2pdf-easy/workflows/ci.yml/main/{name}.zip",
        f"https://nightly.link/lq6733/caj2pdf-easy/workflows/CI/main/{name}.zip",
    )
    data = b""
    last = ""
    for url in urls:
        try:
            print(f"正在下载图片解码库（{name}）…")
            data = _http_get(url, timeout=40)
            if data[:2] == b"PK":
                break
            last = f"{url}: 不是 zip"
            data = b""
        except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as exc:
            last = f"{url}: {exc}"
            data = b""
    if not data:
        raise RuntimeError(last or "自动下载解码库失败")

    VENDOR.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="caj2pdf-native-") as tmp:
        archive = Path(tmp) / "native.zip"
        archive.write_bytes(data)
        extracted = Path(tmp) / "out"
        extracted.mkdir()
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(extracted)
        for src in extracted.rglob("*"):
            if not src.is_file():
                continue
            if not src.name.startswith("libjbig"):
                continue
            dest = VENDOR / src.name
            shutil.copy2(src, dest)
            copied.append(dest)
            print(f"已下载 {dest.name}")
    dec, codec = library_paths()
    if not dec.is_file() or not codec.is_file():
        names = ", ".join(p.name for p in copied) or "无"
        raise RuntimeError(f"下载完成但缺少解码库（得到：{names}）")
    return dec, codec


def ensure_libraries() -> tuple[bool, str]:
    """Make sure decoder libs exist. Returns (ok, help_text)."""
    if libraries_exist():
        return True, ""
    errors: list[str] = []
    if compiler_available():
        try:
            print("正在编译图片解码库…")
            build()
            if libraries_exist():
                return True, ""
        except Exception as exc:
            errors.append(f"自动编译失败：{exc}")
    else:
        errors.append(_compiler_help())
    try:
        download_prebuilt()
        if libraries_exist():
            return True, ""
    except Exception as exc:
        errors.append(f"自动下载失败：{exc}")
    return False, "\n".join(x for x in errors if x)


def library_help(detail: str = "") -> str:
    if libraries_exist():
        return (
            "这个文件有扫描图片，需要图片解码库，但当前程序没能加载它。"
            "请确认使用的是 64 位 Python。"
            "也可以删掉 vendor/caj2pdf 里的 libjbigdec / libjbig2codec 后重新打开本工具，让它自动重编或下载。"
        )
    extra = detail
    if not extra:
        ok, extra = ensure_libraries()
        if ok:
            return "图片解码库已经准备好。请再点一次「开始转换」。"
    bits = [
        "这个文件有扫描图片，需要图片解码库，但这台电脑上还没有。",
        "普通 CAJ / KDH 一般不受影响；HN / C8 扫描件需要这个库。",
    ]
    for item in (extra, _compiler_help()):
        if item and item not in bits:
            bits.append(item)
    bits.append("装好编译器或联网后，重新打开本工具会自动再试。也可以把对应系统的 libjbigdec / libjbig2codec 放到 vendor/caj2pdf/ 目录。")
    return "\n".join(bits)


if __name__ == "__main__":
    try:
        build()
    except Exception as exc:
        print(f"编译解码库失败：{exc}", file=sys.stderr)
        sys.exit(1)
