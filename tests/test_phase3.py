"""第3弾パターンの検証・描画テスト."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import renderer
import validator

PHASE3_SAMPLE = [
    {
        "type": "process",
        "title": "導入フロー",
        "subhead": "4ステップまで",
        "steps": ["要件整理", "設計", "実装", "検証"],
        "notes": "導入フローを説明します",
    },
    {
        "type": "timeline",
        "title": "ロードマップ",
        "milestones": [
            {"label": "PoC完了", "date": "2026 Q1"},
            {"label": "本番移行", "date": "2026 Q3"},
        ],
    },
    {
        "type": "cycle",
        "title": "PDCA",
        "items": [
            {"label": "Plan", "subLabel": "計画"},
            {"label": "Do", "subLabel": "実行"},
            {"label": "Check", "subLabel": "評価"},
            {"label": "Act", "subLabel": "改善"},
        ],
        "centerText": "継続改善",
    },
    {
        "type": "pyramid",
        "title": "優先度",
        "levels": [
            {"title": "最優先", "description": "売上直結"},
            {"title": "重要", "description": "効率化"},
            {"title": "保留", "description": "将来検討"},
        ],
    },
    {
        "type": "triangle",
        "title": "3要素",
        "items": [
            {"title": "品質", "desc": "安定"},
            {"title": "速度", "desc": "迅速"},
            {"title": "コスト", "desc": "最適"},
        ],
    },
]


def test_phase3_validate_ok() -> None:
    text = json.dumps(PHASE3_SAMPLE, ensure_ascii=False)
    data, errors, warnings = validator.validate_json_text(text)
    assert errors == []
    assert data is not None
    assert len(data) == 5


def test_pyramid_too_few_levels() -> None:
    bad = [{
        "type": "pyramid",
        "title": "T",
        "levels": [{"title": "a", "description": "b"}],
    }]
    errors = validator.validate_slide_data(bad)
    assert any("levels" in e for e in errors)


def test_cycle_wrong_count() -> None:
    bad = [{
        "type": "cycle",
        "title": "T",
        "items": [{"label": "a"}, {"label": "b"}],
    }]
    errors = validator.validate_slide_data(bad)
    assert any("4 件固定" in e for e in errors)


def test_build_pptx_phase3() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "phase3.pptx"
        renderer.build_pptx(PHASE3_SAMPLE, str(out))
        assert out.is_file()
        assert out.stat().st_size > 2000
