"""PPTX 描画エンジン — RENDERERS ディスパッチ方式."""

from __future__ import annotations

import logging
import re
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Pt

import schema

logger = logging.getLogger(__name__)

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_EMPHASIS_RE = re.compile(r"\[\[(.+?)\]\]")


def _fill_solid(shape, color: RGBColor) -> None:
    """図形を単色塗りにする。"""
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()


def _add_textbox(
    slide,
    left: Emu,
    top: Emu,
    width: Emu,
    height: Emu,
    text: str,
    *,
    font_size: Pt = schema.SIZE_BODY,
    bold: bool = False,
    color: RGBColor = schema.TEXT_MAIN,
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
    schema.set_jp_font(run, size=font_size, color=color, bold=bold)
    return box


def _add_rich_textbox(
    slide,
    left: Emu,
    top: Emu,
    width: Emu,
    height: Emu,
    text: str,
    *,
    font_size: Pt = schema.SIZE_BODY,
    color: RGBColor = schema.TEXT_MAIN,
) -> Any:
    """**太字** と [[強調]] を解釈するテキストボックス。"""
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.TOP
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT

    for seg_text, seg_bold, seg_emphasis in _parse_inline_markup(text):
        if not seg_text:
            continue
        run = p.add_run()
        run.text = seg_text
        seg_color = schema.PRIMARY if seg_emphasis else color
        schema.set_jp_font(
            run,
            size=font_size,
            color=seg_color,
            bold=seg_bold or seg_emphasis,
        )

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


def _draw_title_header(slide, s: dict[str, Any]) -> None:
    """共通タイトル帯（左アクセントバー + タイトル + subhead）を描画する。"""
    # 左縦アクセントバー
    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        schema.MARGIN_X - schema.ACCENT_BAR_W,
        schema.TITLE_Y,
        schema.ACCENT_BAR_W,
        schema.TITLE_H,
    )
    _fill_solid(bar, schema.ACCENT)

    title = s.get("title", "")
    if title:
        _add_textbox(
            slide,
            schema.MARGIN_X,
            schema.TITLE_Y,
            schema.CONTENT_W,
            schema.TITLE_H,
            title,
            font_size=schema.SIZE_TITLE,
            bold=True,
            color=schema.PRIMARY,
        )

    subhead = s.get("subhead")
    if subhead:
        _add_textbox(
            slide,
            schema.MARGIN_X,
            schema.SUBHEAD_Y,
            schema.CONTENT_W,
            Emu(400000),
            subhead,
            font_size=schema.SIZE_SUBHEAD,
            color=schema.TEXT_SUB,
        )


def render_title(prs: Presentation, s: dict[str, Any]) -> None:
    """表紙スライドを描画する。"""
    slide = _add_slide(prs)
    band = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Emu(0),
        Emu(0),
        schema.SLIDE_W,
        schema.COVER_BAND_H,
    )
    _fill_solid(band, schema.PRIMARY)

    title = s.get("title", "")
    _add_textbox(
        slide,
        schema.MARGIN_X,
        Emu(2000000),
        schema.CONTENT_W,
        Emu(1200000),
        title,
        font_size=schema.SIZE_TITLE_COVER,
        bold=True,
        color=schema.TEXT_ON_FILL,
    )

    date_str = s.get("date", "")
    if date_str:
        _add_textbox(
            slide,
            schema.MARGIN_X,
            Emu(5200000),
            schema.CONTENT_W,
            Emu(400000),
            date_str,
            font_size=schema.SIZE_CAPTION,
            color=schema.TEXT_SUB,
        )


