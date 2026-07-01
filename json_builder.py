"""slideData 生成の司令塔."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Literal

import extractor
import llm_mode
import rule_mode

Mode = Literal["rule", "llm"]

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
    mode: Mode = "rule",
    *,
    cover_title: str | None = None,
    use_llm_title_fix: bool = False,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """PDF から slideData を生成する。

    Args:
        pdf_path: 入力 PDF パス。
        mode: ``rule`` または ``llm``。
        cover_title: ユーザー指定の表紙タイトル（空ならフォールバック）。
        use_llm_title_fix: ルール生成後に LLM で長いタイトルを短縮する。
        progress_callback: LLM タイトル整形の進捗 ``(current, total, message)``。

    Returns:
        ``(slideData 配列, LLM スキップ理由 or None)``。
    """
    path = Path(pdf_path)
    text = extractor.extract_text_from_pdf(path)
    stem = path.stem

    if mode == "llm":
        data = llm_mode.build_slide_data(text, pdf_stem=stem, cover_title=cover_title)
        return data, None

    data = rule_mode.build_slide_data(text, pdf_stem=stem, cover_title=cover_title)
    llm_status: str | None = None
    if use_llm_title_fix:
        data, llm_status = llm_mode.apply_title_fix(
            data,
            progress_callback=progress_callback,
        )
    return data, llm_status
