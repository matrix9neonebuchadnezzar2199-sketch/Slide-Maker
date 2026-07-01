"""PDF からのテキスト抽出（PyMuPDF4LLM）."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_path: str | Path) -> str:
    """PDF から Markdown 形式のテキストを抽出する。

    Args:
        pdf_path: 入力 PDF のパス。

    Returns:
        抽出テキスト。失敗時は空文字列。

    Raises:
        FileNotFoundError: PDF が存在しない場合。
    """
    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(f"PDF が見つかりません: {path}")

    try:
        import pymupdf4llm

        text = pymupdf4llm.to_markdown(str(path))
        if text and text.strip():
            return text.strip()
        logger.warning("PDF からテキストを抽出できませんでした（スキャン PDF の可能性）: %s", path)
        return ""
    except ImportError as exc:
        logger.error("pymupdf4llm がインストールされていません: %s", exc)
        raise
    except Exception as exc:
        logger.error("PDF 抽出エラー (%s): %s", path, exc)
        return ""
