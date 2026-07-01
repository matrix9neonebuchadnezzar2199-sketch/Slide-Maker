"""PPTX 描画エンジン — RENDERERS ディスパッチ方式."""

from __future__ import annotations

import logging
import re
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Pt

import schema

logger = logging.getLogger(__name__)

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_EMPHASIS_RE = re.compile(r"\[\[(.+?)\]\]")


def _hex_to_rgb(hex_color: str) -> RGBColor:
    """#RRGGBB を RGBColor に変換する。"""
    h = hex_color.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _set_font(run, *, size: Pt | None = None, bold: bool = False, color: str | None = None) -> None:
    """run にフォント属性を設定する。"""
    run.font.name = schema.FONT_FAMILIES[0]
    if size:
        run.font.size = size
    run.font.bold = bold
    if color:
        run.font.color.rgb = _hex_to_rgb(color)


def _add_textbox(
    slide,
    left: Emu,
    top: Emu,
    width: Emu,
    height: Emu,
    text: str,
    *,
    font_size: Pt = schema.FONT_BODY,
    bold: bool = False,
    color: str = schema.COLOR_TEXT,
    align: PP_ALIGN = PP_ALIGN.LEFT,
) -> Any:
    """単純テキストボックスを追加する。"""
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.TOP
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    _set_font(run, size=font_size, bold=bold, color=color)
    return box


def _add_rich_textbox(
    slide,
    left: Emu,
    top: Emu,
    width: Emu,
    height: Emu,
    text: str,
    *,
    font_size: Pt = schema.FONT_BODY,
    color: str = schema.COLOR_TEXT,
) -> Any:
    """**太字** と [[強調]] を解釈するテキストボックス。"""
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.TOP
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT

    segments = _parse_inline_markup(text)
    for seg_text, seg_bold, seg_emphasis in segments:
        if not seg_text:
            continue
        run = p.add_run()
        run.text = seg_text
        seg_color = schema.COLOR_PRIMARY if seg_emphasis else color
        _set_font(run, size=font_size, bold=seg_bold or seg_emphasis, color=seg_color)

    return box


def _parse_inline_markup(text: str) -> list[tuple[str, bool, bool]]:
    """インライン記法をセグメントに分割する。"""
    segments: list[tuple[str, bool, bool]] = []
    pos = 0
    while pos < len(text):
        bold_m = _BOLD_RE.search(text, pos)
        emph_m = _EMPHASIS_RE.search(text, pos)
        candidates = [(m, "bold") for m in [bold_m] if m] + [(m, "emph") for m in [emph_m] if m]
        if not candidates:
            segments.append((text[pos:], False, False))
            break
        candidates.sort(key=lambda x: x[0].start())
        match, kind = candidates[0]
        if match.start() > pos:
            segments.append((text[pos:match.start()], False, False))
        inner = match.group(1)
        if kind == "bold":
            segments.append((inner, True, False))
        else:
            segments.append((inner, True, True))
        pos = match.end()
    return segments


def _blank_layout(prs: Presentation):
    """白紙に近いレイアウト（タイトルのみ）を返す。"""
    return prs.slide_layouts[6]


def _add_slide(prs: Presentation):
    """新規スライドを追加する。"""
    return prs.slides.add_slide(_blank_layout(prs))


def _content_width() -> Emu:
    return schema.SLIDE_WIDTH - schema.MARGIN_LEFT - schema.MARGIN_RIGHT


def _draw_title_header(slide, s: dict[str, Any]) -> None:
    """共通タイトル＋サブヘッドを描画する。"""
    title = s.get("title", "")
    if title:
        _add_textbox(
            slide,
            schema.MARGIN_LEFT,
            schema.TITLE_TOP,
            _content_width(),
            Emu(800000),
            title,
            font_size=schema.FONT_TITLE,
            bold=True,
            color=schema.COLOR_PRIMARY,
        )
    subhead = s.get("subhead")
    if subhead:
        _add_textbox(
            slide,
            schema.MARGIN_LEFT,
            schema.SUBHEAD_TOP,
            _content_width(),
            Emu(400000),
            subhead,
            font_size=schema.FONT_SUBHEAD,
            color=schema.COLOR_GRAY,
        )


def render_title(prs: Presentation, s: dict[str, Any]) -> None:
    """表紙スライドを描画する。"""
    slide = _add_slide(prs)
    # 背景アクセント帯
    band = slide.shapes.add_shape(
        1,  # MSO_SHAPE.RECTANGLE
        Emu(0),
        Emu(0),
        schema.SLIDE_WIDTH,
        Emu(2286000),
    )
    band.fill.solid()
    band.fill.fore_color.rgb = _hex_to_rgb(schema.COLOR_PRIMARY)
    band.line.fill.background()

    title = s.get("title", "")
    _add_textbox(
        slide,
        schema.MARGIN_LEFT,
        Emu(2000000),
        _content_width(),
        Emu(1200000),
        title,
        font_size=Pt(40),
        bold=True,
        color=schema.COLOR_TEXT_LIGHT,
    )
    date_str = s.get("date", "")
    if date_str:
        _add_textbox(
            slide,
            schema.MARGIN_LEFT,
            Emu(5200000),
            _content_width(),
            Emu(400000),
            date_str,
            font_size=schema.FONT_SUBHEAD,
            color=schema.COLOR_GRAY,
        )


