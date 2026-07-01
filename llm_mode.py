"""LLM による slideData 生成（第1弾はスタブ）."""

from __future__ import annotations

from typing import Any


class LlmModeNotImplementedError(Exception):
    """LLM モードが未実装であることを示す。"""


def build_slide_data(text: str, *, pdf_stem: str = "") -> list[dict[str, Any]]:
    """LLM で slideData を生成する（第4弾で実装予定）。

    Args:
        text: 抽出済み PDF テキスト。
        pdf_stem: PDF ファイル名（拡張子なし）。

    Raises:
        LlmModeNotImplementedError: 第1弾では常に発生。
    """
    raise LlmModeNotImplementedError(
        "LLM モードは第4弾で実装予定です。ルールベースモードをお使いください。"
    )
