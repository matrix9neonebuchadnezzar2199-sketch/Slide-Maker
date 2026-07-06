"""LLM 補助 — タイトル短縮（Stage 1）と LLM 全文生成スタブ."""

from __future__ import annotations

import concurrent.futures
import gc
import logging
import os
import re
import sys
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

import schema
import slide_sync

try:
    import llama_server
except ImportError:
    llama_server = None  # type: ignore[assignment]

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
_load_lock = threading.Lock()

_SYSTEM_PROMPT = (
    "あなたは日本語の見出しを短くする編集者です。"
    "タイトルと本文の要点から、このスライド全体の主題を表す、"
    "15文字以内の簡潔な見出しだけを出力してください。"
    "説明・記号・カギ括弧・句点は付けないでください。"
    "見出し以外は一切出力しないでください。"
)

_SYSTEM_PROMPT_GENERATE = (
    "あなたは日本語のプレゼン資料編集者です。"
    "スライド本文の要点から、そのスライド全体の主題を表す、"
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

_SYSTEM_PROMPT_SUBHEAD = (
    "あなたは日本語のプレゼン資料編集者です。"
    "スライドタイトルと本文要点から、全角50文字以内の小見出しを1行だけ出力してください。"
    "説明・記号・句点は付けないでください。小見出し以外は出力しないでください。"
)

_SYSTEM_PROMPT_NOTES = (
    "あなたはプレゼン原稿を書く編集者です。"
    "スライド内容に基づき、発表者が話す原稿を2〜3文のプレーンテキストで出力してください。"
    "マークダウン記法（**太字**、[[強調]]等）は使わないでください。"
)

_SYSTEM_PROMPT_RECLASSIFY = (
    "あなたはスライドレイアウト選定者です。"
    "与えられた箇条書きに最適な表現を1語だけ選び、"
    "timeline / process / cycle / pyramid / content のいずれか1語のみ出力してください。"
)

_RECLASSIFY_ALLOWED = frozenset({"timeline", "process", "cycle", "pyramid", "content"})
_NOTES_MARKUP_RE = re.compile(r"\*\*([^*]+)\*\*|\[\[([^\]]+)\]\]")


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
    """利用可能な GGUF モデルパスを解決する。

    優先順: 環境変数 ``SLIDEMAKER_LLM_MODEL`` → 既定 ``model/gemma-4-E2B-it-qat-UD-Q2_K_XL.gguf``
    → ``model/*.gguf`` の先頭。
    """
    env_path = os.environ.get("SLIDEMAKER_LLM_MODEL", "").strip()
    base_dir = _app_base_dir()
    model_dir = base_dir / "model"
    default_model = model_dir / schema.LLM_DEFAULT_MODEL_NAME
    ggufs = sorted(model_dir.glob("*.gguf")) if model_dir.is_dir() else []

    

    if env_path:
        candidate = Path(env_path)
        if candidate.is_file():
            
            return candidate

    model_dir = base_dir / "model"
    if not model_dir.is_dir():
        
        return None

    default_model = model_dir / schema.LLM_DEFAULT_MODEL_NAME
    if default_model.is_file():
        
        return default_model

    ggufs = sorted(model_dir.glob("*.gguf"))
    if ggufs:
        
        return ggufs[0]
    
    return None


def build_llama_load_kwargs(model_path: str | Path) -> dict[str, Any]:
    """低メモリ llama-cpp-python ロード引数を返す（Glaux 節約設定準拠）。"""
    kv_type = _kv_cache_type_id(schema.LLM_KV_CACHE_TYPE)
    return {
        "model_path": str(model_path),
        "n_ctx": int(schema.LLM_N_CTX),
        "n_threads": int(schema.LLM_N_THREADS),
        "n_batch": int(schema.LLM_N_BATCH),
        "n_ubatch": int(schema.LLM_N_UBATCH),
        "n_gpu_layers": int(schema.LLM_N_GPU_LAYERS),
        "type_k": kv_type,
        "type_v": kv_type,
        "op_offload": bool(schema.LLM_OP_OFFLOAD),
        "use_mmap": bool(schema.LLM_USE_MMAP),
        "use_mlock": bool(schema.LLM_USE_MLOCK),
        "verbose": False,
    }


def _kv_cache_type_id(type_name: str) -> int:
    """KV キャッシュ型名（q8_0 等）を llama_cpp 定数に変換する。"""
    from llama_cpp import llama_cpp

    table = {
        "q8_0": llama_cpp.GGML_TYPE_Q8_0,
        "q4_0": llama_cpp.GGML_TYPE_Q4_0,
        "f16": llama_cpp.GGML_TYPE_F16,
    }
    return table.get(type_name.lower(), llama_cpp.GGML_TYPE_Q8_0)


def _llama_load_tiers(model_path: Path) -> list[tuple[str, dict[str, Any]]]:
    """Glaux 準拠の段階的ロード引数（未対応キーは次ティアへ）。"""
    full = build_llama_load_kwargs(model_path)
    mid = {
        key: value
        for key, value in full.items()
        if key not in ("type_k", "type_v", "n_ubatch", "op_offload")
    }
    minimal = {
        "model_path": str(model_path),
        "n_ctx": int(schema.LLM_N_CTX),
        "n_threads": int(schema.LLM_N_THREADS),
        "n_gpu_layers": int(schema.LLM_N_GPU_LAYERS),
        "use_mmap": bool(schema.LLM_USE_MMAP),
        "verbose": False,
    }
    return [("full", full), ("mid", mid), ("minimal", minimal)]


def _ensure_llama_dll_paths() -> None:
    """frozen EXE で llama_cpp / MSVC DLL を探索できるようにする。"""
    if not getattr(sys, "frozen", False):
        return
    meipass = getattr(sys, "_MEIPASS", "")
    if not meipass:
        return
    if hasattr(os, "add_dll_directory"):
        for sub in ("", "llama_cpp", "llama_cpp/lib"):
            path = os.path.join(meipass, sub) if sub else meipass
            if os.path.isdir(path):
                os.add_dll_directory(path)  # type: ignore[attr-defined]


def _load_llama_with_fallback(model_path: Path) -> Any:
    """低メモリ設定で Llama をロードする。未対応引数は段階的に削って再試行。"""
    from llama_cpp import Llama

    _ensure_llama_dll_paths()
    gc.collect()

    last_exc: Exception | None = None
    for tier_name, kwargs in _llama_load_tiers(model_path):
        try:
            model = Llama(**kwargs)
            
            logger.info("LLM loaded with tier=%s keys=%s", tier_name, sorted(kwargs.keys()))
            return model
        except TypeError as exc:
            last_exc = exc
            logger.warning("LLM tier %s TypeError, trying next: %s", tier_name, exc)
            
        except Exception as exc:
            last_exc = exc
            logger.warning("LLM tier %s failed: %s", tier_name, exc)
            

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("LLM load failed: no tiers available")


def load_model(*, force_reload: bool = False) -> Any | None:
    """ローカル GGUF モデルを1回だけロードする。失敗時は None。"""
    global _cached_model, _model_load_attempted

    with _load_lock:
        if not force_reload:
            if _cached_model is not None:
                return _cached_model
            if _model_load_attempted:
                return _cached_model

        _model_load_attempted = True
        model_path = resolve_model_path()
        if model_path is None:
            logger.info("LLM model not found")
            
            _cached_model = None
            return None

        # Glaux 同等: llama-server 子プロセスを優先（frozen 配布はこちらのみ）
        if llama_server is not None and llama_server.resolve_server_exe() is not None:
            try:
                _cached_model = llama_server.start_server(model_path)
                logger.info(
                    "LLM server started (Glaux low-memory): %s ctx=%d threads=%d",
                    model_path,
                    schema.LLM_N_CTX,
                    schema.LLM_N_THREADS,
                )
                
                return _cached_model
            except Exception as exc:
                logger.warning("LLM server start failed: %s", exc)
                
                _cached_model = None
                return None

        # 開発用フォールバック: in-process llama-cpp-python
        try:
            from llama_cpp import Llama  # noqa: F401 — インストール確認
        except (ImportError, OSError, FileNotFoundError) as exc:
            logger.warning("llama-cpp-python is not available: %s", exc)
            
            _cached_model = None
            return None

        try:
            _cached_model = _load_llama_with_fallback(model_path)
            logger.info(
                "LLM model loaded (embedded low-memory): %s ctx=%d threads=%d",
                model_path,
                schema.LLM_N_CTX,
                schema.LLM_N_THREADS,
            )
            
            return _cached_model
        except Exception as exc:
            logger.warning("LLM model load failed: %s", exc)
            
            _cached_model = None
            return None


def reset_model_cache() -> None:
    """テスト用 — モデルキャッシュをリセットする。"""
    global _cached_model, _model_load_attempted
    with _load_lock:
        _cached_model = None
        _model_load_attempted = False


def unload_model() -> None:
    """ロード済み LLM を解放する（アプリ終了時）。"""
    global _cached_model, _model_load_attempted
    with _load_lock:
        if _cached_model is not None:
            close_fn = getattr(_cached_model, "close", None)
            if callable(close_fn):
                try:
                    close_fn()
                except Exception as exc:
                    logger.warning("LLM model close failed: %s", exc)
            _cached_model = None
        _model_load_attempted = False
    gc.collect()
    logger.info("LLM model unloaded")


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


def _is_valid_generated_title(candidate: str) -> bool:
    """AI 生成タイトルが採用可能かどうか。"""
    if not candidate or len(candidate) <= 1:
        return False
    if len(candidate) > schema.TITLE_SHORTEN_MAX:
        return False
    if _INSTRUCTION_ECHO_RE.search(candidate) and len(candidate) <= 8:
        return False
    return True


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
    elif slide_type == "process":
        parts.extend(str(step).strip() for step in slide.get("steps", [])[: schema.LLM_TITLE_CONTEXT_POINTS])
    elif slide_type == "timeline":
        for milestone in slide.get("milestones", [])[: schema.LLM_TITLE_CONTEXT_POINTS]:
            if isinstance(milestone, dict):
                parts.append(str(milestone.get("label", "")).strip())
    elif slide_type in ("cycle", "triangle"):
        for item in slide.get("items", [])[: schema.LLM_TITLE_CONTEXT_POINTS]:
            if isinstance(item, str):
                parts.append(item.strip())
            elif isinstance(item, dict):
                parts.append(str(item.get("label") or item.get("title") or "").strip())
    elif slide_type == "pyramid":
        for level in slide.get("levels", [])[: schema.LLM_TITLE_CONTEXT_POINTS]:
            if isinstance(level, dict):
                parts.append(str(level.get("title", "")).strip())

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


def _extract_assistant_text(response: dict[str, Any]) -> str:
    """chat completion 応答から本文を取り出す。"""
    choice = response["choices"][0]
    message = choice.get("message") or {}
    return str(message.get("content", ""))


def _call_llm_raw(model: Any, system_prompt: str, user_prompt: str) -> str:
    """モデルに chat completion を1回依頼する。"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    kwargs = {
        "messages": messages,
        "max_tokens": schema.LLM_MAX_TOKENS,
        "temperature": schema.LLM_TEMPERATURE,
        "top_p": 0.9,
        "stop": ["\n"],
    }

    # llama-server: HTTP 接続再利用のためスレッドプールを使わない
    if llama_server is not None and isinstance(model, llama_server.LlamaServerClient):
        return _extract_assistant_text(model.create_chat_completion(**kwargs))

    def _generate() -> str:
        return _extract_assistant_text(model.create_chat_completion(**kwargs))

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_generate)
        try:
            return future.result(timeout=schema.LLM_TIMEOUT_SEC)
        except concurrent.futures.TimeoutError:
            logger.warning("LLM timeout")
            raise


def _call_llm(model: Any, original_title: str, *, slide_context: str = "") -> str:
    """モデルに1件のタイトル短縮を依頼する。"""
    system_prompt, user_prompt = _build_user_prompt(original_title, slide_context)

    try:
        return _call_llm_raw(model, system_prompt, user_prompt)
    except Exception:
        raise


def generate_title_from_slide(model: Any | None, slide: dict[str, Any]) -> str:
    """スライド本文から AI タイトルを1件生成する。失敗時は元タイトルを返す。"""
    fallback = str(slide.get("title", ""))
    if model is None:
        return fallback

    slide_context = _build_slide_context(slide)
    if not slide_context.strip():
        slide_context = fallback

    user_prompt = (
        "次のスライド内容にふさわしい、15文字以内の見出しを作ってください。\n"
        "本文の要点:\n"
        f"{slide_context}\n"
        "見出し:"
    )
    try:
        raw = _call_llm_raw(model, _SYSTEM_PROMPT_GENERATE, user_prompt)
    except Exception as exc:
        logger.warning("LLM generate failed: %s", exc)
        return fallback

    candidate = _sanitize_llm_title(raw)
    if _is_valid_generated_title(candidate):
        return candidate

    logger.info("LLM generate rejected, fallback: %r -> %r", fallback[:40], raw[:40])
    return fallback


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


def apply_ai_titles(
    slide_data: list[dict[str, Any]],
    *,
    progress_callback: Callable[[int, int, str], None] | None = None,
    title_ready_callback: Callable[[int, str], None] | None = None,
    model: Any | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """slideData の各本文スライドに AI タイトルを生成する。

    Returns:
        (新しい slideData, スキップ理由メッセージ or None)
    """
    result = deepcopy(slide_data)
    targets = slide_sync.list_ai_title_target_indices(result)
    if not targets:
        return result, None

    if model is None:
        model = load_model()
    if model is None:
        return result, "モデル未検出のためAIタイトル生成をスキップしました"

    total = len(targets)
    for step, index in enumerate(targets, start=1):
        slide = result[index]
        original = str(slide.get("title", ""))
        try:
            slide["title"] = generate_title_from_slide(model, slide)
        except Exception as exc:
            logger.warning("apply_ai_titles slide=%d failed: %s", index, exc)
            slide["title"] = original
        if title_ready_callback is not None:
            title_ready_callback(index, str(slide.get("title", "")))
        if progress_callback is not None:
            progress_callback(step, total, "AIにより処理中・・・")

    return result, None


def _strip_notes_markup(text: str) -> str:
    """notes 用マークアップを除去する（魔人式 7.0 準拠）。"""
    cleaned = _NOTES_MARKUP_RE.sub(lambda m: m.group(1) or m.group(2) or "", text)
    for ch in ("*", "[", "]", "_", "~", "`"):
        cleaned = cleaned.replace(ch, "")
    return cleaned.strip()


def _is_valid_subhead(candidate: str) -> bool:
    """小見出しが採用可能かどうか。"""
    if not candidate or len(candidate) <= 1:
        return False
    if len(candidate) > schema.LLM_SUBHEAD_MAX_CHARS:
        return False
    if _INSTRUCTION_ECHO_RE.search(candidate) and len(candidate) <= 10:
        return False
    return True


def _is_valid_notes(candidate: str) -> bool:
    """スピーカーノートが採用可能かどうか。"""
    if not candidate or len(candidate) < 8:
        return False
    for markup in schema.NOTES_FORBIDDEN_MARKUP:
        if markup in candidate:
            return False
    return True


def _call_llm_with_tokens(
    model: Any,
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int,
) -> str:
    """max_tokens を指定して LLM を1回呼ぶ。"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    kwargs = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": schema.LLM_TEMPERATURE,
        "top_p": 0.9,
        "stop": ["\n\n"],
    }
    if llama_server is not None and isinstance(model, llama_server.LlamaServerClient):
        response = model.create_chat_completion(**kwargs)
        return _extract_assistant_text(response)

    def _generate() -> str:
        response = model.create_chat_completion(**kwargs)
        return _extract_assistant_text(response)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_generate)
        return future.result(timeout=schema.LLM_TIMEOUT_SEC)


