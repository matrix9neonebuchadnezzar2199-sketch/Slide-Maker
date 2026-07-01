"""slideData の構文・スキーマ検証."""

from __future__ import annotations

import json
import re
from typing import Any

import schema

_LEADING_NUMBER_RE = re.compile(schema.LEADING_NUMBER_PATTERN, re.IGNORECASE)


def validate_json_text(
    text: str,
) -> tuple[list[dict[str, Any]] | None, list[str], list[str]]:
    """JSON テキストをパースし、スキーマ検証する。

    Args:
        text: UI 上の JSON 文字列。

    Returns:
        (data, errors, warnings) — 成功時 errors は空。warnings は非致命の注意。
    """
    stripped = text.strip()
    if not stripped:
        return None, ["JSON が空です。"], []

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return None, [f"JSON 構文エラー: {exc.msg} (行 {exc.lineno}, 列 {exc.colno})"], []

    errors = validate_slide_data(parsed)
    if errors:
        return None, errors, []

    warnings = collect_warnings(parsed)
    return parsed, [], warnings


def validate_slide_data(data: Any, *, strict_types: bool = True) -> list[str]:
    """slideData 配列のスキーマ検証。

    Args:
        data: パース済み JSON データ。
        strict_types: True のとき未知 type をエラーとする。

    Returns:
        人間が読める日本語エラーメッセージのリスト。
    """
    errors: list[str] = []

    if not isinstance(data, list):
        return ["トップレベルはスライドオブジェクトの配列である必要があります。"]

    if len(data) == 0:
        errors.append("スライドが 1 枚もありません。")

    for idx, slide in enumerate(data, start=1):
        prefix = f"スライド {idx}"
        slide_errors = _validate_slide(slide, prefix, strict_types=strict_types)
        errors.extend(slide_errors)

    return errors


def _validate_slide(slide: Any, prefix: str, *, strict_types: bool) -> list[str]:
    """単一スライドオブジェクトを検証する。"""
    errors: list[str] = []

    if not isinstance(slide, dict):
        return [f"{prefix}: スライドはオブジェクトである必要があります。"]

    slide_type = slide.get("type")
    if not slide_type:
        errors.append(f"{prefix}: `type` キーが必須です。")
        return errors

    if not isinstance(slide_type, str):
        errors.append(f"{prefix}: `type` は文字列である必要があります。")
        return errors

    known = schema.IMPLEMENTED_TYPES if strict_types else schema.ALL_TYPES
    if slide_type not in known:
        errors.append(f"{prefix}: 未知の type `{slide_type}` です。")
        return errors

    for field in schema.REQUIRED_FIELDS.get(slide_type, ()):
        if field not in slide:
            errors.append(f"{prefix}: `{slide_type}` には `{field}` が必須です。")

    errors.extend(_validate_type_specific(slide, prefix, slide_type))
    errors.extend(_validate_text_rules(slide, prefix, slide_type))

    if "notes" in slide and slide["notes"] is not None:
        if not isinstance(slide["notes"], str):
            errors.append(f"{prefix}: `notes` は文字列である必要があります。")
        else:
            for markup in schema.NOTES_FORBIDDEN_MARKUP:
                if markup in slide["notes"]:
                    errors.append(
                        f"{prefix}: `notes` にマークアップ `{markup}` を含めないでください。"
                    )

    return errors


def collect_warnings(data: Any) -> list[str]:
    """非致命の警告メッセージを収集する（巨大表など）。"""
    warnings: list[str] = []

    if not isinstance(data, list):
        return warnings

    for idx, slide in enumerate(data, start=1):
        if not isinstance(slide, dict) or slide.get("type") != "table":
            continue
        headers = slide.get("headers") or []
        rows = slide.get("rows") or []
        n_cols = len(headers) if isinstance(headers, list) else 0
        n_rows = len(rows) if isinstance(rows, list) else 0
        if n_cols > schema.TABLE_WARN_COLS or n_cols * n_rows > schema.TABLE_WARN_CELLS:
            warnings.append(
                f"スライド {idx}: この表は大きすぎます（{n_cols}列×{n_rows}行）。"
                "LLMモードでのグラフ化、または手動分割を推奨します。"
            )

    return warnings


