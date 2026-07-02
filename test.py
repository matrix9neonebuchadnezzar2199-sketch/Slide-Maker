"""ユーザー行動を予測した統合テスト — ``python test.py`` で実行."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import json_builder
import llm_mode
import renderer
import rule_mode
import validator
from utils import parse_number

# ---------------------------------------------------------------------------
# シナリオ1: ユーザーが PDF 未選択のまま JSON 生成しようとする（空 JSON 検証）
# ---------------------------------------------------------------------------

def test_user_empty_json_validation_fails() -> None:
    """空 JSON を検証するとエラーになる（UI の検証ボタン相当）。"""
    _, errors, _ = validator.validate_json_text("")
    assert any("空" in e for e in errors)


# ---------------------------------------------------------------------------
# シナリオ2: ユーザーがルールベースで KPI 含むテキストから JSON 生成
# ---------------------------------------------------------------------------

def test_user_rule_mode_generates_kpi_from_business_text() -> None:
    """売上・達成率などが並ぶ文書から kpi スライドが生成される。"""
    text = """# 四半期報告

## 主要指標
- 売上：1,234万円
- 達成率：95%
- 顧客数：3,400件
"""
    slides = rule_mode.build_slide_data(text, pdf_stem="四半期報告")
    types = [s["type"] for s in slides]
    assert "kpi" in types or "content" in types


# ---------------------------------------------------------------------------
# シナリオ3: ユーザーが JSON を手編集して禁止記号を入れる → 検証失敗
# ---------------------------------------------------------------------------

def test_user_edits_json_with_forbidden_arrow() -> None:
    """禁止記号 → を含む JSON は検証で弾かれる。"""
    bad = [{"type": "content", "title": "T", "points": ["A→B"]}]
    errors = validator.validate_slide_data(bad)
    assert any("禁止記号" in e for e in errors)


# ---------------------------------------------------------------------------
# シナリオ4: ユーザーが検証後に PPTX 作成（第1+2弾全パターン）
# ---------------------------------------------------------------------------

def test_user_full_workflow_validate_then_build() -> None:
    """検証通過後に全9パターンの pptx が生成できる。"""
    slides = [
        {"type": "title", "title": "報告", "date": "2026.07.01"},
        {"type": "agenda", "title": "Agenda", "items": ["KPI", "比較"]},
        {"type": "section", "title": "本編", "sectionNo": 1},
        {"type": "content", "title": "概要", "points": ["ポイント1"]},
        {
            "type": "kpi", "title": "KPI",
            "items": [
                {"label": "売上", "value": "100", "change": "+5%", "status": "good"},
            ],
        },
        {
            "type": "barCompare", "title": "比較",
            "stats": [{"label": "A", "leftValue": "10", "rightValue": "20"}],
        },
        {
            "type": "compare", "title": "対比",
            "leftTitle": "旧", "rightTitle": "新",
            "leftItems": ["a"], "rightItems": ["b"],
        },
        {
            "type": "table", "title": "表",
            "headers": ["H1", "H2"], "rows": [["a", "b"]],
        },
        {"type": "closing"},
    ]
    text = json.dumps(slides, ensure_ascii=False, indent=2)
    data, errors, warnings = validator.validate_json_text(text)
    assert errors == [], f"validation failed: {errors}"

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "workflow.pptx"
        renderer.build_pptx(data, str(out))
        assert out.stat().st_size > 3000


# ---------------------------------------------------------------------------
# シナリオ5: AI タイトル対象の判定
# ---------------------------------------------------------------------------

def test_user_ai_title_targets_exclude_cover() -> None:
    """表紙・章扉は AI タイトル対象外、content/table は対象。"""
    import slide_sync

    slides = [
        {"type": "title", "title": "表紙", "date": "2026.01.01"},
        {"type": "content", "title": "A", "points": ["p"]},
        {"type": "table", "title": "B", "headers": ["h"], "rows": [["v"]]},
    ]
    targets = slide_sync.list_ai_title_target_indices(slides)
    assert targets == [1, 2]


# ---------------------------------------------------------------------------
# シナリオ6: ユーザーが表の列数を間違えて編集 → 日本語エラー
# ---------------------------------------------------------------------------

def test_user_table_edit_column_mismatch_message() -> None:
    """列数不一致は日本語で具体的に指摘される。"""
    bad = [{
        "type": "table", "title": "T",
        "headers": ["A", "B", "C"],
        "rows": [["1", "2"]],
    }]
    errors = validator.validate_slide_data(bad)
    assert any("1 番目の行" in e and "列数" in e for e in errors)


# ---------------------------------------------------------------------------
# シナリオ7: parse_number — 日本語ビジネス数値の実用パターン
# ---------------------------------------------------------------------------

def test_user_business_number_formats() -> None:
    """日本語ビジネス文書特有の数値表現を吸収する。"""
    assert parse_number("1,234") == 1234.0
    assert parse_number("▲500") == -500.0
    assert parse_number("約3,000円") == 3000.0
    assert parse_number("12.5%") == 12.5


# ---------------------------------------------------------------------------
# シナリオ8: くら寿司型 — Markdown 表が table になり raw 記法が残らない
# ---------------------------------------------------------------------------

def test_user_markdown_table_to_slide_data() -> None:
    """Markdown 表入力から table スライドが生成され |---| / <br> が残らない。"""
    text = """2026年6月18日

