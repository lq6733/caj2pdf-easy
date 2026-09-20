"""Repair PDFs produced by the CAJ converter.

Prefers PyMuPDF (bundled with the app) so Windows and macOS do not need a
system `mutool` binary. Falls back to `mutool` and finally a plain copy.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def repair_pdf(src: str, dst: str) -> None:
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
            return
    except Exception as exc:
        errors.append(f"pymupdf: {exc}")

    mutool = shutil.which("mutool")
    if mutool:
        try:
            subprocess.check_output([mutool, "clean", src, dst], stderr=subprocess.STDOUT)
            if Path(dst).exists() and Path(dst).stat().st_size > 0:
                return
        except Exception as exc:
            errors.append(f"mutool: {exc}")

    shutil.copyfile(src, dst)
    if errors:
        print("PDF repair fallback copy:", "; ".join(errors))
