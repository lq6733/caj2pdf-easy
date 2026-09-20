"""Self-test conversion quality without overwriting the original files."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from app.engine import ConvertResult, collect_files, convert_file, detect_format, extract_hn_text

GRADE_ACCURATE = "准确"
GRADE_PARTIAL = "部分可用"
GRADE_FAIL = "失败"


@dataclass
class FileReport:
    source: Path
    format_code: str
    format_name: str
    grade: str
    convert_ok: bool
    fallback: bool
    pdf_ok: bool
    expected_pages: int | None
    actual_pages: int | None
    empty_pages: int
    image_pages: int
    text_chars: int
    cjk_chars: int
    similarity: float | None = None
    notes: list[str] = field(default_factory=list)
    message: str = ""
    output: Path | None = None


def _safe_format(source: Path) -> str:
    try:
        return detect_format(source) or "未知"
    except Exception:
        return "未知"


def _expected_pages(source: Path, format_code: str) -> int | None:
    if format_code == "PDF":
        try:
            import pymupdf

            doc = pymupdf.open(source)
            try:
                return doc.page_count
            finally:
                doc.close()
        except Exception:
            return None
    if format_code in {"CAJ", "HN", "C8"}:
        try:
            from app.engine import VENDOR
            import sys

            vendor = str(VENDOR)
            if vendor not in sys.path:
                sys.path.insert(0, vendor)
            from cajparser import CAJParser

            return CAJParser(str(source)).page_num
        except Exception:
            return None
    return None


def _inspect_pdf(path: Path) -> dict:
    import pymupdf

    doc = pymupdf.open(path)
    try:
        empty = 0
        image_pages = 0
        text_chars = 0
        cjk_chars = 0
        page_texts: list[str] = []
        for page in doc:
            text = page.get_text("text") or ""
            page_texts.append(text)
            text_chars += len(text)
            cjk_chars += sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
            images = page.get_images() or []
            if images:
                image_pages += 1
            blank = False
            if len(text.strip()) < 8 and not images:
                try:
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(0.2, 0.2), colorspace=pymupdf.csGRAY)
                    blank = bool(pix.is_unicolor)
                except Exception:
                    blank = True
            if blank:
                empty += 1
        return {
            "pages": doc.page_count,
            "empty": empty,
            "image_pages": image_pages,
            "text_chars": text_chars,
            "cjk_chars": cjk_chars,
            "text": "\n".join(page_texts),
            "toc": len(doc.get_toc() or []),
        }
    finally:
        doc.close()


def _pdf_source_text(source: Path) -> str:
    import pymupdf

    doc = pymupdf.open(source)
    try:
        return "\n".join(page.get_text("text") or "" for page in doc)
    finally:
        doc.close()


def _norm_text(text: str) -> str:
    return "".join(text.split())


def _similarity(left: str, right: str) -> float:
    a = _norm_text(left)
    b = _norm_text(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    # Long papers: compare a stable prefix plus lengths to keep this cheap.
    limit = 80000
    return SequenceMatcher(None, a[:limit], b[:limit]).ratio()


def evaluate_conversion(source: Path, result: ConvertResult) -> FileReport:
    format_code = _safe_format(source)
    expected = _expected_pages(source, format_code)
    notes: list[str] = []
    report = FileReport(
        source=source,
        format_code=format_code,
        format_name=result.format_name or format_code,
        grade=GRADE_FAIL,
        convert_ok=result.ok,
        fallback=result.fallback,
        pdf_ok=False,
        expected_pages=expected,
        actual_pages=None,
        empty_pages=0,
        image_pages=0,
        text_chars=0,
        cjk_chars=0,
        notes=notes,
        message=result.message,
        output=result.output,
    )
    if not result.ok or result.output is None or not result.output.exists():
        notes.append(result.message or "转换失败")
        return report

    try:
        info = _inspect_pdf(result.output)
    except Exception as exc:
        notes.append(f"生成的 PDF 打不开：{exc}")
        return report

    report.pdf_ok = True
    report.actual_pages = info["pages"]
    report.empty_pages = info["empty"]
    report.image_pages = info["image_pages"]
    report.text_chars = info["text_chars"]
    report.cjk_chars = info["cjk_chars"]

    if info["pages"] <= 0:
        notes.append("PDF 页数为 0")
        return report

    if result.fallback:
        notes.append("未能保留原版面，只用抽出的文字生成了文字版 PDF")
        try:
            extracted = extract_hn_text(source)
            if extracted:
                report.similarity = _similarity(extracted, info["text"])
                if report.similarity < 0.5:
                    notes.append(f"文字版和抽出正文相似度偏低（{report.similarity:.0%}）")
        except Exception:
            pass
        report.grade = GRADE_PARTIAL
        return report

    if expected is not None and info["pages"] != expected:
        notes.append(f"页数不一致：源文件 {expected} 页，PDF {info['pages']} 页")

    empty_ratio = info["empty"] / max(info["pages"], 1)
    if info["empty"]:
        notes.append(f"空白页 {info['empty']}/{info['pages']}")

    if format_code == "PDF":
        try:
            original = _pdf_source_text(source)
            report.similarity = _similarity(original, info["text"])
            if report.similarity < 0.95:
                notes.append(f"和原 PDF 文字不一致（相似度 {report.similarity:.0%}）")
        except Exception as exc:
            notes.append(f"无法对照原 PDF 文字：{exc}")

    if format_code in {"HN", "C8"} and info["image_pages"] == 0 and info["cjk_chars"] < 80:
        notes.append("扫描页既没有图片也几乎没有文字")

    if format_code in {"CAJ", "KDH", "PDF"} and info["text_chars"] < 40 and info["image_pages"] == 0:
        notes.append("页面里几乎没有文字或图片")

    mismatch = expected is not None and info["pages"] != expected
    mostly_blank = empty_ratio > 0.1
    weak_content = (
        info["text_chars"] < 40
        and info["image_pages"] == 0
        and format_code != "PDF"
    )
    weak_pdf_text = format_code == "PDF" and (report.similarity is not None and report.similarity < 0.95)

    if mismatch or mostly_blank or weak_content or weak_pdf_text:
        report.grade = GRADE_PARTIAL
        return report

    report.grade = GRADE_ACCURATE
    if not notes:
        notes.append("能打开，页数一致，页面有内容")
    return report


def _unique_dest(out_dir: Path, source: Path, used: set[str]) -> Path:
    base = source.stem + ".pdf"
    name = base
    i = 2
    while name.lower() in used:
        name = f"{source.stem}-{i}.pdf"
        i += 1
    used.add(name.lower())
    return out_dir / name


def run_selftest(paths: list[Path], out_dir: Path | None = None) -> int:
    files = collect_files(paths)
    if not files:
        print("没有找到可以自测的 CAJ/KDH 文件。请加上文件或文件夹路径。")
        return 1

    if out_dir is None:
        out_dir = Path(tempfile.mkdtemp(prefix="caj2pdf-selftest-"))
    else:
        out_dir = Path(out_dir).expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

    print(f"自测 {len(files)} 个文件。转换结果写到：{out_dir}")
    print("说明：没有官方 PDF 时，准确率指结构一致性（能打开、页数相符、页面非空）。")
    print("      后缀是 .caj 但内容已是 PDF 的文件，会和原文逐页对文字。")
    print()

    used_names: set[str] = set()
    reports: list[FileReport] = []
    for index, source in enumerate(files, start=1):
        dest = _unique_dest(out_dir, source, used_names)
        print(f"[{index}/{len(files)}] {source.name}")
        result = convert_file(source, dest)
        report = evaluate_conversion(source, result)
        reports.append(report)
        extra = f"  {report.actual_pages}页" if report.actual_pages else ""
        print(f"    {report.grade}  {report.format_code}{extra}  {report.notes[0] if report.notes else report.message}")

    print()
    print("结果明细")
    print("-" * 78)
    for report in reports:
        pages = "?"
        if report.actual_pages is not None:
            if report.expected_pages is not None:
                pages = f"{report.actual_pages}/{report.expected_pages}"
            else:
                pages = str(report.actual_pages)
        print(f"{report.grade:6}  {report.format_code:4}  {pages:>7}  {report.source.name}")
        for note in report.notes:
            print(f"              {note}")

    total = len(reports)
    accurate = sum(1 for r in reports if r.grade == GRADE_ACCURATE)
    partial = sum(1 for r in reports if r.grade == GRADE_PARTIAL)
    failed = sum(1 for r in reports if r.grade == GRADE_FAIL)
    converted = sum(1 for r in reports if r.convert_ok and r.pdf_ok)

    print()
    print("汇总")
    print("-" * 78)
    print(f"文件总数     {total}")
    print(f"转换成功     {converted}/{total}  ({converted / total:.1%})")
    print(f"结构准确     {accurate}/{total}  ({accurate / total:.1%})")
    print(f"部分可用     {partial}/{total}  ({partial / total:.1%})")
    print(f"失败         {failed}/{total}  ({failed / total:.1%})")

    by_fmt: dict[str, list[FileReport]] = {}
    for report in reports:
        by_fmt.setdefault(report.format_code, []).append(report)
    print()
    print("按格式")
    for fmt, items in sorted(by_fmt.items()):
        ok = sum(1 for r in items if r.grade == GRADE_ACCURATE)
        print(f"  {fmt:4}  准确 {ok}/{len(items)}  部分 {sum(1 for r in items if r.grade == GRADE_PARTIAL)}  失败 {sum(1 for r in items if r.grade == GRADE_FAIL)}")

    print()
    print(f"生成的 PDF 在：{out_dir}")
    print("没有改你原来的 CAJ 文件，也没有覆盖它们旁边可能已有的 PDF。")
    return 0 if failed == 0 else 1