def render_section(prs: Presentation, s: dict[str, Any]) -> None:
    """章扉スライドを描画する。"""
    slide = _add_slide(prs)
    # 背景
    bg = slide.shapes.add_shape(1, Emu(0), Emu(0), schema.SLIDE_WIDTH, schema.SLIDE_HEIGHT)
    bg.fill.solid()
    bg.fill.fore_color.rgb = _hex_to_rgb(schema.COLOR_SECTION_BG)
    bg.line.fill.background()

    section_no = s.get("sectionNo")
    if section_no is not None:
        _add_textbox(
            slide,
            Emu(800000),
            Emu(800000),
            Emu(10000000),
            Emu(5000000),
            str(section_no),
            font_size=schema.FONT_SECTION_NO,
            bold=True,
            color="#334155",
            align=PP_ALIGN.LEFT,
        )

    title = s.get("title", "")
    _add_textbox(
        slide,
        schema.MARGIN_LEFT,
        Emu(2800000),
        _content_width(),
        Emu(1500000),
        title,
        font_size=schema.FONT_SECTION,
        bold=True,
        color=schema.COLOR_TEXT_LIGHT,
    )


def render_content(prs: Presentation, s: dict[str, Any]) -> None:
    """箇条書き本文スライドを描画する。"""
    slide = _add_slide(prs)
    _draw_title_header(slide, s)

    if s.get("twoColumn") and s.get("columns"):
        cols = s["columns"]
        col_w = (_content_width() - Emu(200000)) // 2
        for ci, col_items in enumerate(cols[:2]):
            left = schema.MARGIN_LEFT + ci * (col_w + Emu(200000))
            _draw_bullet_list(slide, left, schema.CONTENT_TOP, col_w, col_items or [])
    else:
        points = s.get("points") or []
        _draw_bullet_list(slide, schema.MARGIN_LEFT, schema.CONTENT_TOP, _content_width(), points)


def _draw_bullet_list(slide, left: Emu, top: Emu, width: Emu, items: list[str]) -> None:
    """箇条書きリストを描画する。"""
    line_height = Emu(550000)
    for i, item in enumerate(items):
        y = top + i * line_height
        # ビュレット
        _add_textbox(
            slide, left, y, Emu(200000), line_height,
            "•", font_size=schema.FONT_BODY, color=schema.COLOR_ACCENT,
        )
        _add_rich_textbox(
            slide, left + Emu(250000), y, width - Emu(250000), line_height,
            item, font_size=schema.FONT_BODY,
        )


def render_agenda(prs: Presentation, s: dict[str, Any]) -> None:
    """アジェンダスライドを描画する。"""
    slide = _add_slide(prs)
    _draw_title_header(slide, s)

    items = s.get("items") or []
    line_height = Emu(650000)
    for i, item in enumerate(items):
        y = schema.CONTENT_TOP + i * line_height
        num_text = f"{i + 1:02d}"
        _add_textbox(
            slide, schema.MARGIN_LEFT, y, Emu(600000), line_height,
            num_text, font_size=schema.FONT_AGENDA_ITEM, bold=True, color=schema.COLOR_ACCENT,
        )
        _add_textbox(
            slide, schema.MARGIN_LEFT + Emu(700000), y,
            _content_width() - Emu(700000), line_height,
            item, font_size=schema.FONT_AGENDA_ITEM,
        )


def render_closing(prs: Presentation, s: dict[str, Any]) -> None:
    """結びスライドを描画する。"""
    slide = _add_slide(prs)
    bg = slide.shapes.add_shape(1, Emu(0), Emu(0), schema.SLIDE_WIDTH, schema.SLIDE_HEIGHT)
    bg.fill.solid()
    bg.fill.fore_color.rgb = _hex_to_rgb(schema.COLOR_PRIMARY)
    bg.line.fill.background()

    _add_textbox(
        slide,
        schema.MARGIN_LEFT,
        Emu(2800000),
        _content_width(),
        Emu(1200000),
        "ご清聴ありがとうございました",
        font_size=Pt(36),
        bold=True,
        color=schema.COLOR_TEXT_LIGHT,
        align=PP_ALIGN.CENTER,
    )


RENDERERS = {
    "title": render_title,
    "section": render_section,
    "content": render_content,
    "agenda": render_agenda,
    "closing": render_closing,
}


def build_pptx(slide_data: list[dict[str, Any]], out_path: str, template: str | None = None) -> None:
    """slideData から PPTX を生成する。

    Args:
        slide_data: 検証済みスライド配列。
        out_path: 出力 .pptx パス。
        template: 任意のテンプレートパス。
    """
    prs = Presentation(template) if template else Presentation()
    prs.slide_width = schema.SLIDE_WIDTH
    prs.slide_height = schema.SLIDE_HEIGHT

    for s in slide_data:
        slide_type = s.get("type", "content")
        renderer = RENDERERS.get(slide_type, render_content)
        try:
            renderer(prs, s)
        except Exception as exc:
            logger.warning("skip slide type=%s err=%s", slide_type, exc)

    prs.save(out_path)
