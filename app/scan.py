"""Detect scans, rasterize unselectable PDFs, and OCR them with Tesseract."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

SCAN_DPI = 170
OCR_DPI = 200
TEXT_CHARS_PER_PAGE = 25
CJK_CHARS_PER_PAGE = 8
GARBLED_RATIO = 0.30
OCR_MIN_CONF = 40.0


@dataclass
class PdfAnalysis:
    pages: int = 0
    text_pages: int = 0
    image_pages: int = 0
    text_chars: int = 0
    cjk_chars: int = 0
    garbled_chars: int = 0
    selectable: bool = False
    is_scan: bool = False
    already_image_pdf: bool = False
    needs_rasterize: bool = False
    ocr_applied: bool = False
    label: str = ""

    @property
    def kind(self) -> str:
        if self.ocr_applied:
            return "ocr"
        if self.selectable:
            return "text"
        if self.is_scan or self.needs_rasterize or self.already_image_pdf:
            return "scan"
        return "unknown"


def _is_garbled_char(ch: str) -> bool:
    code = ord(ch)
    return (
        ch == "\ufffd"
        or 0xE000 <= code <= 0xF8FF
        or 0xF0000 <= code <= 0xFFFFD
        or 0x100000 <= code <= 0x10FFFD
    )


def analyze_pdf(path: Path | str) -> PdfAnalysis:
    import pymupdf

    path = Path(path)
    info = PdfAnalysis()
    doc = pymupdf.open(path)
    try:
        info.pages = doc.page_count
        if info.pages <= 0:
            info.label = "空 PDF"
            return info
        for page in doc:
            text = page.get_text("text") or ""
            cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
            garbled = sum(1 for ch in text if _is_garbled_char(ch))
            info.text_chars += len(text)
            info.cjk_chars += cjk
            info.garbled_chars += garbled
            images = page.get_images() or []
            if images:
                info.image_pages += 1
            meaningful = cjk >= CJK_CHARS_PER_PAGE or len(text.strip()) >= TEXT_CHARS_PER_PAGE
            if meaningful and garbled <= max(8, int(0.2 * max(len(text), 1))):
                info.text_pages += 1
        pages = max(info.pages, 1)
        garbled_ratio = info.garbled_chars / max(info.text_chars, 1)
        info.selectable = (
            info.text_pages >= max(1, int(pages * 0.4))
            and garbled_ratio < GARBLED_RATIO
            and (info.cjk_chars >= pages * CJK_CHARS_PER_PAGE or info.text_chars >= pages * TEXT_CHARS_PER_PAGE)
        )
        info.already_image_pdf = info.image_pages >= max(1, int(pages * 0.8)) and info.text_pages == 0
        has_visual = info.image_pages > 0
        if not has_visual:
            try:
                pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(0.15, 0.15), colorspace=pymupdf.csGRAY)
                has_visual = not bool(pix.is_unicolor)
            except Exception:
                has_visual = False
        info.is_scan = (not info.selectable) and (
            info.already_image_pdf or (info.image_pages > 0 and info.text_pages == 0)
        )
        info.needs_rasterize = (not info.selectable) and has_visual and not info.already_image_pdf
        if info.selectable:
            info.label = "可复制文字"
        elif info.is_scan or info.needs_rasterize:
            info.label = "扫描件，无法选中文字"
        else:
            info.label = "无法选中文字"
        return info
    finally:
        doc.close()


def rasterize_to_scan(src: Path | str, dst: Path | str, dpi: int = SCAN_DPI) -> None:
    """Render each page to an image and write a picture-only PDF."""
    import pymupdf

    src = Path(src)
    dst = Path(dst)
    zoom = max(dpi, 72) / 72.0
    matrix = pymupdf.Matrix(zoom, zoom)
    tmp = dst.with_name(dst.name + ".scan-tmp.pdf")
    src_doc = pymupdf.open(src)
    out_doc = pymupdf.open()
    try:
        for page in src_doc:
            pix = page.get_pixmap(matrix=matrix, alpha=False, colorspace=pymupdf.csRGB)
            try:
                image = pix.tobytes("jpeg")
            finally:
                pix = None
            new_page = out_doc.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(new_page.rect, stream=image)
        dst.parent.mkdir(parents=True, exist_ok=True)
        out_doc.save(str(tmp), deflate=True, garbage=4)
    finally:
        out_doc.close()
        src_doc.close()
    tmp.replace(dst)


def tesseract_cmd() -> str | None:
    return shutil.which("tesseract")


def tesseract_languages() -> str:
    cmd = tesseract_cmd()
    if not cmd:
        return ""
    try:
        out = subprocess.check_output([cmd, "--list-langs"], text=True, errors="ignore", stderr=subprocess.STDOUT)
    except (OSError, subprocess.CalledProcessError):
        return ""
    available = {line.strip() for line in out.splitlines() if line.strip() and " " not in line}
    parts: list[str] = []
    if "chi_sim" in available:
        parts.append("chi_sim")
    if "eng" in available:
        parts.append("eng")
    return "+".join(parts)


def tesseract_install_message() -> str:
    import sys

    if sys.platform == "win32":
        extra = "Windows：安装 Tesseract（UB Mannheim 安装包），安装时勾选 Chinese Simplified。"
    elif sys.platform == "darwin":
        extra = "macOS：在终端运行 brew install tesseract tesseract-lang"
    else:
        extra = "Linux：安装 tesseract-ocr 和 tesseract-ocr-chi-sim（Debian/Ubuntu 可用 apt）。"
    return (
        "没有找到文字识别程序 Tesseract，所以没法识别扫描件上的字。\n"
        f"{extra}\n"
        "装好后重新打开本工具即可。"
    )


def _page_needs_ocr(text: str) -> bool:
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return cjk < CJK_CHARS_PER_PAGE and len(text.strip()) < TEXT_CHARS_PER_PAGE


def _tesseract_tsv(image: Path, lang: str) -> str:
    cmd = tesseract_cmd()
    if not cmd:
        raise FileNotFoundError("未找到 tesseract")
    result = subprocess.run(
        [cmd, str(image), "stdout", "-l", lang, "--oem", "1", "--psm", "3", "tsv"],
        capture_output=True,
        timeout=90,
        check=False,
    )
    if result.returncode != 0:
        err = (result.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(err or f"tesseract 退出码 {result.returncode}")
    return (result.stdout or b"").decode("utf-8", errors="replace")


def _iter_ocr_words(tsv: str, page_width: float, page_height: float, pix_w: int, pix_h: int):
    scale_x = page_width / max(pix_w, 1)
    scale_y = page_height / max(pix_h, 1)
    lines = tsv.splitlines()
    if not lines:
        return
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) < 12:
            continue
        try:
            level = int(parts[0])
            left = float(parts[6])
            top = float(parts[7])
            width = float(parts[8])
            height = float(parts[9])
            conf = float(parts[10])
        except ValueError:
            continue
        text = parts[11].strip()
        if level != 5 or conf < OCR_MIN_CONF or not text:
            continue
        fontsize = max(4.0, min(height * scale_y, 72.0))
        x = left * scale_x
        y = (top + height) * scale_y
        if y > page_height - 1:
            y = page_height - 1
        yield x, y, fontsize, text


def ocr_pdf(path: Path | str, lang: str | None = None, dpi: int = OCR_DPI, progress=None) -> int:
    """Add an invisible text layer. Returns the number of pages that received OCR."""
    import pymupdf

    path = Path(path)
    lang = lang or tesseract_languages()
    if not lang:
        raise FileNotFoundError("没有可用的 Tesseract 语言包（需要 chi_sim 或 eng）")

    doc = pymupdf.open(path)
    ocr_pages = 0
    font = pymupdf.Font("cjk")
    zoom = max(dpi, 72) / 72.0
    matrix = pymupdf.Matrix(zoom, zoom)
    tmp_pdf = path.with_name(path.name + ".ocr-tmp.pdf")
    try:
        with tempfile.TemporaryDirectory(prefix="caj2pdf-ocr-") as tmp:
            tmpdir = Path(tmp)
            total = doc.page_count
            for index, page in enumerate(doc):
                if progress is not None:
                    try:
                        progress(index + 1, total)
                    except Exception:
                        pass
                existing = page.get_text("text") or ""
                if not _page_needs_ocr(existing):
                    continue
                pix = page.get_pixmap(matrix=matrix, alpha=False, colorspace=pymupdf.csRGB)
                image_path = tmpdir / f"page-{index:04d}.png"
                pix.save(image_path)
                pix_w, pix_h = pix.width, pix.height
                pix = None
                try:
                    tsv = _tesseract_tsv(image_path, lang)
                except Exception:
                    continue
                words = list(_iter_ocr_words(tsv, page.rect.width, page.rect.height, pix_w, pix_h))
                if not words:
                    continue
                writer = pymupdf.TextWriter(page.rect)
                for x, y, fontsize, word in words:
                    writer.append((x, y), word, font=font, fontsize=fontsize)
                writer.write_text(page, render_mode=3, overlay=True)
                ocr_pages += 1
        if ocr_pages == 0:
            return 0
        try:
            doc.subset_fonts()
        except Exception:
            pass
        doc.save(str(tmp_pdf), deflate=True, garbage=4)
    finally:
        doc.close()
    tmp_pdf.replace(path)
    return ocr_pages


def ensure_scan_if_unselectable(path: Path | str) -> tuple[PdfAnalysis, bool]:
    analysis, rasterized, _ocr_done = enhance_pdf(path)
    return analysis, rasterized


def enhance_pdf(path: Path | str, progress=None) -> tuple[PdfAnalysis, bool, bool]:
    """Rasterize if needed, then OCR scans so text can be selected.

    Returns (analysis, rasterized, ocr_done).
    """
    path = Path(path)
    analysis = analyze_pdf(path)
    rasterized = False
    ocr_done = False
    if analysis.selectable:
        return analysis, False, False
    if analysis.needs_rasterize:
        rasterize_to_scan(path, path)
        rasterized = True
        analysis = analyze_pdf(path)
    lang = tesseract_languages()
    if lang:
        try:
            ocr_pages = ocr_pdf(path, lang=lang, progress=progress)
            if ocr_pages:
                ocr_done = True
                analysis = analyze_pdf(path)
                analysis.ocr_applied = True
                if analysis.selectable or analysis.cjk_chars >= 40:
                    analysis.label = "扫描件，已识别文字，可复制"
                else:
                    analysis.label = "扫描件，识别到的文字较少"
                    ocr_done = analysis.cjk_chars > 0
            else:
                analysis = analyze_pdf(path)
        except Exception:
            analysis = analyze_pdf(path)
    if not ocr_done and (analysis.is_scan or rasterized):
        analysis.is_scan = True
        if lang:
            analysis.label = "扫描件，无法选中文字"
        else:
            analysis.label = "扫描件，无法选中文字（安装 Tesseract 中文包后可识别）"
    return analysis, rasterized, ocr_done
