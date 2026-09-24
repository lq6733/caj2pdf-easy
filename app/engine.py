#!/usr/bin/env python3
"""Wrap caj2pdf so the GUI can convert files with friendly Chinese errors."""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import sys
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "caj2pdf"

SUPPORTED_SUFFIXES = {".caj", ".kdh", ".nh", ".hn", ".c8"}

FORMAT_NAMES = {
    "CAJ": "知网 CAJ",
    "HN": "知网 HN",
    "KDH": "知网 KDH",
    "PDF": "假后缀 PDF（文件本身已经是 PDF）",
    "C8": "知网 C8（较新格式）",
}

FRIENDLY_ERRORS = (
    ("pure-text HN", "这个文件几乎是纯文字，当前方法没法直接生成 PDF。"),
    ("Unknown Image Type", "文件里的图片格式还不支持。"),
    ("unusual image offset", "这个文件结构比较特殊，转换失败了。"),
    ("%%EOF mark can't be found", "文件可能不完整或已损坏。"),
    ("Unknown file type", "这不是能识别的 CAJ/KDH 文件。"),
    ("Unsupported file type", "这种格式还不支持。"),
    ("File is pure-text HN", "这个文件几乎是纯文字，当前方法没法直接生成 PDF。"),
)


KIND_LABELS = {
    "text": "可复制文字",
    "scan": "扫描件，无法选中文字",
    "ocr": "扫描件，已识别文字，可复制",
    "fallback": "文字版（版面已简化）",
}


@dataclass
class ConvertResult:
    source: Path
    output: Path | None
    ok: bool
    format_name: str
    message: str
    detail: str = ""
    fallback: bool = False
    kind: str = ""
    skipped: bool = False


def is_supported_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES


def is_pdf_file(path: Path) -> bool:
    if not path.is_file() or path.suffix.lower() != ".pdf":
        return False
    name = path.name.lower()
    return not (name.endswith(".ocr-tmp.pdf") or name.endswith(".scan-tmp.pdf"))


def _collect_matching(paths: list[Path], predicate) -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    for raw in paths:
        path = Path(raw).expanduser()
        try:
            path = path.resolve()
        except OSError:
            continue
        if path in seen:
            continue
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if predicate(child):
                    resolved = child.resolve()
                    if resolved not in seen:
                        seen.add(resolved)
                        found.append(resolved)
        elif predicate(path):
            seen.add(path)
            found.append(path)
    return found


def collect_files(paths: list[Path]) -> list[Path]:
    return _collect_matching(paths, is_supported_file)


def collect_pdfs(paths: list[Path]) -> list[Path]:
    return _collect_matching(paths, is_pdf_file)


def default_output_for(source: Path) -> Path:
    return source.with_suffix(".pdf")


OCR_NAME_SUFFIX = "-已识别"


def default_ocr_output_for(source: Path) -> Path:
    source = Path(source)
    stem = source.stem
    if stem.endswith(OCR_NAME_SUFFIX):
        return source
    return source.with_name(stem + OCR_NAME_SUFFIX + ".pdf")


def _ensure_vendor_path() -> None:
    vendor = str(VENDOR)
    if vendor not in sys.path:
        sys.path.insert(0, vendor)


def detect_format(source: Path) -> str:
    _ensure_vendor_path()
    from cajparser import CAJParser

    parser = CAJParser(str(source))
    return getattr(parser, "format", "未知")


def _friendly_error(exc: BaseException, lib_detail: str = "") -> str:
    text = str(exc).strip() or exc.__class__.__name__
    if isinstance(exc, SystemExit):
        if isinstance(exc.code, int):
            text = f"转换程序异常退出（代码 {exc.code}）"
        else:
            text = str(exc.code or "转换失败")
    if "找不到解码库" in text:
        from app.build_native import library_help

        return library_help(lib_detail)
    for needle, message in FRIENDLY_ERRORS:
        if needle.lower() in text.lower():
            return message
    if "mutool" in text.lower() or "pymupdf" in text.lower():
        return "PDF 修复步骤失败。这个文件生成的 PDF 可能不完整。"
    if len(text) > 160:
        text = text[:157] + "…"
    return f"转换失败：{text}"


@contextlib.contextmanager
def _work_directory() -> str:
    work = tempfile.mkdtemp(prefix="caj2pdf-")
    old = os.getcwd()
    try:
        os.chdir(work)
        yield work
    finally:
        os.chdir(old)
        shutil.rmtree(work, ignore_errors=True)



