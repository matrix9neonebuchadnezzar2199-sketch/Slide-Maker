"""共通ユーティリティ — 数値パース等."""

from __future__ import annotations

import re

# カンマ・単位・記号を除いた数値部分を抽出
_NUMBER_RE = re.compile(r"(\d[\d,]*\.?\d*)")


def parse_number(text: str) -> float:
    """日本語ビジネス文書の数値表現から float を抽出する。

    対応例: ``1,234`` / ``12.5%`` / ``約3,000円`` / ``▲500`` / ``-12`` / ``+12%``

    Args:
        text: 数値を含む文字列。

    Returns:
        抽出した数値。パース不能時は 0.0。
    """
    if not text or not isinstance(text, str):
        return 0.0

    s = text.strip()
    if not s:
        return 0.0

    negative = False
    if s.startswith(("▲", "▼", "-", "−", "－")):
        negative = True
        s = s.lstrip("▲▼+-−－")

    m = _NUMBER_RE.search(s.replace(",", ""))
    if not m:
        return 0.0

    try:
        value = float(m.group(1).replace(",", ""))
    except ValueError:
        return 0.0

    return -value if negative else value