def generate_subhead_from_slide(model: Any | None, slide: dict[str, Any]) -> str:
    """スライドから小見出しを1件生成する。失敗時は空文字。"""
    if model is None or slide.get("subhead"):
        return str(slide.get("subhead", ""))

    context = _build_slide_context(slide)
    title = str(slide.get("title", ""))
    user_prompt = (
        "次のスライドにふさわしい小見出しを作ってください。\n"
        f"タイトル: {title}\n"
        f"本文要点:\n{context or title}\n"
        "小見出し:"
    )
    try:
        raw = _call_llm_with_tokens(
            model, _SYSTEM_PROMPT_SUBHEAD, user_prompt,
            max_tokens=schema.LLM_SUBHEAD_MAX_TOKENS,
        )
    except Exception as exc:
        logger.warning("LLM subhead failed: %s", exc)
        return ""

    candidate = _sanitize_llm_title(raw)
    if _is_valid_subhead(candidate):
        return candidate
    return ""


def generate_notes_from_slide(model: Any | None, slide: dict[str, Any]) -> str:
    """スライドからスピーカーノートを生成する。失敗時は空文字。"""
    if model is None or slide.get("notes"):
        return str(slide.get("notes", ""))

    context = _build_slide_context(slide)
    title = str(slide.get("title", ""))
    user_prompt = (
        "次のスライドの発表原稿を書いてください。\n"
        f"タイトル: {title}\n"
        f"内容:\n{context or title}\n"
        "原稿:"
    )
    try:
        raw = _call_llm_with_tokens(
            model, _SYSTEM_PROMPT_NOTES, user_prompt,
            max_tokens=schema.LLM_NOTES_MAX_TOKENS,
        )
    except Exception as exc:
        logger.warning("LLM notes failed: %s", exc)
        return ""

    candidate = _strip_notes_markup(raw.replace("\n", " ").strip())
    if _is_valid_notes(candidate):
        return candidate
    return ""