## くら寿司5月度月次情報

|指標|5月|前年比|
|---|---|---|
|全店売上|100|+5%|
|客数|50<br>万件|+3%|

（注）問い合わせ先は広報部
"""
    slides = rule_mode.build_slide_data(text, pdf_stem="くら寿司月次")
    json_text = json.dumps(slides, ensure_ascii=False)

    assert "くら寿司5月度月次情報" in json_text
    assert '"type": "table"' in json_text
    assert "|---|" not in json_text
    assert "<br>" not in json_text.lower()

    title_slide = slides[0]
    assert title_slide["type"] == "title"
    assert title_slide["title"] == "くら寿司月次"
    assert title_slide["title"] != "2026年6月18日"

    table_slides = [s for s in slides if s.get("type") == "table"]
    assert len(table_slides) >= 1
    assert table_slides[0]["headers"][0] == "指標"

    compare_slides = [s for s in slides if s.get("type") == "compare"]
    assert len(compare_slides) == 0

    data, errors, warnings = validator.validate_json_text(json_text)
    assert errors == []


def test_user_title_skips_date_only_content() -> None:
    """日付のみの行が content スライドのタイトルにならない。"""
    text = """2026年6月18日

## 月次報告書
"""
    slides = rule_mode.build_slide_data(text, pdf_stem="fallback")
    content_titles = [s["title"] for s in slides if s.get("type") == "content"]
    assert "2026年6月18日" not in content_titles


def test_user_cover_title_first_h2_not_later_heading() -> None:
    """最初の H2 が表紙になり、後続の H2 は表紙にならない。"""
    text = """2026年6月18日

## くら寿司5月度月次情報

|指標|5月|
|---|---|
|売上|100|

## 1Q

## 年度

## ◎日本・米国・アジア店舗数推移

|国|5月|
|---|---|
|日本|10|
"""
    slides = rule_mode.build_slide_data(text, pdf_stem="fallback")
    assert slides[0]["title"] == "くら寿司5月度月次情報"

    empty_content = [
        s for s in slides
        if s.get("type") == "content" and not s.get("points")
    ]
    assert empty_content == []

    store_table = [s for s in slides if s.get("type") == "table" and "店舗数" in s.get("title", "")]
    assert len(store_table) == 1
    assert store_table[0]["title"] == "◎日本・米国・アジア店舗数推移"

    cover_dup_content = [
        s for s in slides
        if s.get("type") == "content" and s.get("title") == "くら寿司5月度月次情報"
    ]
    assert cover_dup_content == []


def test_user_cover_title_plain_text_before_table() -> None:
    """## 無しのプレーンテキストタイトル + 表セル由来 ## 1Q 等を正しく処理。"""
    text = """2026年6月18日
くら寿司5月度月次情報
|指標|5月|
|---|---|
|売上|100|

## 1Q

## 年度 11月 12月 1月

## 2月

## ◎日本・米国・アジア店舗数推移

|国|5月|
|---|---|
|日本|10|
"""
    slides = rule_mode.build_slide_data(text, pdf_stem="fallback")
    assert slides[0]["title"] == "くら寿司5月度月次情報"
    store_table = [s for s in slides if s.get("type") == "table" and "店舗数" in s.get("title", "")]
    assert len(store_table) == 1
    assert store_table[0]["title"] == "◎日本・米国・アジア店舗数推移"


