"""slideData 生成の司令塔."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

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
) -> list[dict[str, Any]]:
    """PDF から slideData を生成する。

    Args:
        pdf_path: 入力 PDF パス。
        mode: ``rule`` または ``llm``。
        cover_title: ユーザー指定の表紙タイトル（空ならフォールバック）。

    Returns:
        slideData 配列。
    """
    path = Path(pdf_path)
    text = extractor.extract_text_from_pdf(path)
    stem = path.stem

    if mode == "llm":
        return llm_mode.build_slide_data(text, pdf_stem=stem, cover_title=cover_title)
    return rule_mode.build_slide_data(text, pdf_stem=stem, cover_title=cover_title)