def _classify_content_slide(model: Any, slide: dict[str, Any]) -> str:
    """content スライドの最適パターンを1語で分類する。"""
    points = slide.get("points") or []
    if not isinstance(points, list) or len(points) < 2:
        return "content"

    bullet_text = "\n".join(f"- {str(p)}" for p in points[:6])
    user_prompt = (
        "次の箇条書きに最適な表現を1語だけ選んでください。\n"
        f"{bullet_text}\n"
        "回答:"
    )
    try:
        raw = _call_llm_with_tokens(
            model, _SYSTEM_PROMPT_RECLASSIFY, user_prompt,
            max_tokens=schema.LLM_RECLASSIFY_MAX_TOKENS,
        )
    except Exception as exc:
        logger.warning("LLM reclassify failed: %s", exc)
        return "content"

    answer = raw.strip().lower().split()[0] if raw.strip() else "content"
    answer = answer.strip(".,。、")
    if answer in _RECLASSIFY_ALLOWED:
        return answer
    return "content"


def _transform_content_slide(slide: dict[str, Any], target_type: str) -> dict[str, Any]:
    """content を専門パターンへ構造変換する（Python 側）。"""
    if target_type == "content":
        return slide

    points = [str(p).strip() for p in (slide.get("points") or []) if str(p).strip()]
    base = {key: value for key, value in slide.items() if key != "points"}

    if target_type == "process" and 2 <= len(points) <= schema.MAX_COUNT["process"]:
        return {**base, "type": "process", "steps": points[: schema.MAX_COUNT["process"]]}

    if target_type == "timeline" and len(points) >= 2:
        milestones = [
            {"label": point[:30], "date": f"Phase {index + 1}"}
            for index, point in enumerate(points[:8])
        ]
        return {**base, "type": "timeline", "milestones": milestones}

    if target_type == "cycle" and len(points) == schema.FIXED_COUNT["cycle"]:
        items = [{"label": point[:20]} for point in points]
        return {**base, "type": "cycle", "items": items}

    if target_type == "pyramid" and schema.MAX_COUNT["pyramid_levels_min"] <= len(points) <= schema.MAX_COUNT["pyramid_levels_max"]:
        levels = [
            {"title": point[:12], "description": point}
            for point in points[: schema.MAX_COUNT["pyramid_levels_max"]]
        ]
        return {**base, "type": "pyramid", "levels": levels}

    return slide


