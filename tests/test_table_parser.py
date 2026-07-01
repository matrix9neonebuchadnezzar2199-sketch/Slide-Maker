"""Markdown 表パーサーのテスト."""

from __future__ import annotations

from table_parser import detect_markdown_tables, parse_markdown_table_block


def test_parse_markdown_table_with_separator() -> None:
    lines = [
        "|全店|Q1|Q2|",
        "|---|---|---|",
        "|売上|100|120|",
        "|客数|50<br>件|55|",
    ]
    result = parse_markdown_table_block(lines)
    assert result is not None
    assert result["headers"] == ["全店", "Q1", "Q2"]
    assert result["rows"][0] == ["売上", "100", "120"]
    assert "<br>" not in result["rows"][1][1]


def test_detect_excludes_table_lines_from_remaining() -> None:
    lines = [
        "前文",
        "|A|B|",
        "|---|---|",
        "|1|2|",
        "後文",
    ]
    tables, remaining = detect_markdown_tables(lines)
    assert len(tables) == 1
    assert "前文" in remaining
    assert "後文" in remaining
    assert not any("|---" in ln for ln in remaining)
