"""Detect image-only PDFs and rasterize files whose text cannot be selected."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SCAN_DPI = 170
TEXT_CHARS_PER_PAGE = 25
CJK_CHARS_PER_PAGE = 8
GARBLED_RATIO = 0.30


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
    label: str = ""

    @property
    def kind(self) -> str:
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
            # Cheap visual check on the first page: not a blank unicolor page.
            try:
                pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(0.15, 0.15), colorspace=pymupdf.csGRAY)
                has_visual = not bool(pix.is_unicolor)
            except Exception:
                has_visual = False
        info.is_scan = (not info.selectable) and (info.already_image_pdf or (info.image_pages > 0 and info.text_pages == 0))
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


def ensure_scan_if_unselectable(path: Path | str) -> tuple[PdfAnalysis, bool]:
    """If the PDF has no usable selectable text, convert it to a scanned PDF.

    Returns (analysis_after, rasterized).
    """
    path = Path(path)
    analysis = analyze_pdf(path)
    if not analysis.needs_rasterize:
        return analysis, False
    rasterize_to_scan(path, path)
    after = analyze_pdf(path)
    after.needs_rasterize = False
    after.is_scan = True
    after.label = "扫描件，无法选中文字"
    return after, True