def render_section(prs: Presentation, s: dict[str, Any]) -> None:
    """章扉スライドを描画する。"""
    slide = _add_slide(prs)
    bg = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Emu(0), Emu(0), schema.SLIDE_W, schema.SLIDE_H,
    )
    _fill_solid(bg, schema.PRIMARY)

    section_no = s.get("sectionNo")
    if section_no is not None:
        _add_textbox(
            slide,
            Emu(800000),
            Emu(800000),
            Emu(10000000),
            Emu(5000000),
            str(section_no),
            font_size=schema.SIZE_SECTION_NO,
            bold=True,
            color=schema.SECTION_NO_FILL,
            align=PP_ALIGN.LEFT,
        )

    title = s.get("title", "")
    _add_textbox(
        slide,
        schema.MARGIN_X,
        schema.SECTION_TITLE_Y,
        schema.CONTENT_W,
        Emu(1500000),
        title,
        font_size=schema.SIZE_TITLE_SECTION,
        bold=True,
        color=schema.TEXT_ON_FILL,
    )


def render_content(prs: Presentation, s: dict[str, Any]) -> None:
    """箇条書き本文スライドを描画する。"""
    slide = _add_slide(prs)
    _draw_title_header(slide, s)

    gap = schema.CARD_GAP
    if s.get("twoColumn") and s.get("columns"):
        cols = s["columns"]
        col_w = (schema.CONTENT_W - gap) // 2
        for ci, col_items in enumerate(cols[:2]):
            left = schema.MARGIN_X + ci * (col_w + gap)
            _draw_bullet_list(slide, left, schema.BODY_Y, col_w, col_items or [])
    else:
        points = s.get("points") or []
        _draw_bullet_list(slide, schema.MARGIN_X, schema.BODY_Y, schema.CONTENT_W, points)


def _draw_bullet_list(slide, left: Emu, top: Emu, width: Emu, items: list[str]) -> None:
    """箇条書きリストを描画する。"""
    for i, item in enumerate(items):
        y = top + i * schema.BULLET_LINE_H
        _add_textbox(
            slide, left, y, Emu(200000), schema.BULLET_LINE_H,
            "•", font_size=schema.SIZE_BODY, color=schema.ACCENT,
        )
        _add_rich_textbox(
            slide, left + Emu(250000), y, width - Emu(250000), schema.BULLET_LINE_H,
            item, font_size=schema.SIZE_BODY,
        )


def render_agenda(prs: Presentation, s: dict[str, Any]) -> None:
    """アジェンダスライドを描画する。"""
    slide = _add_slide(prs)
    _draw_title_header(slide, s)

    items = s.get("items") or []
    for i, item in enumerate(items):
        y = schema.BODY_Y + i * schema.AGENDA_LINE_H
        num_text = f"{i + 1:02d}"
        _add_textbox(
            slide, schema.MARGIN_X, y, Emu(600000), schema.AGENDA_LINE_H,
            num_text, font_size=schema.SIZE_BODY, bold=True, color=schema.ACCENT,
        )
        _add_textbox(
            slide, schema.MARGIN_X + Emu(700000), y,
            schema.CONTENT_W - Emu(700000), schema.AGENDA_LINE_H,
            item, font_size=schema.SIZE_BODY,
        )


def render_closing(prs: Presentation, s: dict[str, Any]) -> None:
    """結びスライドを描画する。"""
    slide = _add_slide(prs)
    bg = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Emu(0), Emu(0), schema.SLIDE_W, schema.SLIDE_H,
    )
    _fill_solid(bg, schema.PRIMARY)

    _add_textbox(
        slide,
        schema.MARGIN_X,
        schema.CLOSING_TEXT_Y,
        schema.CONTENT_W,
        Emu(1200000),
        "ご清聴ありがとうございました",
        font_size=schema.SIZE_TITLE_SECTION,
        bold=True,
        color=schema.TEXT_ON_FILL,
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
    prs.slide_width = schema.SLIDE_W
    prs.slide_height = schema.SLIDE_H

    for s in slide_data:
        slide_type = s.get("type", "content")
        renderer_fn = RENDERERS.get(slide_type, render_content)
        try:
            renderer_fn(prs, s)
        except Exception as exc:
            logger.warning("skip slide type=%s err=%s", slide_type, exc)

    prs.save(out_path)
