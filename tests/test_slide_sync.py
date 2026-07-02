"""slide_sync ユニットテスト."""

from __future__ import annotations

import slide_sync


def test_should_get_ai_title_skips_cover_section_closing() -> None:
    """表紙・章扉・closing は AI タイトル対象外。"""
    assert not slide_sync.should_get_ai_title({"type": "title", "title": "表紙"})
    assert not slide_sync.should_get_ai_title({"type": "section", "title": "章"})
    assert not slide_sync.should_get_ai_title({"type": "closing"})


def test_should_get_ai_title_includes_body_types() -> None:
    """本文系 type は AI タイトル対象。"""
    assert slide_sync.should_get_ai_title({"type": "content", "title": "T"})
    assert slide_sync.should_get_ai_title({"type": "table", "title": "T"})
    assert slide_sync.should_get_ai_title({"type": "kpi", "title": "T"})


def test_merge_ai_titles_into_slides() -> None:
    """Entry 値が該当 slide の title に反映される。"""
    slides = [
        {"type": "title", "title": "表紙", "date": "2026.01.01"},
        {"type": "content", "title": "旧タイトル", "points": ["a"]},
    ]
    merged = slide_sync.merge_ai_titles_into_slides(slides, {1: "新タイトル"})
    assert merged[0]["title"] == "表紙"
    assert merged[1]["title"] == "新タイトル"


def test_list_ai_title_target_indices() -> None:
    """対象 index 一覧が正しい。"""
    slides = [
        {"type": "title", "title": "表紙", "date": "2026.01.01"},
        {"type": "content", "title": "A", "points": []},
        {"type": "section", "title": "章"},
        {"type": "table", "title": "B", "headers": ["h"], "rows": [["v"]]},
    ]
    assert slide_sync.list_ai_title_target_indices(slides) == [1, 3]
