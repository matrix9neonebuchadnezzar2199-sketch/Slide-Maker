"""Slide-Maker GUI テーマ — Green Color Palette."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# Green Color Palettes（添付デザインガイド準拠）
GREEN_DEEP = "#1d3937"
GREEN_EMERALD = "#195042"
GOLD = "#91855a"
GOLD_HOVER = "#a69666"
BEIGE = "#d6cabc"
APP_BG = "#eee8dc"
CREAM_CARD = "#f7f2ea"
WHITE = "#ffffff"
TEXT_ON_DARK = "#f5f0e8"
TEXT_MAIN = "#1d3937"
TEXT_SUB = "#5a6a64"
BORDER = "#c4b8a8"
CARD_BORDER = "#d8cfc0"

MIN_WINDOW_WIDTH = 1120
MIN_WINDOW_HEIGHT = 760
DEFAULT_GEOMETRY = "1180x820"


def apply_theme(root: tk.Tk, *, font_family: str) -> ttk.Style:
    """ttk スタイルとルート背景を適用する。"""
    root.configure(bg=APP_BG)

    style = ttk.Style(root)
    # clam は Windows でも色カスタムが効きやすい
    if "clam" in style.theme_names():
        style.theme_use("clam")

    base_font = (font_family, 12)
    small_font = (font_family, 10)
    heading_font = (font_family, 22, "bold")
    section_font = (font_family, 13, "bold")

    style.configure(".", background=APP_BG, foreground=TEXT_MAIN, font=base_font)
    style.configure("TFrame", background=APP_BG)
    style.configure("Card.TFrame", background=CREAM_CARD, relief="flat")
    style.configure("TLabel", background=APP_BG, foreground=TEXT_MAIN, font=base_font)
    style.configure("Card.TLabel", background=CREAM_CARD, foreground=TEXT_MAIN, font=base_font)
    style.configure("Muted.TLabel", background=APP_BG, foreground=TEXT_SUB, font=small_font)
    style.configure("CardMuted.TLabel", background=CREAM_CARD, foreground=TEXT_SUB, font=small_font)
    style.configure("Section.TLabel", background=CREAM_CARD, foreground=TEXT_MAIN, font=section_font)
    style.configure("Step.TLabel", background=CREAM_CARD, foreground=GREEN_EMERALD, font=(font_family, 12, "bold"))
    style.configure("Status.TLabel", background=GREEN_DEEP, foreground=TEXT_ON_DARK, font=base_font)
    style.configure("StatusValue.TLabel", background=GREEN_DEEP, foreground=GOLD, font=base_font)

    style.configure(
        "TEntry",
        fieldbackground=WHITE,
        foreground=TEXT_MAIN,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        padding=(8, 7),
    )
    style.configure(
        "TRadiobutton",
        background=CREAM_CARD,
        foreground=TEXT_MAIN,
        font=base_font,
    )
    style.map("TRadiobutton", background=[("active", CREAM_CARD)])

    style.configure(
        "TButton",
        background=CREAM_CARD,
        foreground=TEXT_MAIN,
        bordercolor=BORDER,
        padding=(14, 8),
        font=base_font,
    )
    style.map(
        "TButton",
        background=[("active", BEIGE), ("disabled", "#e8e0d4")],
        foreground=[("disabled", "#9a9a9a")],
    )
    style.configure(
        "Accent.TButton",
        background=GOLD,
        foreground=WHITE,
        bordercolor=GOLD,
        padding=(18, 9),
        font=(font_family, 12, "bold"),
    )
    style.map(
        "Accent.TButton",
        background=[("active", GOLD_HOVER), ("disabled", "#b8ad8a")],
        foreground=[("disabled", "#f0f0f0")],
    )

    style.configure("Header.TLabel", background=GREEN_DEEP, foreground=TEXT_ON_DARK, font=heading_font)
    style.configure("HeaderSub.TLabel", background=GREEN_DEEP, foreground=GOLD, font=small_font)

    return style
