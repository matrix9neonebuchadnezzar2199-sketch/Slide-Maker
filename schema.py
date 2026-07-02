"""slideData スキーマ定義・デザイン定数."""

from __future__ import annotations

from pptx.dml.color import RGBColor
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

# ============================================================
# カラーパレット（RGBCold）— 濃紺プライマリのビジネス配色
# ============================================================

# --- 基本カラー ---
PRIMARY = RGBColor(0x1F, 0x3A, 0x5F)       # 濃紺（タイトル帯・章番号・[[強調]]）
PRIMARY_LT = RGBColor(0x2E, 0x5A, 0x88)    # 明るい紺（サブ要素・グラデ上段）
ACCENT = RGBColor(0x2E, 0x9E, 0xC9)        # シアン系アクセント（差し色・バー）
ACCENT_WARM = RGBColor(0xE8, 0x8A, 0x3C)   # オレンジ（警告・注意）

# --- テキスト ---
TEXT_MAIN = RGBColor(0x1A, 0x1A, 0x1A)     # 本文（ほぼ黒）
TEXT_SUB = RGBColor(0x5A, 0x5A, 0x5A)      # 補足・subhead
TEXT_ON_FILL = RGBColor(0xFF, 0xFF, 0xFF)  # 塗り背景上の白文字

# --- 背景・面 ---
BG_WHITE = RGBColor(0xFF, 0xFF, 0xFF)      # スライド地
BG_LIGHT = RGBColor(0xF4, 0xF6, 0xF9)      # カード・帯の薄い面
BORDER = RGBColor(0xD8, 0xDE, 0xE6)        # 罫線・カード枠

# --- 章扉背景の大番号（単色代用・alpha 不要）---
SECTION_NO_FILL = RGBColor(0xE8, 0xEC, 0xF1)

# --- ステータス色（kpi の status 用）---
STATUS_GOOD = RGBColor(0x2E, 0xA5, 0x6A)
STATUS_BAD = RGBColor(0xD1, 0x4B, 0x4B)
STATUS_NEUTRAL = RGBColor(0x7A, 0x7A, 0x7A)

STATUS_COLORS: dict[str, RGBColor] = {
    "good": STATUS_GOOD,
    "bad": STATUS_BAD,
    "neutral": STATUS_NEUTRAL,
}

# --- ピラミッド等のグラデ段階（上=濃 → 下=淡）---
GRADIENT_STEPS: list[RGBColor] = [
    RGBColor(0x1F, 0x3A, 0x5F),
    RGBColor(0x2E, 0x5A, 0x88),
    RGBColor(0x4A, 0x7F, 0xB0),
    RGBColor(0x7A, 0xA8, 0xCE),
]

# ============================================================
# フォント
# ============================================================
FONT_JP = "Meiryo"
FONT_JP_ALT = "Yu Gothic UI"
FONT_FALLBACK = "MS PGothic"
FONT_FAMILIES = (FONT_JP, FONT_JP_ALT, FONT_FALLBACK)

# フォントサイズ（pt）— 16:9 ワイド基準
SIZE_TITLE_COVER = Pt(40)
SIZE_TITLE_SECTION = Pt(32)
SIZE_SECTION_NO = Pt(200)
SIZE_TITLE = Pt(28)
SIZE_SUBHEAD = Pt(15)
SIZE_BODY = Pt(18)
SIZE_BODY_SM = Pt(14)
SIZE_KPI_VALUE = Pt(36)
SIZE_KPI_LABEL = Pt(13)
SIZE_CAPTION = Pt(11)

# ============================================================
# レイアウト寸法（EMU）— 16:9 = 12192000 × 6858000
# ============================================================
SLIDE_W = Emu(12192000)
SLIDE_H = Emu(6858000)

# 後方互換エイリアス（既存コード・SPEC 参照用）
SLIDE_WIDTH = SLIDE_W
SLIDE_HEIGHT = SLIDE_H

MARGIN_X = Emu(685800)    # 左右マージン 約 0.75 inch
MARGIN_TOP = Emu(457200)  # 上マージン 約 0.5 inch
MARGIN_LEFT = MARGIN_X
MARGIN_RIGHT = MARGIN_X

TITLE_Y = Emu(457200)
TITLE_H = Emu(914400)
SUBHEAD_Y = Emu(1371600)
BODY_Y = Emu(1828800)
BODY_H = Emu(4343400)
CONTENT_W = Emu(10820400)   # SLIDE_W - MARGIN_X * 2

