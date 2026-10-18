"""Modern ttk theme for the Windows / macOS window."""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk

from app.icon import ICO_PATH, PNG_PATH, ensure_icons

ACCENT = "#1f6feb"
ACCENT_HOVER = "#1558c7"
ACCENT_SOFT = "#eaf2fe"
ACCENT_LINE = "#8bb4f7"
TEXT = "#1f2328"
MUTED = "#656d76"
SUCCESS = "#1a7f37"
DANGER = "#cf222e"
WARN = "#9a6700"
WHITE = "#ffffff"
STRIPE = "#f6f8fa"
BORDER = "#d0d7de"


def palette() -> dict[str, str]:
    if sys.platform == "darwin":
        bg = "#f5f5f7"
    else:
        bg = "#f3f3f3"
    return {
        "bg": bg,
        "card": WHITE,
        "text": TEXT,
        "muted": MUTED,
        "accent": ACCENT,
        "accent_hover": ACCENT_HOVER,
        "accent_soft": ACCENT_SOFT,
        "accent_line": ACCENT_LINE,
        "success": SUCCESS,
        "danger": DANGER,
        "warn": WARN,
        "stripe": STRIPE,
        "border": BORDER,
    }


def ui_fonts() -> dict[str, tuple]:
    if sys.platform == "win32":
        family = "Microsoft YaHei UI"
        return {
            "ui": (family, 10),
            "title": (family, 20, "bold"),
            "subtitle": (family, 10),
            "button": (family, 10),
            "tree": (family, 10),
            "heading": (family, 9),
            "drop": (family, 11),
            "drop_sub": (family, 9),
        }
    if sys.platform == "darwin":
        family = "PingFang SC"
        return {
            "ui": (family, 13),
            "title": (family, 22, "bold"),
            "subtitle": (family, 12),
            "button": (family, 13),
            "tree": (family, 13),
            "heading": (family, 12),
            "drop": (family, 14),
            "drop_sub": (family, 12),
        }
    family = "Noto Sans CJK SC"
    return {
        "ui": (family, 10),
        "title": (family, 18, "bold"),
        "subtitle": (family, 10),
        "button": (family, 10),
        "tree": (family, 10),
        "heading": (family, 9),
        "drop": (family, 11),
        "drop_sub": (family, 9),
    }


def enable_dpi() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("io.github.caj2pdf.easy")
    except Exception:
        pass


def apply_window_icon(root: tk.Tk) -> list:
    photos: list = []
    try:
        ensure_icons()
    except Exception:
        pass
    if sys.platform == "win32" and ICO_PATH.is_file():
        try:
            root.iconbitmap(str(ICO_PATH))
        except tk.TclError:
            pass
    if PNG_PATH.is_file():
        try:
            photo = tk.PhotoImage(file=str(PNG_PATH))
            root.iconphoto(True, photo)
            photos.append(photo)
        except tk.TclError:
            pass
    return photos


def header_icon_photo(size: int = 48):
    try:
        ensure_icons()
        from PIL import Image, ImageTk

        if not PNG_PATH.is_file():
            return None
        img = Image.open(PNG_PATH).convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception:
        return None


