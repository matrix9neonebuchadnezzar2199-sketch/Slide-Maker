"""parse_number の単体テスト."""

from __future__ import annotations

import pytest

from utils import parse_number


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1,234", 1234.0),
        ("12.5%", 12.5),
        ("約3,000円", 3000.0),
        ("▲500", -500.0),
        ("-12", -12.0),
        ("+12%", 12.0),
        ("", 0.0),
        ("該当なし", 0.0),
        ("売上 1,234,567件", 1234567.0),
    ],
)
def test_parse_number(text: str, expected: float) -> None:
    assert parse_number(text) == expected
