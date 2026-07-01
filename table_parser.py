"""Markdown / タブ区切り表の検出・パース."""

from __future__ import annotations

import re
from typing import Any

_MD_TABLE_ROW_RE = re.compile(r"^\s*\|.+\|\s*$")
_MD_SEP_ROW_RE = re.compile(r"^\s*\|[\s\-:|\u2014]+\|\s*$")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def is_markdown_table_row(line: str) -> bool:
    """行が Markdown テーブル行かどうか。"""
    return bool(_MD_TABLE_ROW_RE.match(line))


def is_separator_row(line: str) -> bool:
    """`|---|---|` 形式の区切り行かどうか。"""
    return bool(_MD_SEP_ROW_RE.match(line))


def clean_cell(text: str) -> str:
    """セル内の HTML・余白を除去する。"""
    cleaned = _BR_RE.sub(" ", text)
    return cleaned.strip()


def parse_pipe_row(line: str) -> list[str]:
    """パイプ区切り行をセル配列に変換する。"""
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [clean_cell(c) for c in inner.split("|")]


def compress_empty_columns(headers: list[str], rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    """全行が空の列を除去する。"""
    if not headers:
        return headers, rows
    keep = []
    for ci in range(len(headers)):
        col_vals = [headers[ci]] + [row[ci] if ci < len(row) else "" for row in rows]
        if any(v.strip() for v in col_vals):
            keep.append(ci)
    if not keep:
        return headers, rows
    new_headers = [headers[i] for i in keep]
    new_rows = [[row[i] if i < len(row) else "" for i in keep] for row in rows]
    return new_headers, new_rows


def parse_markdown_table_block(lines: list[str]) -> dict[str, Any] | None:
    """Markdown テーブル行ブロックを table スライド dict に変換する。

    Args:
        lines: 連続する ``|...|`` 行のリスト。

    Returns:
        table スライド dict。パース不能時は None。
    """
    if len(lines) < 2:
        return None

    parsed_rows = [parse_pipe_row(ln) for ln in lines]
    if not parsed_rows:
        return None

    headers: list[str]
    data_rows: list[list[str]]

    if is_separator_row(lines[1]):
        headers = parsed_rows[0]
        data_rows = parsed_rows[2:]
    elif is_separator_row(lines[0]):
        headers = parsed_rows[1] if len(parsed_rows) > 1 else []
        data_rows = parsed_rows[2:]
    else:
        headers = parsed_rows[0]
        data_rows = parsed_rows[1:]

    headers = [h for h in headers]
    if len(headers) < 2:
        return None

    # 行の列数をヘッダーに揃える
    normalized: list[list[str]] = []
    for row in data_rows:
        if is_separator_row("|".join(row)):
            continue
        cells = list(row)
        while len(cells) < len(headers):
            cells.append("")
        normalized.append(cells[: len(headers)])

    headers, normalized = compress_empty_columns(headers, normalized)
    if len(headers) < 2:
        return None

    return {
        "type": "table",
        "headers": headers,
        "rows": normalized,
    }


def detect_markdown_tables(
    lines: list[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    """行走査で Markdown テーブルを検出し、残りの行を返す。

    Args:
        lines: ブロック内の全行。

    Returns:
        (table_dicts, remaining_lines) — table_dicts は headers/rows のみ（title 未設定）。
    """
    tables: list[dict[str, Any]] = []
    remaining: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not is_markdown_table_row(line):
            remaining.append(line)
            i += 1
            continue

        block: list[str] = []
        while i < len(lines) and is_markdown_table_row(lines[i]):
            block.append(lines[i])
            i += 1

        parsed = parse_markdown_table_block(block)
        if parsed:
            tables.append(parsed)
        else:
            remaining.extend(block)

    return tables, remaining