def apply_theme(root: tk.Tk) -> dict[str, str]:
    colors = palette()
    fonts = ui_fonts()
    root.configure(bg=colors["bg"])
    try:
        root.option_add("*Font", fonts["ui"])
        root.option_add("*tearOff", False)
    except tk.TclError:
        pass

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    bg = colors["bg"]
    card = colors["card"]
    text = colors["text"]
    muted = colors["muted"]
    accent = colors["accent"]
    hover = colors["accent_hover"]
    border = colors["border"]

    style.configure(".", background=bg, foreground=text, font=fonts["ui"])
    style.configure("TFrame", background=bg)
    style.configure("Card.TFrame", background=card)
    style.configure("TLabel", background=bg, foreground=text, font=fonts["ui"])
    style.configure("Card.TLabel", background=card, foreground=text, font=fonts["ui"])
    style.configure("Title.TLabel", background=bg, foreground=text, font=fonts["title"])
    style.configure("Subtitle.TLabel", background=bg, foreground=muted, font=fonts["subtitle"])
    style.configure("Muted.TLabel", background=bg, foreground=muted, font=fonts["subtitle"])
    style.configure("Heading.TLabel", background=bg, foreground=text, font=fonts["heading"])
    style.configure("Status.TLabel", background=bg, foreground=muted, font=fonts["subtitle"])
    style.configure("Summary.TLabel", background=bg, foreground=text, font=fonts["ui"])

    style.configure(
        "TButton",
        font=fonts["button"],
        padding=(16, 8),
        background=card,
        foreground=text,
        bordercolor=border,
        lightcolor=card,
        darkcolor=border,
        focusthickness=0,
        focuscolor=accent,
    )
    style.map(
        "TButton",
        background=[("active", colors["stripe"]), ("disabled", colors["stripe"])],
        foreground=[("disabled", "#9aa3ad")],
        bordercolor=[("active", accent)],
    )
    style.configure(
        "Accent.TButton",
        font=fonts["button"],
        padding=(18, 9),
        background=accent,
        foreground=WHITE,
        bordercolor=accent,
        lightcolor=accent,
        darkcolor=accent,
        focusthickness=0,
        focuscolor=accent,
    )
    style.map(
        "Accent.TButton",
        background=[("active", hover), ("disabled", ACCENT_LINE)],
        foreground=[("disabled", WHITE), ("!disabled", WHITE)],
        bordercolor=[("active", hover), ("disabled", ACCENT_LINE)],
        lightcolor=[("active", hover), ("disabled", ACCENT_LINE)],
        darkcolor=[("active", hover), ("disabled", ACCENT_LINE)],
    )

    row_h = 36 if sys.platform == "darwin" else 32
    style.configure(
        "Treeview",
        font=fonts["tree"],
        rowheight=row_h,
        background=card,
        fieldbackground=card,
        foreground=text,
        bordercolor=border,
        lightcolor=card,
        darkcolor=border,
        relief="flat",
    )
    style.configure(
        "Treeview.Heading",
        font=fonts["heading"],
        background=colors["stripe"],
        foreground=muted,
        relief="flat",
        padding=(8, 6),
        bordercolor=border,
    )
    style.map(
        "Treeview",
        background=[("selected", ACCENT_SOFT)],
        foreground=[("selected", text)],
    )
    style.map("Treeview.Heading", background=[("active", ACCENT_SOFT)])

    style.configure(
        "Horizontal.TProgressbar",
        troughcolor=colors["stripe"],
        background=accent,
        bordercolor=border,
        lightcolor=accent,
        darkcolor=accent,
        thickness=8,
    )
    style.configure("TScrollbar", background=colors["stripe"], troughcolor=bg, bordercolor=bg, arrowcolor=muted)
    return colors


def draw_drop_card(canvas: tk.Canvas, hover: bool, fonts: dict[str, tuple], colors: dict[str, str]) -> None:
    canvas.delete("all")
    w = max(canvas.winfo_width(), 20)
    h = max(canvas.winfo_height(), 20)
    fill = colors["accent_soft"] if hover else "#f7fbff"
    outline = colors["accent"] if hover else colors["accent_line"]
    pad = 4
    canvas.create_rectangle(
        pad,
        pad,
        w - pad,
        h - pad,
        outline=outline,
        width=2,
        dash=(9, 6),
        fill=fill,
    )
    canvas.create_text(
        w / 2,
        h / 2 - 12,
        text="点这里选择要转换的文件",
        fill=colors["text"],
        font=fonts["drop"],
    )
    canvas.create_text(
        w / 2,
        h / 2 + 14,
        text="支持知网 CAJ、EPUB 电子书，以及图片版 PDF",
        fill=colors["muted"],
        font=fonts["drop_sub"],
    )
