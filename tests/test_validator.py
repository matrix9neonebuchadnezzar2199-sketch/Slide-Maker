"""validator / renderer の単体テスト."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import renderer
import validator

SAMPLE_SLIDES = [
    {"type": "title", "title": "テスト資料", "date": "2026.07.01"},
    {"type": "agenda", "title": "アジェンダ", "items": ["背景", "課題", "提案"]},
    {"type": "section", "title": "背景", "sectionNo": 1},
    {
        "type": "content",
        "title": "現状",
        "points": ["市場は拡大中", "[[重要]]な変化がある", "**強調**ポイント"],
    },
    {"type": "closing"},
]


def test_validate_sample_ok() -> None:
    text = json.dumps(SAMPLE_SLIDES, ensure_ascii=False)
    data, errors, warnings = validator.validate_json_text(text)
    assert errors == []
    assert data is not None
    assert len(data) == 5


def test_validate_forbidden_symbol() -> None:
    bad = [{"type": "content", "title": "T", "points": ["矢印→禁止"]}]
    errors = validator.validate_slide_data(bad)
    assert any("禁止記号" in e for e in errors)


def test_huge_table_warning() -> None:
    """巨大表は警告を返すが検証は通過する。"""
    huge = [{
        "type": "table",
        "title": "大表",
        "headers": [f"C{i}" for i in range(10)],
        "rows": [[str(j) for j in range(10)] for _ in range(10)],
    }]
    errors = validator.validate_slide_data(huge)
    assert errors == []
    warnings = validator.collect_warnings(huge)
    assert any("大きすぎます" in w for w in warnings)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "test.pptx"
        renderer.build_pptx(SAMPLE_SLIDES, str(out))
        assert out.is_file()
        assert out.stat().st_size > 1000
