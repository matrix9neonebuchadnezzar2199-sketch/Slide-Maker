"""第2弾パターンの検証・描画テスト."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import renderer
import validator

PHASE2_SAMPLE = [
    {
        "type": "kpi",
        "title": "主要指標",
        "items": [
            {"label": "売上", "value": "1.2億", "change": "+12%", "status": "good"},
            {"label": "利益率", "value": "18%", "change": "-2pt", "status": "bad"},
            {"label": "顧客数", "value": "3,400", "change": "±0", "status": "neutral"},
        ],
    },
    {
        "type": "barCompare",
        "title": "前年比較",
        "stats": [
            {"label": "売上", "leftValue": "100", "rightValue": "120", "trend": "up"},
            {"label": "コスト", "leftValue": "80", "rightValue": "70", "trend": "down"},
        ],
        "showTrends": True,
    },
    {
        "type": "compare",
        "title": "方式比較",
        "leftTitle": "従来",
        "rightTitle": "新方式",
        "leftItems": ["コスト低", "実績あり"],
        "rightItems": ["高速", "拡張性"],
    },
    {
        "type": "table",
        "title": "実績表",
        "headers": ["項目", "Q1", "Q2"],
        "rows": [["売上", "100", "120"], ["利益", "20", "25"]],
    },
]


def test_phase2_validate_ok() -> None:
    text = json.dumps(PHASE2_SAMPLE, ensure_ascii=False)
    data, errors = validator.validate_json_text(text)
    assert errors == []
    assert data is not None


def test_kpi_invalid_status() -> None:
    bad = [{
        "type": "kpi",
        "title": "KPI",
        "items": [{"label": "a", "value": "1", "change": "x", "status": "unknown"}],
    }]
    errors = validator.validate_slide_data(bad)
    assert any("status" in e for e in errors)


def test_table_column_mismatch() -> None:
    bad = [{
        "type": "table",
        "title": "T",
        "headers": ["A", "B"],
        "rows": [["1", "2", "3"]],
    }]
    errors = validator.validate_slide_data(bad)
    assert any("列数" in e for e in errors)


def test_build_pptx_phase2() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "phase2.pptx"
        renderer.build_pptx(PHASE2_SAMPLE, str(out))
        assert out.is_file()
        assert out.stat().st_size > 2000