# 後方互換エイリアス
TITLE_TOP = TITLE_Y
SUBHEAD_TOP = SUBHEAD_Y
CONTENT_TOP = BODY_Y

CARD_GAP = Emu(228600)
CARD_RADIUS = Emu(91440)
ACCENT_BAR_W = Emu(68580)

# 表紙・章扉の帯高さ
COVER_BAND_H = Emu(2286000)
SECTION_TITLE_Y = Emu(2800000)
CLOSING_TEXT_Y = Emu(2800000)

# 箇条書き・アジェンダ行高
BULLET_LINE_H = Emu(550000)
AGENDA_LINE_H = Emu(650000)

# 第2弾レイアウト
KPI_CARD_H = Emu(2743200)
KPI_STATUS_BAR_H = Emu(68580)
COMPARE_HEADER_H = Emu(548640)
COMPARE_BULLET_OVAL = Emu(45720)
TABLE_ROW_H = Emu(365760)
BAR_COMPARE_MAX_ROWS = 6
TABLE_WARN_COLS = 8
TABLE_WARN_CELLS = 80
TABLE_DENSE_COLS = 8
COMPARE_MAX_ITEMS = 6


def set_jp_font(
    run,
    name: str = FONT_JP,
    size: Pt | None = None,
    color: RGBColor | None = None,
    bold: bool = False,
) -> None:
    """日本語フォントを ea 属性含めて確実に適用する。

    python-pptx は ``run.font.name`` だけでは東アジア文字に別フォントが
    当たることがあるため、``a:ea`` を XML に明示する。
    """
    run.font.name = name
    run.font.bold = bold
    if size is not None:
        run.font.size = size
    if color is not None:
        run.font.color.rgb = color

    r_el = getattr(run, "_r", None)
    if r_el is None:
        r_el = getattr(run, "_element", None)
    if r_el is None:
        return
    r_pr = r_el.get_or_add_rPr()
    ea = r_pr.find(qn("a:ea"))
    if ea is None:
        ea = r_pr.makeelement(qn("a:ea"), {})
        r_pr.append(ea)
    ea.set("typeface", name)


def gradient_steps_for_levels(level_count: int) -> list[RGBColor]:
    """ピラミッド等で levels 数に応じたグラデ色リストを返す。

    Args:
        level_count: 段数（3〜4 想定）。

    Returns:
        上から濃い順の RGBColor リスト。
    """
    n = max(1, min(level_count, len(GRADIENT_STEPS)))
    return GRADIENT_STEPS[:n]


# ============================================================
# slideData スキーマ定義
# ============================================================

PHASE1_TYPES = frozenset({"title", "section", "content", "agenda", "closing"})

PHASE2_TYPES = frozenset({"kpi", "barCompare", "compare", "table"})

# 現時点で validator / UI が許可する type（第1+2弾）
IMPLEMENTED_TYPES = PHASE1_TYPES | PHASE2_TYPES

ALL_TYPES = PHASE1_TYPES | frozenset({
    "kpi", "barCompare", "compare", "table",
    "pyramid", "triangle", "timeline", "process", "cycle",
})

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

FORBIDDEN_SYMBOLS = ("■", "→")
NOTES_FORBIDDEN_MARKUP = ("**", "[[", "]]")
AUTO_NUMBER_TYPES = frozenset({"agenda", "process", "timeline"})

LEADING_NUMBER_PATTERN = r"^[\d①②③④⑤⑥⑦⑧⑨⑩]+[\.\)、．\s]|^STEP\s*\d+|^第\d+"

# LLM タイトル短縮（Stage 1）
TITLE_SHORTEN_THRESHOLD = 30
TITLE_SHORTEN_MAX = 20
LLM_TIMEOUT_SEC = 15
LLM_MAX_TOKENS = 32
LLM_TEMPERATURE = 0.1
LLM_TITLE_CONTEXT_POINTS = 2
LLM_TITLE_CONTEXT_MAX_CHARS = 200

# LLM モデル・低メモリロード（Glaux glaux-low-memory-llama-server 準拠）
LLM_DEFAULT_MODEL_NAME = "gemma-4-E2B-it-qat-UD-Q2_K_XL.gguf"
LLM_N_CTX = 1000
LLM_N_THREADS = 2
LLM_N_BATCH = 512
LLM_N_UBATCH = 128
LLM_N_GPU_LAYERS = 0
LLM_KV_CACHE_TYPE = "q8_0"
