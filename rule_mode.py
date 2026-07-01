"""ルールベース slideData 生成."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

# 見出しパターン（Markdown / 日本語文書向け）
_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_H2_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_H3_RE = re.compile(r"^###\s+(.+)$", re.MULTILINE)
_BULLET_RE = re.compile(r"^[\-\*•・]\s+(.+)$", re.MULTILINE)
_NUMBERED_RE = re.compile(r"^\d+[\.\)、．]\s*(.+)$", re.MULTILINE)

_AGENDA_KEYWORDS = ("目次", "アジェンダ", "agenda", "Agenda", "概要")
_SECTION_KEYWORDS = ("章", "パート", "Part", "PART", "第")
_CLOSING_KEYWORDS = ("まとめ", "おわりに", "結論", "ご清聴", "Thank", "thank")


def build_slide_data(text: str, *, pdf_stem: str = "プレゼンテーション") -> list[dict[str, Any]]:
    """抽出テキストからルールベースで slideData を生成する。

    Args:
        text: extractor が返した Markdown テキスト。
        pdf_stem: PDF ファイル名（拡張子なし）— タイトル候補に使用。

    Returns:
        slideData 配列。
    """
    if not text or not text.strip():
        return _empty_fallback(pdf_stem)

    blocks = _split_blocks(text)
    slides: list[dict[str, Any]] = []
    section_counter = 0
    agenda_items: list[str] = []
    pending_agenda = False

    # 表紙
    title = _guess_title(blocks, pdf_stem)
    slides.append({
        "type": "title",
        "title": title,
        "date": date.today().strftime("%Y.%m.%d"),
    })

    for block in blocks:
        block_type, heading, body_lines = _classify_block(block)

        if block_type == "agenda_header":
            pending_agenda = True
            continue

        if pending_agenda and body_lines:
            agenda_items = [_clean_bullet(line) for line in body_lines if line.strip()]
            pending_agenda = False
            continue

        if block_type == "section":
            section_counter += 1
            slides.append({
                "type": "section",
                "title": heading,
                "sectionNo": section_counter,
            })
            if body_lines:
                points = [_clean_bullet(line) for line in body_lines if line.strip()]
                if points:
                    slides.append({
                        "type": "content",
                        "title": heading,
                        "points": points[:8],
                    })
            continue

        if block_type == "closing":
            slides.append({"type": "closing"})
            continue

        if heading:
            points = [_clean_bullet(line) for line in body_lines if line.strip()]
            if not points and not heading:
                continue
            slide: dict[str, Any] = {"type": "content", "title": heading}
            if points:
                slide["points"] = points[:8]
            slides.append(slide)

    if agenda_items:
        # アジェンダは表紙の直後に挿入
        slides.insert(1, {
            "type": "agenda",
            "title": "アジェンダ",
            "items": agenda_items[:12],
        })

    if not any(s.get("type") == "closing" for s in slides):
        slides.append({"type": "closing"})

    return slides


def _empty_fallback(pdf_stem: str) -> list[dict[str, Any]]:
    """抽出失敗時の最低限スライド。"""
    return [
        {
            "type": "title",
            "title": pdf_stem,
            "date": date.today().strftime("%Y.%m.%d"),
            "notes": "PDF からテキストを抽出できませんでした。スキャン PDF の可能性があります。",
        },
        {
            "type": "content",
            "title": "内容を確認してください",
            "points": [
                "PDF からテキストを抽出できませんでした",
                "スキャン PDF の場合は OCR 対応が必要です（第1弾範囲外）",
                "JSON を手動で編集してスライドを作成できます",
            ],
        },
        {"type": "closing"},
    ]


def _split_blocks(text: str) -> list[str]:
    """見出しでブロックに分割する。"""
    lines = text.splitlines()
    blocks: list[list[str]] = []
    current: list[str] = []

    for line in lines:
        if _is_heading(line) and current:
            blocks.append("\n".join(current))
            current = [line]
        else:
            current.append(line)

    if current:
        blocks.append("\n".join(current))

    return [b.strip() for b in blocks if b.strip()]


def _is_heading(line: str) -> bool:
    """行が見出しかどうか。"""
    stripped = line.strip()
    return bool(_H1_RE.match(stripped) or _H2_RE.match(stripped) or _H3_RE.match(stripped))


def _extract_heading(line: str) -> str | None:
    """見出し行からタイトル文字列を取り出す。"""
    stripped = line.strip()
    for pattern in (_H1_RE, _H2_RE, _H3_RE):
        m = pattern.match(stripped)
        if m:
            return m.group(1).strip()
    return None


def _classify_block(block: str) -> tuple[str, str, list[str]]:
    """ブロックを分類する。

    Returns:
        (block_type, heading, body_lines)
    """
    lines = block.splitlines()
    if not lines:
        return "content", "", []

    first = lines[0].strip()
    heading = _extract_heading(first) or first
    body_lines = lines[1:] if _is_heading(first) else lines

    heading_lower = heading.lower()
    for kw in _AGENDA_KEYWORDS:
        if kw.lower() in heading_lower:
            return "agenda_header", heading, body_lines

    for kw in _CLOSING_KEYWORDS:
        if kw in heading:
            return "closing", heading, body_lines

    for kw in _SECTION_KEYWORDS:
        if kw in heading:
            return "section", heading, body_lines

    if _is_heading(first):
        return "content", heading, body_lines

    return "content", heading if len(lines) == 1 else "", body_lines if len(lines) > 1 else lines


def _guess_title(blocks: list[str], pdf_stem: str) -> str:
    """最初のブロックからタイトルを推定する。"""
    if not blocks:
        return pdf_stem
    first_line = blocks[0].splitlines()[0].strip()
    h = _extract_heading(first_line)
    return h or first_line or pdf_stem


def _clean_bullet(line: str) -> str:
    """箇条書き記号・末尾句点を除去する。"""
    stripped = line.strip()
    for pattern in (_BULLET_RE, _NUMBERED_RE):
        m = pattern.match(stripped)
        if m:
            stripped = m.group(1).strip()
            break
    if stripped.endswith("。"):
        stripped = stripped[:-1]
    return stripped
