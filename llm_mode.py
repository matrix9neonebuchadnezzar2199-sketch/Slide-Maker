"""LLM 補助 — タイトル短縮（Stage 1）と LLM 全文生成スタブ."""

from __future__ import annotations

import concurrent.futures
import logging
import os
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

import schema

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_LEADING_DECOR_RE = re.compile(
    r"^[\s\d①②③④⑤⑥⑦⑧⑨⑩]+[\.\)、．\s]*|^STEP\s*\d+\s*|^第\d+\s*",
)
_INSTRUCTION_ECHO_RE = re.compile(r"見出し|以下|出力|してください")

_TITLE_FIX_TYPES = frozenset({"content", "table"})
_SKIP_TITLE_TYPES = frozenset({"title", "section", "closing"})

_cached_model: Any | None = None
_model_load_attempted = False

_SYSTEM_PROMPT = (
    "あなたは日本語の見出しを短くする編集者です。"
    "タイトルと本文の要点から、このスライド全体の主題を表す、"
    "15文字以内の簡潔な見出しだけを出力してください。"
    "説明・記号・カギ括弧・句点は付けないでください。"
    "見出し以外は一切出力しないでください。"
)

_SYSTEM_PROMPT_TITLE_ONLY = (
    "あなたは日本語の見出しを短くする編集者です。"
    "入力された文の内容を表す、15文字以内の簡潔な見出しだけを出力してください。"
    "説明・記号・カギ括弧・句点は付けないでください。"
    "見出し以外は一切出力しないでください。"
)


class LlmModeNotImplementedError(Exception):
    """LLM 全文生成モードが未実装であることを示す。"""


def build_slide_data(
    text: str,
    *,
    pdf_stem: str = "",
    cover_title: str | None = None,
) -> list[dict[str, Any]]:
    """LLM で slideData を全文生成する（第4弾で実装予定）。

    Raises:
        LlmModeNotImplementedError: 現時点では常に発生。
    """
    raise LlmModeNotImplementedError(
        "LLM モードは第4弾で実装予定です。ルールベースモードをお使いください。"
    )


