"""LLM タイトル短縮補助のユニットテスト（モデル本体は呼ばない）."""

from __future__ import annotations

from unittest.mock import patch

import llm_mode
import schema

# 閾値(30)を確実に超える見出し
_LONG_CONTENT_TITLE = "国内経済の概況について詳細に説明するための非常に長い見出しタイトル例です"
_LONG_TABLE_TITLE = "主要指標の前年同月比と推移を一覧で示すための長いテーブル見出し例です"
_LONG_COVER_TITLE = "これは表紙で非常に長いタイトルですが絶対に変更してはいけない見出し例です"
_LONG_SECTION_TITLE = "これも三十文字を絶対に超えるセクション見出しですが対象外の見出し例です"
_LONG_CLOSING_TITLE = "これは三十文字を絶対に超えるクロージング見出しですが対象外の見出し例です"


class _MockModel:
    """create_chat_completion をモックする最小 LLM。"""

    def __init__(self, response: str = "短い見出し") -> None:
        self.response = response
        self.call_count = 0
        self.last_messages: list[dict[str, str]] = []

    def create_chat_completion(self, **kwargs) -> dict:
        self.call_count += 1
        self.last_messages = kwargs.get("messages", [])
        return {"choices": [{"message": {"content": self.response}}]}


class _FailingModel:
    """常に例外を投げるモック。"""

    def create_chat_completion(self, **kwargs) -> dict:
        raise RuntimeError("mock failure")


def test_short_title_skips_llm() -> None:
    """閾値以下のタイトルは LLM を呼ばない。"""
    model = _MockModel("置換")
    original = "短いタイトル"
    result = llm_mode.shorten_title(model, original)
    assert result == original
    assert model.call_count == 0


def test_long_title_shortened_on_success() -> None:
    """長いタイトルは成功時のみ短縮される。"""
    model = _MockModel("国内経済の概況")
    original = "国内経済の概況について詳細に説明するための長い見出しタイトルです"
    result = llm_mode.shorten_title(model, original)
    assert result == "国内経済の概況"
    assert model.call_count == 1


def test_llm_failure_falls_back_to_original() -> None:
    """LLM 例外時は元タイトルに戻る。"""
    model = _FailingModel()
    original = "これは三十文字を超える非常に長いタイトル見出しの例です"
    result = llm_mode.shorten_title(model, original)
    assert result == original


def test_invalid_llm_output_falls_back() -> None:
    """空・長すぎ・指示文復唱は元タイトルに戻る。"""
    model = _MockModel("見出し")
    original = "これは三十文字を超える非常に長いタイトル見出しの例です"
    result = llm_mode.shorten_title(model, original)
    assert result == original


def test_build_slide_context_from_content_points() -> None:
    """content の points 冒頭を文脈として抽出する。"""
    slide = {
        "type": "content",
        "title": "長いタイトル",
        "points": ["消費は底堅い", "設備投資は増加", "第三の要点"],
    }
    context = llm_mode._build_slide_context(slide)
    assert "消費は底堅い" in context
    assert "設備投資は増加" in context
    assert "第三の要点" not in context


def test_build_slide_context_from_table_headers_and_row() -> None:
    """table は headers と先頭行を文脈として使う。"""
    slide = {
        "type": "table",
        "title": "長いタイトル",
        "headers": ["項目", "値"],
        "rows": [["売上", "100"], ["利益", "20"]],
    }
    context = llm_mode._build_slide_context(slide)
    assert "項目 / 値" in context
    assert "売上 / 100" in context
    assert "利益" not in context


def test_shorten_title_includes_context_in_prompt() -> None:
    """points 文脈があるときは主題見出しプロンプトを使う。"""
    model = _MockModel("消費動向")
    original = "国内経済の概況について詳細に説明するための非常に長い見出しタイトル例です"
    llm_mode.shorten_title(
        model,
        original,
        slide_context="消費は底堅く、設備投資は増加傾向",
    )
    user_prompt = model.last_messages[1]["content"]
    system_prompt = model.last_messages[0]["content"]
    assert "本文の要点" in user_prompt
    assert "消費は底堅く" in user_prompt
    assert "このスライド全体の主題" in system_prompt


