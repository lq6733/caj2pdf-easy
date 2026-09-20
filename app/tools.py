"""Helpers for locating tools and repairing generated PDF files."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def which(name: str) -> str | None:
    return shutil.which(name)


def repair_pdf(src: str | Path, dst: str | Path) -> str:
    """Repair xref / reconstruct a PDF. Returns the backend that succeeded."""
    src = str(src)
    dst = str(dst)
    errors: list[str] = []

    try:
        import pymupdf

        doc = pymupdf.open(src)
        try:
            doc.save(
                dst,
                garbage=4,
                deflate=True,
                clean=True,
                encryption=pymupdf.PDF_ENCRYPT_NONE,
            )
        finally:
            doc.close()
        if Path(dst).exists() and Path(dst).stat().st_size > 0:
            return "pymupdf"
    except Exception as exc:
        errors.append(f"pymupdf: {exc}")

    mutool = which("mutool")
    if mutool:
        try:
            subprocess.check_output([mutool, "clean", src, dst], stderr=subprocess.STDOUT)
            if Path(dst).exists() and Path(dst).stat().st_size > 0:
                return "mutool"
        except Exception as exc:
            errors.append(f"mutool: {exc}")

    shutil.copyfile(src, dst)
    if errors:
        print("PDF 修复失败，已原样复制：", "; ".join(errors))
    return "copy"


def open_path(path: Path) -> None:
    path = Path(path)
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
        return
    subprocess.Popen(["xdg-open", str(path)])


def has_display() -> bool:
    if sys.platform in {"win32", "darwin"}:
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
