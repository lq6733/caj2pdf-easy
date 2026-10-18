"""Build and locate the app icon used by the window and desktop shortcuts."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARE = ROOT / "share"
PNG_PATH = SHARE / "caj2pdf-easy.png"
ICO_PATH = SHARE / "caj2pdf-easy.ico"
ICNS_PATH = SHARE / "caj2pdf-easy.icns"


def _rounded_rect(draw, box, radius, fill) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def _load_font(size: int):
    from PIL import ImageFont

    candidates = (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansSC-Bold.otf",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/segoeuib.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_icon(size: int = 1024):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s = size / 128.0

    def box(x, y, w, h):
        return (round(x * s), round(y * s), round((x + w) * s), round((y + h) * s))

    _rounded_rect(draw, box(8, 8, 112, 112), round(24 * s), "#1f6feb")
    _rounded_rect(draw, box(28, 24, 52, 68), round(6 * s), "#ffffff")
    draw.polygon(
        [
            (round(64 * s), round(24 * s)),
            (round(80 * s), round(24 * s)),
            (round(80 * s), round(40 * s)),
        ],
        fill="#d8e4ff",
    )
    font_caj = _load_font(max(12, round(15 * s)))
    font_pdf = _load_font(max(10, round(12 * s)))
    draw.text((round(38 * s), round(50 * s)), "CAJ", fill="#1f6feb", font=font_caj)
    draw.polygon(
        [
            (round(86 * s), round(58 * s)),
            (round(104 * s), round(58 * s)),
            (round(104 * s), round(52 * s)),
            (round(118 * s), round(64 * s)),
            (round(104 * s), round(76 * s)),
            (round(104 * s), round(70 * s)),
            (round(86 * s), round(70 * s)),
        ],
        fill="#ffd166",
    )
    _rounded_rect(draw, box(78, 82, 28, 22), round(5 * s), "#ffffff")
    draw.text((round(82 * s), round(85 * s)), "PDF", fill="#1f6feb", font=font_pdf)
    return img


def ensure_icons() -> tuple[Path, Path, Path]:
    SHARE.mkdir(parents=True, exist_ok=True)
    master = render_icon(1024)
    png = master.resize((256, 256))
    if not PNG_PATH.is_file() or PNG_PATH.stat().st_size < 1000:
        png.save(PNG_PATH, format="PNG")
    if not ICO_PATH.is_file() or ICO_PATH.stat().st_size < 2000:
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        png.save(ICO_PATH, format="ICO", sizes=sizes)
    if not ICNS_PATH.is_file() or ICNS_PATH.stat().st_size < 1000:
        try:
            master.save(ICNS_PATH, format="ICNS")
        except Exception:
            pass
    return PNG_PATH, ICO_PATH, ICNS_PATH


if __name__ == "__main__":
    png, ico, icns = ensure_icons()
    print(png, png.stat().st_size if png.is_file() else 0)
    print(ico, ico.stat().st_size if ico.is_file() else 0)
    print(icns, icns.stat().st_size if icns.is_file() else 0)