def test_sanitize_strips_html_and_symbols() -> None:
    """サニタイズで HTML と禁止記号を除去する。"""
    raw = "<u>■</u>テスト見出し。"
    cleaned = llm_mode._sanitize_llm_title(raw)
    assert "<" not in cleaned
    assert "■" not in cleaned
    assert cleaned.endswith("見出し")


def test_apply_title_fix_skips_cover_section_closing() -> None:
    """表紙・section・closing は変更しない。"""
    slides = [
        {"type": "title", "title": _LONG_COVER_TITLE},
        {"type": "section", "title": _LONG_SECTION_TITLE},
        {
            "type": "content",
            "title": _LONG_CONTENT_TITLE,
            "points": ["a"],
        },
        {"type": "closing", "title": _LONG_CLOSING_TITLE},
    ]
    model = _MockModel("短縮後")
    result, status = llm_mode.apply_title_fix(slides, model=model)
    assert status is None
    assert result[0]["title"] == slides[0]["title"]
    assert result[1]["title"] == slides[1]["title"]
    assert result[2]["title"] == "短縮後"
    assert result[3]["title"] == slides[3]["title"]
    assert model.call_count == 1


def test_apply_title_fix_without_model_returns_skip_message() -> None:
    """モデル未ロード時は全体をスキップし理由を返す。"""
    slides = [
        {
            "type": "content",
            "title": _LONG_CONTENT_TITLE,
            "points": ["a"],
        },
    ]
    llm_mode.reset_model_cache()
    with patch.object(llm_mode, "load_model", return_value=None):
        result, status = llm_mode.apply_title_fix(slides)
    assert status == "モデル未検出のためLLM補助をスキップしました"
    assert result[0]["title"] == slides[0]["title"]


def test_apply_title_fix_progress_callback() -> None:
    """進捗コールバックが対象件数分呼ばれる。"""
    slides = [
        {
            "type": "content",
            "title": _LONG_CONTENT_TITLE,
            "points": ["a"],
        },
        {
            "type": "table",
            "title": _LONG_TABLE_TITLE,
            "headers": ["h"],
            "rows": [["v"]],
        },
    ]
    model = _MockModel("短縮")
    progress: list[tuple[int, int, str]] = []

    def on_progress(current: int, total: int, message: str) -> None:
        progress.append((current, total, message))

    llm_mode.apply_title_fix(slides, model=model, progress_callback=on_progress)
    assert progress == [(1, 2, "タイトル整形中"), (2, 2, "タイトル整形中")]


def test_resolve_model_path_from_env(tmp_path, monkeypatch) -> None:
    """環境変数でモデルパスを解決できる。"""
    gguf = tmp_path / "test.gguf"
    gguf.write_bytes(b"fake")
    monkeypatch.setenv("SLIDEMAKER_LLM_MODEL", str(gguf))
    assert llm_mode.resolve_model_path() == gguf


def test_resolve_model_path_prefers_default_gemma(tmp_path, monkeypatch) -> None:
    """既定 Gemma モデルが model/*.gguf の先頭より優先される。"""
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    other = model_dir / "aaa-other.gguf"
    other.write_bytes(b"fake")
    default = model_dir / schema.LLM_DEFAULT_MODEL_NAME
    default.write_bytes(b"fake")

    monkeypatch.delenv("SLIDEMAKER_LLM_MODEL", raising=False)
    with patch.object(llm_mode, "_app_base_dir", return_value=tmp_path):
        assert llm_mode.resolve_model_path() == default


def test_resolve_model_path_falls_back_to_any_gguf(tmp_path, monkeypatch) -> None:
    """既定モデルが無い場合は model/*.gguf の先頭を使う。"""
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    only = model_dir / "backup-model.gguf"
    only.write_bytes(b"fake")

    monkeypatch.delenv("SLIDEMAKER_LLM_MODEL", raising=False)
    with patch.object(llm_mode, "_app_base_dir", return_value=tmp_path):
        assert llm_mode.resolve_model_path() == only


def test_build_llama_load_kwargs_low_memory() -> None:
    """低メモリ llama-cpp 引数が schema 定数と一致する。"""
    kwargs = llm_mode.build_llama_load_kwargs("/path/to/model.gguf")
    assert kwargs["model_path"] == "/path/to/model.gguf"
    assert kwargs["n_ctx"] == schema.LLM_N_CTX
    assert kwargs["n_threads"] == schema.LLM_N_THREADS
    assert kwargs["n_batch"] == schema.LLM_N_BATCH
    assert kwargs["n_ubatch"] == schema.LLM_N_UBATCH
    assert kwargs["n_gpu_layers"] == schema.LLM_N_GPU_LAYERS
    assert kwargs["type_k"] == schema.LLM_KV_CACHE_TYPE
    assert kwargs["type_v"] == schema.LLM_KV_CACHE_TYPE
    assert kwargs["verbose"] is False