def test_user_cover_title_user_override() -> None:
    """ユーザー指定の表紙タイトルが最優先で反映される。"""
    text = """## 誤タイトル

|A|B|
|---|---|
|1|2|
"""
    slides = rule_mode.build_slide_data(
        text,
        pdf_stem="fallback",
        cover_title="くら寿司5月度月次情報",
    )
    assert slides[0]["title"] == "くら寿司5月度月次情報"


def test_user_kpi_not_generated_from_prose_percentages() -> None:
    """文章に散在する％から kpi が暴発しない。"""
    text = """## 経済動向

政府は、景気の現状について報告した。
物価は総じて1.0％程度で推移している。
２％の物価安定目標に向けて政策を継続する。
前期比0.3％増となった。
"""
    slides = rule_mode.build_slide_data(text, pdf_stem="月例経済報告")
    assert not any(s.get("type") == "kpi" for s in slides)
    assert any(s.get("type") == "content" for s in slides)


def test_user_h4_heading_markers_stripped_from_points() -> None:
    """H4 見出し記号が content points に残らない。"""
    text = """## 報告

#### 令和８年６月30日
- 景気は緩やかに回復している。
"""
    slides = rule_mode.build_slide_data(text, pdf_stem="fallback")
    content = [s for s in slides if s.get("type") == "content"]
    assert content
    joined = json.dumps(content, ensure_ascii=False)
    assert "####" not in joined
    assert "令和８年６月30日" in joined


def test_user_html_tags_stripped_from_json() -> None:
    """見出し・本文・表セルの HTML タグが JSON に残らない。"""
    text = """## <u>個人消費は、持ち直しの動きがみられる。</u>

- <b>雇用情勢</b>は改善している。

## 表

|項目|内容|
|---|---|
|<u>消費</u>|持ち直し<br>継続|
"""
    slides = rule_mode.build_slide_data(text, pdf_stem="fallback")
    joined = json.dumps(slides, ensure_ascii=False)
    assert "<u>" not in joined
    assert "</u>" not in joined
    assert "<b>" not in joined
    assert "<br>" not in joined.lower()
    assert "個人消費は、持ち直しの動きがみられる。" in joined
    assert "持ち直し 継続" in joined


def run_all() -> int:
    """全シナリオを実行し、失敗数を返す。"""
    tests = [
        test_user_empty_json_validation_fails,
        test_user_rule_mode_generates_kpi_from_business_text,
        test_user_edits_json_with_forbidden_arrow,
        test_user_full_workflow_validate_then_build,
        test_user_ai_title_targets_exclude_cover,
        test_user_table_edit_column_mismatch_message,
        test_user_business_number_formats,
        test_user_markdown_table_to_slide_data,
        test_user_title_skips_date_only_content,
        test_user_cover_title_first_h2_not_later_heading,
        test_user_cover_title_plain_text_before_table,
        test_user_cover_title_user_override,
        test_user_kpi_not_generated_from_prose_percentages,
        test_user_h4_heading_markers_stripped_from_points,
        test_user_html_tags_stripped_from_json,
    ]
    failed = 0
    for fn in tests:
        name = fn.__name__
        try:
            fn()
            print(f"  OK  {name}")
        except Exception as exc:
            print(f"  FAIL {name}: {exc}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return failed


if __name__ == "__main__":
    print("Slide-Maker user flow tests\n")
    sys.exit(1 if run_all() else 0)
