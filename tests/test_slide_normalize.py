"""魔人式 JSON 降格のテスト."""

from __future__ import annotations

import json

import validator


def test_faq_downgrades_to_content_with_warning() -> None:
    payload = [{
        "type": "faq",
        "title": "FAQ",
        "items": [{"q": "質問", "a": "回答"}],
    }]
    data, errors, warnings = validator.validate_json_text(json.dumps(payload, ensure_ascii=False))
    assert errors == []
    assert data is not None
    assert data[0]["type"] == "content"
    assert any("faq" in w for w in warnings)


def test_processList_downgrades_to_content() -> None:
    payload = [{
        "type": "processList",
        "title": "手順",
        "steps": ["調査", "実装"],
    }]
    data, errors, _warnings = validator.validate_json_text(json.dumps(payload, ensure_ascii=False))
    assert errors == []
    assert data is not None
    assert data[0]["type"] == "content"
    assert "調査" in data[0]["points"][0]
