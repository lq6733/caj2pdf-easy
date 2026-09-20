#!/usr/bin/env python3
"""Compile JBIG decoder libraries for the current platform."""

from __future__ import annotations

import os
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


if __name__ == "__main__":
    try:
        build()
    except Exception as exc:
        print(f"编译解码库失败：{exc}", file=sys.stderr)
        sys.exit(1)