def test_load_model_uses_low_memory_kwargs(tmp_path, monkeypatch) -> None:
    """load_model は低メモリ kwargs で Llama を呼ぶ。"""
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    gguf = model_dir / schema.LLM_DEFAULT_MODEL_NAME
    gguf.write_bytes(b"fake")

    llm_mode.reset_model_cache()
    monkeypatch.delenv("SLIDEMAKER_LLM_MODEL", raising=False)

    captured: dict[str, object] = {}

    class _FakeLlama:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    with patch.object(llm_mode, "_app_base_dir", return_value=tmp_path):
        with patch.dict("sys.modules", {"llama_cpp": type("M", (), {"Llama": _FakeLlama})()}):
            with patch("llm_mode.Llama", _FakeLlama, create=True):
                # _load_llama_with_fallback 内の import を直接パッチ
                with patch.object(llm_mode, "_load_llama_with_fallback", side_effect=lambda p: _FakeLlama(**llm_mode.build_llama_load_kwargs(p))):
                    model = llm_mode.load_model(force_reload=True)

    assert model is not None
    assert captured["n_ctx"] == schema.LLM_N_CTX
    assert captured["n_threads"] == schema.LLM_N_THREADS
    assert captured["n_gpu_layers"] == 0
    llm_mode.reset_model_cache()


def test_apply_ai_titles_skips_cover_section_closing() -> None:
    """apply_ai_titles は表紙・section・closing を変更しない。"""
    slides = [
        {"type": "title", "title": _LONG_COVER_TITLE, "date": "2026.01.01"},
        {"type": "section", "title": _LONG_SECTION_TITLE},
        {"type": "content", "title": "旧", "points": ["消費は底堅い"]},
        {"type": "closing"},
    ]
    model = _MockModel("生成タイトル")
    ready: list[tuple[int, str]] = []

    def on_ready(index: int, title: str) -> None:
        ready.append((index, title))

    result, status = llm_mode.apply_ai_titles(slides, model=model, title_ready_callback=on_ready)
    assert status is None
    assert result[0]["title"] == slides[0]["title"]
    assert result[1]["title"] == slides[1]["title"]
    assert result[2]["title"] == "生成タイトル"
    assert "title" not in result[3]
    assert ready == [(2, "生成タイトル")]
    assert model.call_count == 1


def test_apply_ai_titles_without_model_returns_skip_message() -> None:
    """モデル未ロード時はスキップ理由を返す。"""
    slides = [{"type": "content", "title": "T", "points": ["a"]}]
    llm_mode.reset_model_cache()
    with patch.object(llm_mode, "load_model", return_value=None):
        result, status = llm_mode.apply_ai_titles(slides)
    assert status == "モデル未検出のためAIタイトル生成をスキップしました"
    assert result[0]["title"] == "T"


def test_generate_title_from_slide_uses_body_context() -> None:
    """本文要点を含むプロンプトでタイトルを生成する。"""
    model = _MockModel("消費動向")
    slide = {"type": "content", "title": "長い旧タイトル", "points": ["消費は底堅い"]}
    title = llm_mode.generate_title_from_slide(model, slide)
    assert title == "消費動向"
    assert "本文の要点" in model.last_messages[1]["content"]


def test_threshold_constants_match_spec() -> None:
    """schema 定数が SPEC と一致する。"""
    assert len(_LONG_CONTENT_TITLE) > schema.TITLE_SHORTEN_THRESHOLD
    assert schema.TITLE_SHORTEN_THRESHOLD == 30
    assert schema.TITLE_SHORTEN_MAX == 20
    assert schema.LLM_TIMEOUT_SEC == 15
    assert schema.LLM_DEFAULT_MODEL_NAME == "gemma-4-E2B-it-qat-UD-Q2_K_XL.gguf"
    assert schema.LLM_N_CTX == 1000
    assert schema.LLM_N_THREADS == 2
