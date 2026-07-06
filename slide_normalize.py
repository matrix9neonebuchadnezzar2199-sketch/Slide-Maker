"""魔人式 JSON の未対応 type を content へ降格する."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import schema


def normalize_slide_data(data: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """未実装 type を content に変換し、警告メッセージを返す。

    Args:
        data: パース済み slideData。

    Returns:
        (正規化後 slideData, 警告リスト)
    """
    if not isinstance(data, list):
        return data, []

    result: list[dict[str, Any]] = []
    warnings: list[str] = []

    for idx, slide in enumerate(data, start=1):
        if not isinstance(slide, dict):
            result.append(slide)
            continue
        normalized, warning = _normalize_single_slide(slide, idx)
        result.append(normalized)
        if warning:
            warnings.append(warning)

    return result, warnings


def _normalize_single_slide(slide: dict[str, Any], index: int) -> tuple[dict[str, Any], str | None]:
    """1枚分を正規化する。"""
    slide_type = slide.get("type")
    if slide_type in schema.IMPLEMENTED_TYPES:
        return slide, None
    if slide_type not in schema.MAJIN_DOWNGRADE_TYPES:
        return slide, None

    converted = _downgrade_to_content(slide)
    warning = (
        f"スライド {index}: type `{slide_type}` は Slide-Maker 未対応のため "
        f"content に変換しました（専用レイアウトは描画されません）。"
    )
    return converted, warning


def _downgrade_to_content(slide: dict[str, Any]) -> dict[str, Any]:
    """魔人式スライドを content へ変換する。"""
    slide_type = str(slide.get("type", "content"))
    title = str(slide.get("title", ""))
    points: list[str] = []

    if slide_type == "processList":
        points = [str(step) for step in slide.get("steps") or []]
    elif slide_type == "faq":
        for item in slide.get("items") or []:
            if isinstance(item, dict):
                points.append(f"Q: {item.get('q', '')}")
                points.append(f"A: {item.get('a', '')}")
    elif slide_type == "quote":
        points = [str(slide.get("text", "")), f"— {slide.get('author', '')}".strip(" —")]
    elif slide_type in ("cards", "headerCards", "bulletCards", "stepUp"):
        for item in slide.get("items") or []:
            if isinstance(item, str):
                points.append(item)
            elif isinstance(item, dict):
                head = str(item.get("title", ""))
                desc = str(item.get("desc", ""))
                points.append(f"{head}: {desc}".strip(": "))
    elif slide_type == "progress":
        for item in slide.get("items") or []:
            if isinstance(item, dict):
                points.append(f"{item.get('label', '')}: {item.get('percent', '')}%")
    elif slide_type == "statsCompare":
        left_title = slide.get("leftTitle", "左")
        right_title = slide.get("rightTitle", "右")
        for stat in slide.get("stats") or []:
            if isinstance(stat, dict):
                points.append(
                    f"{stat.get('label', '')}: {left_title}{stat.get('leftValue', '')} / "
                    f"{right_title}{stat.get('rightValue', '')}"
                )
    elif slide_type == "flowChart":
        for flow in slide.get("flows") or []:
            if isinstance(flow, dict):
                points.extend(str(step) for step in flow.get("steps") or [])
    elif slide_type == "diagram":
        for lane in slide.get("lanes") or []:
            if isinstance(lane, dict):
                lane_title = str(lane.get("title", ""))
                lane_items = lane.get("items") or []
                points.append(lane_title)
                points.extend(str(item) for item in lane_items)
    elif slide_type == "imageText":
        points = [str(point) for point in slide.get("points") or []]
        image = slide.get("image")
        if image:
            points.insert(0, f"[画像] {image}")
    else:
        for key in ("points", "steps", "items", "text"):
            value = slide.get(key)
            if isinstance(value, list):
                points.extend(str(item) for item in value)
            elif value:
                points.append(str(value))

    if not points:
        points = ["（内容を編集してください）"]

    result: dict[str, Any] = {
        "type": "content",
        "title": title or "スライド",
        "points": points,
    }
    subhead = slide.get("subhead")
    if subhead:
        result["subhead"] = subhead
    notes = slide.get("notes")
    if notes:
        result["notes"] = notes
    return deepcopy(result)
