"""slideData 生成の司令塔."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

import extractor
import llm_mode
import rule_mode

# PDF ファイル名から日付サフィックス等を除去する
_STEM_DATE_SUFFIX_RE = re.compile(
    r"[_\-\s]?(?:\d{4}[\-_]?\d{2}[\-_]?\d{2}|\d{8}|v\d+)$",
    re.IGNORECASE,
)


def suggest_cover_title_from_stem(pdf_stem: str) -> str:
    """PDF ファイル名から表紙タイトル候補を推定する（入力欄の初期値用）。"""
    stem = pdf_stem.strip()
    while True:
        cleaned = _STEM_DATE_SUFFIX_RE.sub("", stem).strip(" _-")
        if cleaned == stem or not cleaned:
            break
        stem = cleaned
    return stem or pdf_stem


def build_from_pdf(
    pdf_path: str | Path,
    *,
    cover_title: str | None = None,
    use_ai_titles: bool = False,
    progress_callback: Callable[[int, int, str], None] | None = None,
    title_ready_callback: Callable[[int, str], None] | None = None,
    model: Any | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """PDF から slideData を生成する（ルールベース → 任意で AI タイトル）。

    Args:
        pdf_path: 入力 PDF パス。
        cover_title: ユーザー指定の表紙タイトル（空ならフォールバック）。
        use_ai_titles: ルール生成後に AI で各スライドタイトルを生成する。
        progress_callback: AI 処理進捗 ``(current, total, message)``。
        title_ready_callback: 1件完了ごと ``(slide_index, title)``。
        model: 事前ロード済み LLM（省略時はキャッシュから取得）。

    Returns:
        ``(slideData 配列, AI スキップ理由 or None)``。
    """
    path = Path(pdf_path)
    text = extractor.extract_text_from_pdf(path)
    stem = path.stem

    data = rule_mode.build_slide_data(text, pdf_stem=stem, cover_title=cover_title)
    llm_status: str | None = None
    if use_ai_titles:
        data, llm_status = llm_mode.apply_ai_titles(
            data,
            progress_callback=progress_callback,
            title_ready_callback=title_ready_callback,
            model=model,
        )
    return data, llm_status