def extract_hn_text(source: Path) -> str:
    _ensure_vendor_path()
    from cajparser import CAJParser
    from HNParsePage import HNParsePage
    import struct
    import zlib

    parser = CAJParser(str(source))
    if parser.format not in {"HN", "C8"}:
        return ""
    pages: list[str] = []
    file_size = source.stat().st_size
    with open(source, "rb") as caj:
        for i in range(parser.page_num):
            rec_pos = parser._TOC_END_OFFSET + i * 20
            if rec_pos + 20 > file_size:
                break
            caj.seek(rec_pos)
            page_data_offset, size_of_text_section, images_per_page, page_no, unk2, next_page_data_offset = struct.unpack(
                "iihhii", caj.read(20)
            )
            if page_data_offset < 0 or size_of_text_section <= 0 or page_data_offset + size_of_text_section > file_size:
                continue
            caj.seek(page_data_offset)
            header = caj.read(32)
            try:
                if header[8:20] == b"COMPRESSTEXT" or header[0:12] == b"COMPRESSTEXT":
                    coff = 0 if header[0:12] == b"COMPRESSTEXT" else 8
                    (expanded_text_size,) = struct.unpack("i", header[12 + coff:16 + coff])
                    caj.seek(page_data_offset + 16 + coff)
                    data = caj.read(size_of_text_section - 16 - coff)
                    output = zlib.decompress(data)
                else:
                    caj.seek(page_data_offset)
                    output = caj.read(size_of_text_section)
            except Exception:
                continue
            page_style = next_page_data_offset > page_data_offset
            parsed = HNParsePage(output, page_style)
            text = parsed.texts.replace("\x00", "").strip()
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            text = "\n".join(lines)
            if text:
                pages.append(text)
    return "\n\n".join(pages).strip()


def _wrap_by_width(line: str, size: float, max_w: float, measure) -> list[str]:
    if not line:
        return [""]
    lines: list[str] = []
    buf = ""
    for ch in line:
        trial = buf + ch
        if measure(trial, size) <= max_w:
            buf = trial
        else:
            if buf:
                lines.append(buf)
            buf = ch
    if buf:
        lines.append(buf)
    return lines or [""]


def _write_text_pdf_pymupdf(text: str, dest: Path, title: str = "") -> None:
    import pymupdf

    font = pymupdf.Font("cjk")
    width, height = 595.0, 842.0
    margin = 48.0
    max_w = width - 2 * margin

    def measure(s: str, size: float) -> float:
        return font.text_length(s, fontsize=size)

    items: list[tuple[str, float, float]] = []
    if title:
        for line in _wrap_by_width(title, 16, max_w, measure):
            items.append((line, 16, 24))
        items.append(("", 12, 10))
    for para in text.split("\n"):
        for line in _wrap_by_width(para, 12, max_w, measure):
            items.append((line, 12, 18))

    doc = pymupdf.open()
    page = None
    writer = None
    y = 0.0

    def new_page() -> None:
        nonlocal page, writer, y
        if page is not None and writer is not None:
            writer.write_text(page)
        page = doc.new_page(width=width, height=height)
        writer = pymupdf.TextWriter(page.rect)
        y = margin + 18

    new_page()
    assert page is not None and writer is not None
    for line, size, step in items:
        if y > height - margin:
            new_page()
        if line:
            writer.append((margin, y), line, font=font, fontsize=size)
        y += step
    writer.write_text(page)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        doc.subset_fonts()
    except Exception:
        pass
    doc.save(str(dest))
    doc.close()


