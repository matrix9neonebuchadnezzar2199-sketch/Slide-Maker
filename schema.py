"""slideData スキーマ定義・デザイン定数."""

from __future__ import annotations

from pptx.util import Emu, Pt

# --- スライド寸法 (16:9 固定) ---
SLIDE_WIDTH = Emu(12192000)
SLIDE_HEIGHT = Emu(6858000)

# --- レイアウト (EMU) ---
MARGIN_LEFT = Emu(457200)      # ~0.5 inch
MARGIN_RIGHT = Emu(457200)
MARGIN_TOP = Emu(365760)        # ~0.4 inch
CONTENT_TOP = Emu(1371600)      # タイトル下の本文開始
TITLE_TOP = Emu(548640)
SUBHEAD_TOP = Emu(1005840)
FOOTER_TOP = Emu(6400800)

# --- フォントサイズ (Pt) ---
FONT_TITLE = Pt(32)
FONT_SECTION = Pt(36)
FONT_SUBHEAD = Pt(18)
FONT_BODY = Pt(20)
FONT_AGENDA_ITEM = Pt(22)
FONT_KPI_VALUE = Pt(28)
FONT_SMALL = Pt(14)
FONT_SECTION_NO = Pt(120)

# --- 日本語フォント優先順 ---
FONT_FAMILIES = ("Meiryo", "Yu Gothic UI", "MS Gothic", "Arial")

# --- 配色 (ビジネス向け落ち着いた青系) ---
COLOR_PRIMARY = "#1B3A6B"       # 濃紺
COLOR_ACCENT = "#2E6DB4"        # アクセント青
COLOR_BG = "#FFFFFF"
COLOR_TEXT = "#1A1A1A"
COLOR_TEXT_LIGHT = "#FFFFFF"
COLOR_GRAY = "#6B7280"
COLOR_GRAY_LIGHT = "#E5E7EB"
COLOR_GOOD = "#059669"
COLOR_BAD = "#DC2626"
COLOR_NEUTRAL = "#6B7280"
COLOR_SECTION_BG = "#1B3A6B"
COLOR_SECTION_NO = "#FFFFFF33"  # 半透明章番号用（描画時に alpha 相当で薄く）

# --- 第1弾で有効な type ---
PHASE1_TYPES = frozenset({"title", "section", "content", "agenda", "closing"})

# --- 全 type（将来拡張用） ---
ALL_TYPES = PHASE1_TYPES | frozenset({
    "kpi", "barCompare", "compare", "table",
    "pyramid", "triangle", "timeline", "process", "cycle",
})

# --- type 別必須フィールド ---
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "title": ("title", "date"),
    "section": ("title",),
    "content": ("title",),
    "agenda": ("title", "items"),
    "closing": (),
    "kpi": ("title", "items"),
    "barCompare": ("title", "stats"),
    "compare": ("title", "leftTitle", "rightTitle", "leftItems", "rightItems"),
    "table": ("title", "headers", "rows"),
    "pyramid": ("title", "levels"),
    "triangle": ("title", "items"),
    "timeline": ("title", "milestones"),
    "process": ("title", "steps"),
    "cycle": ("title", "items"),
}

# --- 固定数制約 ---
FIXED_COUNT: dict[str, int] = {
    "triangle": 3,
    "cycle": 4,
}

MAX_COUNT: dict[str, int] = {
    "kpi": 4,
    "process": 4,
    "pyramid_levels_min": 3,
    "pyramid_levels_max": 4,
}

# --- テキストルール ---
FORBIDDEN_SYMBOLS = ("■", "→")
NOTES_FORBIDDEN_MARKUP = ("**", "[[", "]]")
AUTO_NUMBER_TYPES = frozenset({"agenda", "process", "timeline"})

# 先頭番号パターン（自動番号描画 type 用）
LEADING_NUMBER_PATTERN = r"^[\d①②③④⑤⑥⑦⑧⑨⑩]+[\.\)、．\s]|^STEP\s*\d+|^第\d+"
