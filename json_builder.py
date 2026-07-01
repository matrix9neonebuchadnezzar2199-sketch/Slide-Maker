"""slideData 生成の司令塔."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import extractor
import llm_mode
import rule_mode

Mode = Literal["rule", "llm"]


def build_from_pdf(pdf_path: str | Path, mode: Mode = "rule") -> list[dict[str, Any]]:
    """PDF から slideData を生成する。

    Args:
        pdf_path: 入力 PDF パス。
        mode: ``rule`` または ``llm``。

    Returns:
        slideData 配列。
    """
    path = Path(pdf_path)
    text = extractor.extract_text_from_pdf(path)
    stem = path.stem

    if mode == "llm":
        return llm_mode.build_slide_data(text, pdf_stem=stem)
    return rule_mode.build_slide_data(text, pdf_stem=stem)
