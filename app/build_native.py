#!/usr/bin/env python3
"""Compile the JBIG decoder libraries used by HN/C8 CAJ files."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "caj2pdf"
INCLUDE = ROOT / "vendor" / "jbig2dec"


def build() -> None:
    lib_dir = VENDOR / "lib"
    dec = VENDOR / "libjbigdec.so"
    codec = VENDOR / "libjbig2codec.so"
    subprocess.run(
        [
            "g++",
            "-Wall",
            "-O2",
            "-fPIC",
            "-shared",
            "-o",
            str(dec),
            str(lib_dir / "jbigdec.cc"),
            str(lib_dir / "JBigDecode.cc"),
        ],
        check=True,
    )
    subprocess.run(
        [
            "g++",
            "-Wall",
            "-O2",
            "-fPIC",
            "-shared",
            "-o",
            str(codec),
            str(lib_dir / "decode_jbig2data_x.cc"),
            "-I",
            str(INCLUDE),
            "-l:libjbig2dec.so.0",
        ],
        check=True,
    )
    print(f"已生成 {dec}")
    print(f"已生成 {codec}")


if __name__ == "__main__":
    try:
        build()
    except Exception as exc:
        print(f"编译解码库失败：{exc}", file=sys.stderr)
        sys.exit(1)
