"""ルールベース slideData 生成."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from utils import parse_number

# 見出しパターン（Markdown / 日本語文書向け）
_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_H2_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_H3_RE = re.compile(r"^###\s+(.+)$", re.MULTILINE)
_BULLET_RE = re.compile(r"^[\-\*•・]\s+(.+)$", re.MULTILINE)
_NUMBERED_RE = re.compile(r"^\d+[\.\)、．]\s*(.+)$", re.MULTILINE)
_TAB_ROW_RE = re.compile(r"\t")

_AGENDA_KEYWORDS = ("目次", "アジェンダ", "agenda", "Agenda", "概要")
_SECTION_KEYWORDS = ("章", "パート", "Part", "PART", "第")
_CLOSING_KEYWORDS = ("まとめ", "おわりに", "結論", "ご清聴", "Thank", "thank")

_COMPARE_KEYWORDS = re.compile(
    r"対|vs|VS|比較|メリット|デメリット|従来|新方式|Before|After",
)
_KPI_KEYWORDS = re.compile(r"売上|達成率|件数|人数|KPI|kpi|利益|成長")
_NUMERIC_UNIT_RE = re.compile(
    r"[\d,]+\.?\d*\s*[%％円万件人台回]|約[\d,]+",
)
_BAR_COMPARE_RE = re.compile(r"前年|前月|対比|昨年|目標|実績|予算")


def build_slide_data(text: str, *, pdf_stem: str = "プレゼンテーション") -> list[dict[str, Any]]:
    """抽出テキストからルールベースで slideData を生成する。"""
    if not text or not text.strip():
        return _empty_fallback(pdf_stem)

    blocks = _split_blocks(text)
    slides: list[dict[str, Any]] = []
    section_counter = 0
    agenda_items: list[str] = []
    pending_agenda = False

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
            special = _detect_special_slide(heading, body_lines)
            if special:
                slides.append(special)
            elif body_lines:
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

        special = _detect_special_slide(heading, body_lines)
        if special:
            slides.append(special)
            continue

        if heading:
            points = [_clean_bullet(line) for line in body_lines if line.strip()]
            slide: dict[str, Any] = {"type": "content", "title": heading}
            if points:
                slide["points"] = points[:8]
            slides.append(slide)

    if agenda_items:
        slides.insert(1, {
            "type": "agenda",
            "title": "アジェンダ",
            "items": agenda_items[:12],
        })

    if not any(s.get("type") == "closing" for s in slides):
        slides.append({"type": "closing"})

    return slides


def _detect_special_slide(heading: str, body_lines: list[str]) -> dict[str, Any] | None:
    """数値・比較構造を検出して第2弾パターンを返す。"""
    combined = heading + "\n" + "\n".join(body_lines)
    cleaned = [_clean_bullet(line) for line in body_lines if line.strip()]

    table_slide = _try_table(heading, body_lines)
    if table_slide:
        return table_slide

    compare_slide = _try_compare(heading, cleaned, combined)
    if compare_slide:
        return compare_slide

    bar_slide = _try_bar_compare(heading, cleaned, combined)
    if bar_slide:
        return bar_slide

    kpi_slide = _try_kpi(heading, cleaned, combined)
    if kpi_slide:
        return kpi_slide

    return None


def _try_table(heading: str, body_lines: list[str]) -> dict[str, Any] | None:
    """タブ区切り行から table を生成する。"""
    tab_rows = [line for line in body_lines if _TAB_ROW_RE.search(line)]
    if len(tab_rows) < 2:
        return None

    rows = [line.split("\t") for line in tab_rows]
    headers = [c.strip() for c in rows[0]]
    data_rows = [[c.strip() for c in row] for row in rows[1:]]
    if len(headers) < 2:
        return None

    return {
        "type": "table",
        "title": heading or "データ一覧",
        "headers": headers,
        "rows": data_rows[:12],
    }


def _try_compare(heading: str, lines: list[str], combined: str) -> dict[str, Any] | None:
    """対比語から compare を生成する。"""
    if not _COMPARE_KEYWORDS.search(combined):
        return None

    mid = max(1, len(lines) // 2)
    left_items = lines[:mid][:6]
    right_items = lines[mid:][:6]
    if not left_items and not right_items:
        return None

    left_title = "メリット" if "メリット" in combined else "A"
    right_title = "デメリット" if "デメリット" in combined else "B"
    if "従来" in combined and "新" in combined:
        left_title, right_title = "従来", "新方式"

    return {
        "type": "compare",
        "title": heading or "比較",
        "leftTitle": left_title,
        "rightTitle": right_title,
        "leftItems": left_items or ["項目なし"],
        "rightItems": right_items or ["項目なし"],
    }


def _try_bar_compare(heading: str, lines: list[str], combined: str) -> dict[str, Any] | None:
    """2値比較行から barCompare を生成する。"""
    if not _BAR_COMPARE_RE.search(combined):
        return None

    stats: list[dict[str, str]] = []
    pair_re = re.compile(
        r"(.+?)[:：]\s*([\d,.\-%％円万件人]+)\s*(?:→|/|vs|VS|対)\s*([\d,.\-%％円万件人]+)",
    )
    for line in lines:
        m = pair_re.search(line)
        if m:
            stats.append({
                "label": m.group(1).strip()[:12],
                "leftValue": m.group(2).strip(),
                "rightValue": m.group(3).strip(),
            })

    numeric_lines = [ln for ln in lines if len(_NUMERIC_UNIT_RE.findall(ln)) >= 2]
    if len(stats) < 2 and len(numeric_lines) >= 2:
        for i, line in enumerate(numeric_lines[:6]):
            nums = _NUMERIC_UNIT_RE.findall(line)
            label = line.split(":")[0].split("：")[0].strip()[:12] or f"項目{i + 1}"
            stats.append({
                "label": label,
                "leftValue": nums[0],
                "rightValue": nums[1] if len(nums) > 1 else "0",
            })

    if len(stats) < 2:
        return None

    return {
        "type": "barCompare",
        "title": heading or "数値比較",
        "stats": stats[:6],
        "showTrends": False,
    }


def _try_kpi(heading: str, lines: list[str], combined: str) -> dict[str, Any] | None:
    """KPI 的数値列から kpi を生成する。"""
    kpi_lines = [ln for ln in lines if _KPI_KEYWORDS.search(ln) or _NUMERIC_UNIT_RE.search(ln)]
    if len(kpi_lines) < 3:
        return None

    items: list[dict[str, str]] = []
    for line in kpi_lines[:4]:
        label = line
        value = ""
        change = ""
        m = re.match(r"(.+?)[:：]\s*(.+)", line)
        if m:
            label = m.group(1).strip()
            value = m.group(2).strip()
        else:
            nums = _NUMERIC_UNIT_RE.findall(line)
            if nums:
                value = nums[0]
                label = line.replace(nums[0], "").strip(" ：:()（）") or label

        status = "neutral"
        if parse_number(value) > 0 and ("+" in value or "増" in line):
            status = "good"
        elif "▲" in value or "減" in line or parse_number(value) < 0:
            status = "bad"

        items.append({
            "label": label[:14],
            "value": value or "—",
            "change": change or ("+0%" if status == "good" else "—"),
            "status": status,
        })

    if len(items) < 3:
        return None

    return {
        "type": "kpi",
        "title": heading or "主要指標",
        "items": items,
    }


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
    """ブロックを分類する。"""
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
