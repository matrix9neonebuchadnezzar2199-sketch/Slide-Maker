"""slideData と AI タイトル Entry の同期ユーティリティ."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

# AI タイトル生成・手編集の対象 type（表紙・章扉・closing は除外）
AI_TITLE_SKIP_TYPES = frozenset({"title", "section", "closing"})

AI_TITLE_ELIGIBLE_TYPES = frozenset({
    "content",
    "table",
    "kpi",
    "barCompare",
    "compare",
    "agenda",
    "process",
    "timeline",
    "cycle",
    "pyramid",
    "triangle",
})


def should_get_ai_title(slide: dict[str, Any]) -> bool:
    """AI タイトル欄を表示し、上書き対象とするスライドかどうか。"""
    slide_type = slide.get("type", "")
    if slide_type in AI_TITLE_SKIP_TYPES:
        return False
    return slide_type in AI_TITLE_ELIGIBLE_TYPES


def list_ai_title_target_indices(slide_data: list[dict[str, Any]]) -> list[int]:
    """AI タイトル対象スライドの index 一覧を返す。"""
    return [i for i, slide in enumerate(slide_data) if should_get_ai_title(slide)]


def merge_ai_titles_into_slides(
    slide_data: list[dict[str, Any]],
    titles_by_index: dict[int, str],
) -> list[dict[str, Any]]:
    """Entry 欄の最新タイトルを slideData に反映する（検証・PPTX 作成直前用）。"""
    result = deepcopy(slide_data)
    for index, title in titles_by_index.items():
        if index < 0 or index >= len(result):
            continue
        if not should_get_ai_title(result[index]):
            continue
        cleaned = title.strip()
        if cleaned:
            result[index]["title"] = cleaned
    return result