def _validate_type_specific(slide: dict[str, Any], prefix: str, slide_type: str) -> list[str]:
    """type 固有の構造制約を検証する。"""
    errors: list[str] = []

    if slide_type == "content":
        two_col = slide.get("twoColumn", False)
        if two_col:
            cols = slide.get("columns")
            if not isinstance(cols, list) or len(cols) != 2:
                errors.append(f"{prefix}: `twoColumn` が true のとき `columns` は 2 要素の配列が必須です。")
            else:
                for ci, col in enumerate(cols, start=1):
                    if not isinstance(col, list):
                        errors.append(f"{prefix}: `columns[{ci - 1}]` は文字列配列である必要があります。")
        else:
            points = slide.get("points")
            if points is not None and not isinstance(points, list):
                errors.append(f"{prefix}: `points` は文字列配列である必要があります。")

    if slide_type == "agenda":
        items = slide.get("items")
        if items is not None:
            if not isinstance(items, list) or len(items) == 0:
                errors.append(f"{prefix}: `items` は 1 件以上の文字列配列が必須です。")

    if slide_type in schema.FIXED_COUNT:
        expected = schema.FIXED_COUNT[slide_type]
        key = "items"
        arr = slide.get(key)
        if arr is not None and isinstance(arr, list) and len(arr) != expected:
            errors.append(f"{prefix}: `{slide_type}` の `{key}` は {expected} 件固定です（現在 {len(arr)} 件）。")

    if slide_type == "kpi":
        items = slide.get("items")
        if isinstance(items, list):
            if len(items) > schema.MAX_COUNT["kpi"]:
                errors.append(f"{prefix}: `kpi` の `items` は最大 {schema.MAX_COUNT['kpi']} 件です。")
            for ii, item in enumerate(items, start=1):
                if not isinstance(item, dict):
                    errors.append(f"{prefix}: `items[{ii - 1}]` はオブジェクトである必要があります。")
                    continue
                for key in ("label", "value", "change", "status"):
                    if key not in item:
                        errors.append(f"{prefix}: `items[{ii - 1}]` に `{key}` が必須です。")
                status = item.get("status")
                if status is not None and status not in schema.STATUS_COLORS:
                    errors.append(
                        f"{prefix}: `items[{ii - 1}].status` は good/bad/neutral のいずれかです。"
                    )

    if slide_type == "barCompare":
        stats = slide.get("stats")
        if isinstance(stats, list):
            for si, stat in enumerate(stats, start=1):
                if not isinstance(stat, dict):
                    errors.append(f"{prefix}: `stats[{si - 1}]` はオブジェクトである必要があります。")
                    continue
                for key in ("label", "leftValue", "rightValue"):
                    if key not in stat:
                        errors.append(f"{prefix}: `stats[{si - 1}]` に `{key}` が必須です。")

    if slide_type == "compare":
        for key in ("leftItems", "rightItems"):
            arr = slide.get(key)
            if arr is not None and not isinstance(arr, list):
                errors.append(f"{prefix}: `{key}` は文字列配列である必要があります。")

    if slide_type == "table":
        headers = slide.get("headers")
        rows = slide.get("rows")
        if isinstance(headers, list) and isinstance(rows, list):
            n_cols = len(headers)
            for ri, row in enumerate(rows, start=1):
                if not isinstance(row, list):
                    errors.append(f"{prefix}: {ri} 番目の行は配列である必要があります。")
                    continue
                if len(row) != n_cols:
                    errors.append(
                        f"{prefix}: {ri} 番目の行の列数がヘッダー（{n_cols}列）と不一致です（{len(row)}列）。"
                    )

    if slide_type == "process":
        steps = slide.get("steps")
        if isinstance(steps, list) and len(steps) > schema.MAX_COUNT["process"]:
            errors.append(f"{prefix}: `process` の `steps` は最大 {schema.MAX_COUNT['process']} 件です。")

    if slide_type == "title":
        date_val = slide.get("date", "")
        if isinstance(date_val, str) and date_val:
            if not re.match(r"^\d{4}\.\d{2}\.\d{2}$", date_val):
                errors.append(f"{prefix}: `date` は YYYY.MM.DD 形式である必要があります。")

    return errors


def _validate_text_rules(slide: dict[str, Any], prefix: str, slide_type: str) -> list[str]:
    """禁止記号・句点・改行・先頭番号を検証する。"""
    errors: list[str] = []

    bullet_fields = _collect_bullet_texts(slide, slide_type)
    header_fields = _collect_header_texts(slide, slide_type)

    for field_path, text in bullet_fields:
        if not isinstance(text, str):
            continue
        if "\n" in text:
            errors.append(f"{prefix}: `{field_path}` に改行を含めないでください。")
        if text.endswith("。"):
            errors.append(f"{prefix}: `{field_path}` の文末に句点「。」を付けないでください。")
        for sym in schema.FORBIDDEN_SYMBOLS:
            if sym in text:
                errors.append(f"{prefix}: `{field_path}` に禁止記号 `{sym}` を含めないでください。")
        if slide_type in schema.AUTO_NUMBER_TYPES and _LEADING_NUMBER_RE.match(text.strip()):
            errors.append(f"{prefix}: `{field_path}` の先頭に番号を含めないでください（自動描画されます）。")

    for field_path, text in header_fields:
        if not isinstance(text, str):
            continue
        if "**" in text or "[[" in text:
            errors.append(f"{prefix}: `{field_path}`（ヘッダー）にインライン強調記法を使わないでください。")

    return errors


def _collect_bullet_texts(slide: dict[str, Any], slide_type: str) -> list[tuple[str, str]]:
    """箇条書き系テキストフィールドを収集する。"""
    result: list[tuple[str, str]] = []

    if slide_type == "content":
        if slide.get("twoColumn"):
            cols = slide.get("columns") or []
            for i, col in enumerate(cols):
                if isinstance(col, list):
                    for j, item in enumerate(col):
                        result.append((f"columns[{i}][{j}]", item))
        else:
            for i, pt in enumerate(slide.get("points") or []):
                result.append((f"points[{i}]", pt))

    if slide_type == "agenda":
        for i, item in enumerate(slide.get("items") or []):
            result.append((f"items[{i}]", item))

    if slide_type in ("compare",):
        for i, item in enumerate(slide.get("leftItems") or []):
            result.append((f"leftItems[{i}]", item))
        for i, item in enumerate(slide.get("rightItems") or []):
            result.append((f"rightItems[{i}]", item))

    if slide_type == "process":
        for i, step in enumerate(slide.get("steps") or []):
            result.append((f"steps[{i}]", step))

    return result


def _collect_header_texts(slide: dict[str, Any], slide_type: str) -> list[tuple[str, str]]:
    """タイトル・サブヘッド等のヘッダーテキストを収集する。"""
    result: list[tuple[str, str]] = []
    for key in ("title", "subhead", "leftTitle", "rightTitle"):
        if key in slide:
            result.append((key, slide[key]))
    if slide_type == "table":
        for i, h in enumerate(slide.get("headers") or []):
            result.append((f"headers[{i}]", h))
    return result