def apply_pattern_reclassify(
    slide_data: list[dict[str, Any]],
    *,
    progress_callback: Callable[[int, int, str], None] | None = None,
    model: Any | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """content スライドを LLM 分類 + Python 変換で専門パターンへ再配置する。"""
    result = deepcopy(slide_data)
    targets = [i for i, slide in enumerate(result) if slide.get("type") == "content" and slide.get("points")]
    if not targets:
        return result, None

    if model is None:
        model = load_model()
    if model is None:
        return result, "モデル未検出のためパターン再分類をスキップしました"

    total = len(targets)
    for step, index in enumerate(targets, start=1):
        slide = result[index]
        target_type = _classify_content_slide(model, slide)
        result[index] = _transform_content_slide(slide, target_type)
        if progress_callback is not None:
            progress_callback(step, total, "パターン選定中...")

    return result, None


def apply_ai_subheads(
    slide_data: list[dict[str, Any]],
    *,
    progress_callback: Callable[[int, int, str], None] | None = None,
    model: Any | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """各スライドに AI 小見出しを付与する。"""
    result = deepcopy(slide_data)
    targets = [
        i for i, slide in enumerate(result)
        if slide.get("type") not in _SKIP_TITLE_TYPES and not slide.get("subhead")
    ]
    if not targets:
        return result, None

    if model is None:
        model = load_model()
    if model is None:
        return result, "モデル未検出のため小見出し生成をスキップしました"

    total = len(targets)
    for step, index in enumerate(targets, start=1):
        subhead = generate_subhead_from_slide(model, result[index])
        if subhead:
            result[index]["subhead"] = subhead
        if progress_callback is not None:
            progress_callback(step, total, "小見出し生成中...")

    return result, None


def apply_ai_notes(
    slide_data: list[dict[str, Any]],
    *,
    progress_callback: Callable[[int, int, str], None] | None = None,
    model: Any | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """各スライドに AI スピーカーノートを付与する。"""
    result = deepcopy(slide_data)
    targets = [
        i for i, slide in enumerate(result)
        if slide.get("type") not in _SKIP_TITLE_TYPES and not slide.get("notes")
    ]
    if not targets:
        return result, None

    if model is None:
        model = load_model()
    if model is None:
        return result, "モデル未検出のためノート生成をスキップしました"

    total = len(targets)
    for step, index in enumerate(targets, start=1):
        notes = generate_notes_from_slide(model, result[index])
        if notes:
            result[index]["notes"] = notes
        if progress_callback is not None:
            progress_callback(step, total, "ノート生成中...")

    return result, None


def apply_ai_enhancements(
    slide_data: list[dict[str, Any]],
    *,
    use_reclassify: bool = False,
    use_subhead: bool = False,
    use_notes: bool = False,
    progress_callback: Callable[[int, int, str], None] | None = None,
    model: Any | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """タイトル以外の LLM 拡張（再分類→小見出し→ノート）を順に適用する。"""
    result = deepcopy(slide_data)
    skip_messages: list[str] = []

    if model is None and (use_reclassify or use_subhead or use_notes):
        model = load_model()

    if use_reclassify:
        result, msg = apply_pattern_reclassify(
            result, progress_callback=progress_callback, model=model,
        )
        if msg:
            skip_messages.append(msg)

    if use_subhead:
        result, msg = apply_ai_subheads(
            result, progress_callback=progress_callback, model=model,
        )
        if msg:
            skip_messages.append(msg)

    if use_notes:
        result, msg = apply_ai_notes(
            result, progress_callback=progress_callback, model=model,
        )
        if msg:
            skip_messages.append(msg)

    return result, skip_messages


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
