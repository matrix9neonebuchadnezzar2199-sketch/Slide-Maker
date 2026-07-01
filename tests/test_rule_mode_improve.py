"""rule_mode の見出し除去・表紙タイトル."""

from __future__ import annotations

import rule_mode


def test_h4_heading_stripped_from_content_points() -> None:
    """#### 記号が content points に残らない。"""
    text = """## 月例報告

#### 令和８年６月30日
- 景気は緩やかに回復している。
"""
    slides = rule_mode.build_slide_data(text, pdf_stem="fallback")
    points: list[str] = []
    for slide in slides:
        if slide.get("type") == "content":
            points.extend(slide.get("points", []))
    assert points
    assert all("####" not in p for p in points)
    titles = [s.get("title", "") for s in slides if s.get("type") == "content"]
    assert any("令和８年６月30日" in t for t in titles) or any(
        "令和８年６月30日" in p for p in points
    )


def test_cover_title_paren_only_excluded_from_auto_detect() -> None:
    """括弧のみの見出しは自動表紙候補にならない。"""
    text = """（令和８年６月）

## 月例経済報告
"""
    slides = rule_mode.build_slide_data(text, pdf_stem="fallback")
    assert slides[0]["title"] == "月例経済報告"


def test_html_tags_stripped_from_titles_points_and_tables() -> None:
    """PyMuPDF4LLM 由来の HTML 装飾タグが最終JSONに残らない。"""
    text = """## <u>個人消費は、持ち直しの動きがみられる。</u>

- <b>雇用情勢</b>は改善している。
- 物価は<i>緩やかに上昇</i>している。

## 主要変更点

|項目|内容|
|---|---|
|<u>消費</u>|持ち直し<br>継続|
"""
    slides = rule_mode.build_slide_data(text, pdf_stem="fallback")
    rendered = str(slides)

    assert "<u>" not in rendered
    assert "</u>" not in rendered
    assert "<b>" not in rendered
    assert "<i>" not in rendered
    assert "<br>" not in rendered.lower()
    assert any(
        slide.get("title") == "個人消費は、持ち直しの動きがみられる。"
        for slide in slides
        if slide.get("type") == "content"
    )
    table_slides = [slide for slide in slides if slide.get("type") == "table"]
    assert table_slides
    assert table_slides[0]["rows"][0] == ["消費", "持ち直し 継続"]