def _write_text_pdf_cairo(text: str, dest: Path, title: str = "") -> None:
    import cairo

    dest.parent.mkdir(parents=True, exist_ok=True)
    width, height = 595.0, 842.0
    margin = 48.0
    max_w = width - 2 * margin
    surface = cairo.PDFSurface(str(dest), width, height)
    ctx = cairo.Context(surface)
    ctx.select_font_face("Noto Serif CJK SC", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    ctx.set_source_rgb(0, 0, 0)

    def measure(s: str, size: float) -> float:
        ctx.set_font_size(size)
        return ctx.text_extents(s).x_advance

    def draw(y: float, line: str, size: float) -> None:
        ctx.set_font_size(size)
        ctx.move_to(margin, y)
        ctx.show_text(line)

    y = margin + 18
    if title:
        for line in _wrap_by_width(title, 16, max_w, measure):
            if y > height - margin:
                ctx.show_page()
                y = margin + 18
            draw(y, line, 16)
            y += 24
        y += 10
    for para in text.split("\n"):
        for line in _wrap_by_width(para, 12, max_w, measure):
            if y > height - margin:
                ctx.show_page()
                y = margin + 18
            draw(y, line, 12)
            y += 18
    surface.finish()


def write_text_pdf(text: str, dest: Path, title: str = "") -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    try:
        _write_text_pdf_pymupdf(text, dest, title)
        if dest.exists() and dest.stat().st_size > 32:
            return
    except Exception as exc:
        errors.append(f"pymupdf: {exc}")
    try:
        _write_text_pdf_cairo(text, dest, title)
        if dest.exists() and dest.stat().st_size > 32:
            return
    except Exception as exc:
        errors.append(f"cairo: {exc}")
    raise RuntimeError("无法生成文字版 PDF：" + "; ".join(errors))


def _try_text_pdf_fallback(source, output, format_name, exc, detail, tb) -> ConvertResult | None:
    try:
        text = extract_hn_text(source)
    except Exception:
        return None
    from app.scan import text_is_readable

    if not text_is_readable(text, min_cjk=80, min_letters=120):
        return None
    try:
        write_text_pdf(text, output, title=source.stem)
    except Exception:
        return None
    if not output.exists() or output.stat().st_size < 32:
        return None
    extra = "这个文件没法保留原来的版面，已经转成可阅读的文字版 PDF。"
    return ConvertResult(
        source=source,
        output=output,
        ok=True,
        format_name=format_name or "文字版",
        message=extra + f" 已保存为：{output.name}",
        detail="\n".join(x for x in (detail, tb) if x).strip(),
        fallback=True,
        kind="fallback",
    )


def convert_file(source: Path, output: Path | None = None, progress=None) -> ConvertResult:
    source = Path(source).expanduser().resolve()
    output = Path(output).expanduser().resolve() if output else default_output_for(source)
    if not source.exists():
        return ConvertResult(source, None, False, "未知", "找不到这个文件。可能被移动或删除了。")
    if not is_supported_file(source):
        return ConvertResult(source, None, False, "未知", "只支持 CAJ、KDH、NH 这些知网下载的文件。")

    _ensure_vendor_path()
    lib_detail = ""
    try:
        from app.build_native import ensure_libraries

        _ok, lib_detail = ensure_libraries()
    except Exception as exc:
        lib_detail = str(exc)
    log = io.StringIO()
    format_name = "未知"
    try:
        with _work_directory(), contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            from cajparser import CAJParser

            parser = CAJParser(str(source))
            format_name = FORMAT_NAMES.get(parser.format, parser.format or "未知")
            output.parent.mkdir(parents=True, exist_ok=True)
            parser.convert(str(output))
    except BaseException as exc:
        detail = log.getvalue().strip()
        tb = traceback.format_exc()
        fallback = _try_text_pdf_fallback(source, output, format_name, exc, detail, tb)
        if fallback is not None:
            return fallback
        return ConvertResult(
            source=source,
            output=None,
            ok=False,
            format_name=format_name,
            message=_friendly_error(exc, lib_detail),
            detail="\n".join(x for x in (detail, tb) if x).strip(),
        )

    if not output.exists() or output.stat().st_size < 32:
        fallback = _try_text_pdf_fallback(source, output, format_name, None, log.getvalue().strip(), "")
        if fallback is not None:
            return fallback
        return ConvertResult(
            source,
            output if output.exists() else None,
            False,
            format_name,
            "转换过程没有生成可用的 PDF。",
            log.getvalue().strip(),
        )

    extra = ""
    if format_name.startswith("假后缀"):
        extra = "这个文件其实已经是 PDF，已按 PDF 复制出来。"
    elif format_name.endswith("较新格式）"):
        extra = "已尝试按较新格式转换。"

    kind = "text"
    try:
        from app.scan import enhance_pdf, tesseract_languages

        analysis, rasterized, ocr_done = enhance_pdf(output, progress=progress)
        kind = "ocr" if ocr_done else (analysis.kind or "text")
        bits: list[str] = []
        if extra:
            bits.append(extra.strip())
        if rasterized:
            bits.append("已检测为无法选中文字，已自动转为扫描件。")
        if ocr_done:
            bits.append("已用 Tesseract 识别文字，可以搜索和复制（个别字可能不准）。")
        elif kind == "scan":
            if tesseract_languages():
                bits.append("这是扫描件，页面是图片，无法选中文字。")
            else:
                bits.append("这是扫描件，无法选中文字。安装 Tesseract 中文语言包后可自动识别。")
        elif kind == "text":
            bits.append("可以选中和复制文字。")
        extra = " ".join(bits)
    except Exception as exc:
        extra = (extra + " " if extra else "") + f"文字/扫描件检测失败：{exc}"

    message = f"成功，已保存为：{output.name}"
    if extra:
        message = extra + " " + message
    return ConvertResult(
        source=source,
        output=output,
        ok=True,
        format_name=format_name,
        message=message,
        detail=log.getvalue().strip(),
        kind=kind,
    )



def ocr_image_pdf(source: Path, output: Path | None = None, progress=None) -> ConvertResult:
    """OCR an existing image-only PDF. Never overwrites the original unless it is already *-已识别.pdf."""
    source = Path(source).expanduser().resolve()
    dest = Path(output).expanduser().resolve() if output else default_ocr_output_for(source)
    if not source.exists():
        return ConvertResult(source, None, False, "PDF", "找不到这个文件。可能被移动或删除了。")
    if source.suffix.lower() != ".pdf":
        return ConvertResult(source, None, False, "PDF", "请选择 PDF 文件。")

    from app.scan import analyze_pdf, enhance_pdf, tesseract_install_message, tesseract_languages

    if not tesseract_languages():
        return ConvertResult(source, None, False, "PDF", tesseract_install_message())

    try:
        import pymupdf

        doc = pymupdf.open(source)
        try:
            if getattr(doc, "needs_pass", False):
                return ConvertResult(source, None, False, "PDF", "这个 PDF 有密码，没法识别。")
            if doc.page_count <= 0:
                return ConvertResult(source, None, False, "PDF", "这个 PDF 是空的。")
        finally:
            doc.close()
        analysis = analyze_pdf(source)
    except Exception as exc:
        return ConvertResult(source, None, False, "PDF", f"打不开这个 PDF：{exc}")

    if analysis.selectable:
        return ConvertResult(
            source=source,
            output=source,
            ok=True,
            format_name="PDF",
            message="这个 PDF 已经可以选中文字，不用再识别。",
            kind="text",
            skipped=True,
        )

    broken_text_layer = (
        analysis.image_pages == 0
        and analysis.garbled_chars >= 80
        and analysis.cjk_chars < max(40, analysis.pages * 20)
    )

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest != source:
            shutil.copy2(source, dest)
    except OSError as exc:
        return ConvertResult(source, None, False, "PDF", f"没法保存识别结果：{exc}")

    try:
        analysis, rasterized, ocr_done = enhance_pdf(dest, progress=progress)
    except Exception as exc:
        return ConvertResult(
            source=source,
            output=dest if dest.exists() else None,
            ok=False,
            format_name="PDF",
            message=f"识别失败：{exc}",
            detail=traceback.format_exc(),
            kind="scan",
        )

    unchanged = dest != source
    if ocr_done:
        extra = "（原来的文件没有改动）" if unchanged else ""
        return ConvertResult(
            source=source,
            output=dest,
            ok=True,
            format_name="PDF",
            message=f"已识别文字，可以搜索和复制（个别字可能不准）。已保存为：{dest.name}{extra}",
            kind="ocr",
        )

    if dest != source and dest.exists() and (broken_text_layer or not rasterized):
        try:
            dest.unlink()
        except OSError:
            pass
    if broken_text_layer:
        return ConvertResult(
            source=source,
            output=None,
            ok=False,
            format_name="PDF",
            message="这个 PDF 里的文字是乱码，页面上看着也是乱码，没法靠识别恢复。请用原始的 CAJ 或清晰扫描件重新转换。",
            kind="scan",
        )
    if rasterized:
        extra = "（原来的文件没有改动）" if unchanged else ""
        return ConvertResult(
            source=source,
            output=dest,
            ok=False,
            format_name="PDF",
            message=f"已另存为扫描件，但没能识别出文字。已保存为：{dest.name}{extra}",
            kind="scan",
        )
    return ConvertResult(
        source=source,
        output=None,
        ok=False,
        format_name="PDF",
        message="没能识别出文字。可能是图片不清晰，或不是中文/英文扫描件。",
        kind="scan",
    )