def _app_base_dir() -> Path:
    """実行ファイルまたはソースの基準ディレクトリを返す。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resolve_model_path() -> Path | None:
    """利用可能な GGUF モデルパスを解決する。"""
    env_path = os.environ.get("SLIDEMAKER_LLM_MODEL", "").strip()
    if env_path:
        candidate = Path(env_path)
        if candidate.is_file():
            return candidate

    model_dir = _app_base_dir() / "model"
    if model_dir.is_dir():
        ggufs = sorted(model_dir.glob("*.gguf"))
        if ggufs:
            return ggufs[0]
    return None


def load_model(*, force_reload: bool = False) -> Any | None:
    """ローカル GGUF モデルを1回だけロードする。失敗時は None。"""
    global _cached_model, _model_load_attempted

    if _model_load_attempted and not force_reload:
        return _cached_model

    _model_load_attempted = True
    model_path = resolve_model_path()
    if model_path is None:
        logger.info("LLM model not found")
        _cached_model = None
        return None

    try:
        from llama_cpp import Llama
    except ImportError:
        logger.warning("llama-cpp-python is not installed")
        _cached_model = None
        return None

    try:
        _cached_model = Llama(
            model_path=str(model_path),
            n_ctx=2048,
            n_threads=max(1, (os.cpu_count() or 2) - 1),
            verbose=False,
        )
        logger.info("LLM model loaded: %s", model_path)
        return _cached_model
    except Exception as exc:
        logger.warning("LLM model load failed: %s", exc)
        _cached_model = None
        return None


def reset_model_cache() -> None:
    """テスト用 — モデルキャッシュをリセットする。"""
    global _cached_model, _model_load_attempted
    _cached_model = None
    _model_load_attempted = False


def _sanitize_llm_title(text: str) -> str:
    """LLM 出力を見出し用に正規化する。"""
    cleaned = text.strip()
    cleaned = _HTML_TAG_RE.sub("", cleaned)
    cleaned = _LEADING_DECOR_RE.sub("", cleaned).strip()
    for ch in ("「", "」", "『", "』"):
        cleaned = cleaned.strip(ch)
    cleaned = cleaned.rstrip("。、，．")
    for symbol in schema.FORBIDDEN_SYMBOLS:
        cleaned = cleaned.replace(symbol, "")
    return cleaned.strip()


def _is_valid_shortened_title(original: str, candidate: str) -> bool:
    """短縮結果が採用可能かどうか。"""
    if not candidate or len(candidate) <= 1:
        return False
    if len(candidate) > schema.TITLE_SHORTEN_MAX:
        return False
    if candidate == original:
        return False
    if _INSTRUCTION_ECHO_RE.search(candidate) and len(candidate) <= 8:
        return False
    return True


def _build_slide_context(slide: dict[str, Any]) -> str:
    """スライド本文の冒頭を LLM 用の短い文脈文字列にまとめる。"""
    slide_type = slide.get("type", "")
    parts: list[str] = []

    if slide_type == "content":
        for point in slide.get("points", [])[: schema.LLM_TITLE_CONTEXT_POINTS]:
            text = str(point).strip()
            if text:
                parts.append(_HTML_TAG_RE.sub("", text))
    elif slide_type == "table":
        headers = slide.get("headers", [])
        if headers:
            parts.append(" / ".join(str(header).strip() for header in headers if str(header).strip()))
        rows = slide.get("rows", [])
        if rows:
            parts.append(" / ".join(str(cell).strip() for cell in rows[0] if str(cell).strip()))

    context = "\n".join(parts)
    if len(context) > schema.LLM_TITLE_CONTEXT_MAX_CHARS:
        context = context[: schema.LLM_TITLE_CONTEXT_MAX_CHARS].rstrip() + "…"
    return context


def _build_user_prompt(original_title: str, slide_context: str = "") -> tuple[str, str]:
    """文脈の有無に応じた user プロンプトと system プロンプトを返す。"""
    if slide_context.strip():
        user_prompt = (
            "次のスライド内容にふさわしい、15文字以内の見出しを作ってください。\n"
            f"タイトル: {original_title}\n"
            "本文の要点:\n"
            f"{slide_context}\n"
            "見出し:"
        )
        return _SYSTEM_PROMPT, user_prompt

    user_prompt = (
        "次の文を15文字以内の見出しにしてください。\n"
        f"文: {original_title}\n"
        "見出し:"
    )
    return _SYSTEM_PROMPT_TITLE_ONLY, user_prompt


def _call_llm(model: Any, original_title: str, *, slide_context: str = "") -> str:
    """モデルに1件のタイトル短縮を依頼する。"""
    system_prompt, user_prompt = _build_user_prompt(original_title, slide_context)

    def _generate() -> str:
        response = model.create_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=schema.LLM_MAX_TOKENS,
            temperature=schema.LLM_TEMPERATURE,
            top_p=0.9,
            stop=["\n"],
        )
        choice = response["choices"][0]
        message = choice.get("message") or {}
        return str(message.get("content", ""))

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_generate)
        try:
            return future.result(timeout=schema.LLM_TIMEOUT_SEC)
        except concurrent.futures.TimeoutError:
            logger.warning("LLM timeout for title: %s", original_title[:40])
            raise


def shorten_title(
    model: Any | None,
    original_title: str,
    *,
    slide_context: str = "",
) -> str:
    """1件のタイトルを短縮する。失敗時は元タイトルを返す。"""
    if not original_title:
        return original_title
    if len(original_title) <= schema.TITLE_SHORTEN_THRESHOLD:
        return original_title
    if model is None:
        return original_title

    try:
        raw = _call_llm(model, original_title, slide_context=slide_context)
    except Exception as exc:
        logger.warning("LLM shorten failed: %s", exc)
        return original_title

    candidate = _sanitize_llm_title(raw)
    if _is_valid_shortened_title(original_title, candidate):
        return candidate

    logger.info("LLM shorten rejected, fallback to original: %r -> %r", original_title[:40], raw[:40])
    return original_title


def _should_fix_slide(slide: dict[str, Any]) -> bool:
    """タイトル短縮対象スライドかどうか。"""
    slide_type = slide.get("type", "")
    if slide_type in _SKIP_TITLE_TYPES:
        return False
    if slide_type not in _TITLE_FIX_TYPES:
        return False
    title = str(slide.get("title", ""))
    return len(title) > schema.TITLE_SHORTEN_THRESHOLD


def apply_title_fix(
    slide_data: list[dict[str, Any]],
    *,
    progress_callback: Callable[[int, int, str], None] | None = None,
    model: Any | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """slideData の長いタイトルを1件ずつ短縮する。

    Returns:
        (新しい slideData, スキップ理由メッセージ or None)
    """
    result = deepcopy(slide_data)
    targets = [i for i, slide in enumerate(result) if _should_fix_slide(slide)]
    if not targets:
        return result, None

    if model is None:
        model = load_model()
    if model is None:
        return result, "モデル未検出のためLLM補助をスキップしました"

    total = len(targets)
    for step, index in enumerate(targets, start=1):
        slide = result[index]
        original = str(slide.get("title", ""))
        slide_context = _build_slide_context(slide)
        try:
            slide["title"] = shorten_title(model, original, slide_context=slide_context)
        except Exception as exc:
            logger.warning("apply_title_fix slide=%d failed: %s", index, exc)
            slide["title"] = original
        if progress_callback is not None:
            progress_callback(step, total, "タイトル整形中")

    return result, None
