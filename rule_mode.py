"""ルールベース slideData 生成."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from table_parser import detect_markdown_tables, is_markdown_table_row
from utils import parse_number

# 見出しパターン（Markdown / 日本語文書向け）
_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_H2_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_H3_RE = re.compile(r"^###\s+(.+)$", re.MULTILINE)
_BULLET_RE = re.compile(r"^[\-\*•・]\s+(.+)$", re.MULTILINE)
_NUMBERED_RE = re.compile(r"^\d+[\.\)、．]\s*(.+)$", re.MULTILINE)
_TAB_ROW_RE = re.compile(r"\t")

# 日付のみの行（表紙 date 用・タイトル除外）
_DATE_LINE_RE = re.compile(
    r"^(\d{4})[年.\-/](\d{1,2})[月.\-/](\d{1,2})日?\s*$"
    r"|^(\d{4})\.(\d{2})\.(\d{2})\s*$",
)

_AGENDA_KEYWORDS = ("目次", "アジェンダ", "agenda", "Agenda", "概要")
_SECTION_KEYWORDS = ("章", "パート", "Part", "PART", "第")
_CLOSING_KEYWORDS = ("まとめ", "おわりに", "結論", "ご清聴", "Thank", "thank")

# compare は明示的対比語のみ（「対」「比較」単独は除外）
_COMPARE_STRONG_RE = re.compile(
    r"vs\.?|VS|対比|メリット|デメリット|従来\s*/\s*新|従来/新|新方式|Before|After",
    re.IGNORECASE,
)
_KPI_KEYWORDS = re.compile(r"売上|達成率|件数|人数|KPI|kpi|利益|成長")
_NUMERIC_UNIT_RE = re.compile(
    r"[\d,]+\.?\d*\s*[%％円万件人台回]|約[\d,]+",
)
_BAR_COMPARE_RE = re.compile(r"前年比|前月比|昨年対|目標対|実績対|予算対")


def build_slide_data(text: str, *, pdf_stem: str = "プレゼンテーション") -> list[dict[str, Any]]:
    """抽出テキストからルールベースで slideData を生成する。"""
    if not text or not text.strip():
        return _empty_fallback(pdf_stem)

    blocks = _split_blocks(text)
    slides: list[dict[str, Any]] = []
    section_counter = 0
    agenda_items: list[str] = []
    pending_agenda = False

    cover_title = _find_cover_title(text, pdf_stem)
    cover_date = _extract_cover_date(blocks) or date.today().strftime("%Y.%m.%d")
    slides.append({
        "type": "title",
        "title": cover_title,
        "date": cover_date,
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
            slides.extend(_slides_from_body(heading, body_lines, cover_title=cover_title))
            continue

        if block_type == "closing":
            slides.append({"type": "closing"})
            continue

        # 日付のみブロックは表紙で処理済み — 独立スライドにしない
        if _is_date_only(heading) and not body_lines:
            continue

        slides.extend(_slides_from_body(heading, body_lines, cover_title=cover_title))

    if agenda_items:
        slides.insert(1, {
            "type": "agenda",
            "title": "アジェンダ",
            "items": agenda_items[:12],
        })

    if not any(s.get("type") == "closing" for s in slides):
        slides.append({"type": "closing"})

    return slides


def _slides_from_body(
    heading: str,
    body_lines: list[str],
    *,
    cover_title: str = "",
) -> list[dict[str, Any]]:
    """本文行からスライド（table / 特殊 / content）を生成する。"""
    result: list[dict[str, Any]] = []
    tables, remaining = detect_markdown_tables(body_lines)

    for tbl in tables:
        slide = dict(tbl)
        slide["title"] = heading or "データ一覧"
        result.append(slide)

    # タブ区切り表
    tab_slide = _try_tab_table(heading, remaining)
    if tab_slide:
        result.append(tab_slide)
        remaining = [ln for ln in remaining if "\t" not in ln]

    # 非表行のみで特殊パターン判定
    non_table_lines = [
        ln for ln in remaining
        if ln.strip() and not is_markdown_table_row(ln)
    ]
    cleaned = [_clean_bullet(line) for line in non_table_lines if line.strip()]

    special = _detect_special_slide(heading, cleaned, non_table_lines)
    if special:
        result.append(special)
        return result

    points = [p for p in cleaned if p and not _is_date_only(p)]
    # points が空の content は生成しない（表見出しだけの殻スライド防止）
    if not points:
        return result

    # 表紙タイトルと同一で、既に table 等を出している場合は content を重複させない
    if heading == cover_title and result:
        return result

    result.append({
        "type": "content",
        "title": heading or "内容",
        "points": points[:8],
    })

    return result


def _detect_special_slide(
    heading: str,
    cleaned: list[str],
    raw_lines: list[str],
) -> dict[str, Any] | None:
    """数値・比較構造を検出して第2弾パターンを返す。"""
    if _lines_look_like_table(raw_lines):
        return None

    combined = heading + "\n" + "\n".join(raw_lines)

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


def _lines_look_like_table(lines: list[str]) -> bool:
    """行群が表形式かどうか。"""
    return sum(1 for ln in lines if is_markdown_table_row(ln)) >= 2


def _try_tab_table(heading: str, body_lines: list[str]) -> dict[str, Any] | None:
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
        "rows": data_rows[:20],
    }


def _try_compare(heading: str, lines: list[str], combined: str) -> dict[str, Any] | None:
    """明示的対比語がある場合のみ compare を生成する。"""
    if not _COMPARE_STRONG_RE.search(combined):
        return None

    # 注釈ブロックは content 向け
    if heading.strip().startswith("（注") or combined.strip().startswith("（注"):
        return None

    mid = max(1, len(lines) // 2)
    left_items = lines[:mid][:6]
    right_items = lines[mid:][:6]
    if not left_items or not right_items:
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
        "leftItems": left_items,
        "rightItems": right_items,
    }


def _try_bar_compare(heading: str, lines: list[str], combined: str) -> dict[str, Any] | None:
    """2値比較行から barCompare を生成する。"""
    if not _BAR_COMPARE_RE.search(combined):
        return None

    stats: list[dict[str, str]] = []
    pair_re = re.compile(
        r"(.+?)[:：]\s*([\d,.\-%％円万件人]+)\s*(?:/|vs|VS)\s*([\d,.\-%％円万件人]+)",
    )
    for line in lines:
        m = pair_re.search(line)
        if m:
            stats.append({
                "label": m.group(1).strip()[:12],
                "leftValue": m.group(2).strip(),
                "rightValue": m.group(3).strip(),
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


def _is_date_only(text: str) -> bool:
    """文字列が日付のみかどうか。"""
    if not text:
        return False
    return bool(_DATE_LINE_RE.match(text.strip()))


def _normalize_date(text: str) -> str | None:
    """日付文字列を YYYY.MM.DD に正規化する。"""
    stripped = text.strip()
    m = _DATE_LINE_RE.match(stripped)
    if not m:
        return None
    if m.group(1):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        y, mo, d = int(m.group(4)), int(m.group(5)), int(m.group(6))
    return f"{y:04d}.{mo:02d}.{d:02d}"


def _extract_cover_date(blocks: list[str]) -> str | None:
    """文書先頭付近の日付を表紙 date 用に抽出する。"""
    for block in blocks[:3]:
        for line in block.splitlines()[:5]:
            stripped = line.strip()
            norm = _normalize_date(stripped)
            if norm:
                return norm
            h = _extract_heading(line)
            if h:
                norm = _normalize_date(h)
                if norm:
                    return norm
    return None


def _is_valid_cover_title(text: str) -> bool:
    """表紙タイトル候補として妥当かどうか。"""
    if not text or not text.strip():
        return False
    if _is_date_only(text):
        return False
    if is_markdown_table_row(text) or text.strip().startswith("|"):
        return False
    return True


def _parse_heading_level(line: str) -> tuple[int, str] | None:
    """見出し行のレベルとタイトル文字列を返す。"""
    stripped = line.strip()
    for level, pattern in ((1, _H1_RE), (2, _H2_RE), (3, _H3_RE)):
        m = pattern.match(stripped)
        if m:
            return level, m.group(1).strip()
    return None


def _find_cover_title(text: str, pdf_stem: str) -> str:
    """文書先頭から走査し、最初の有効 H2 を表紙タイトルに確定する。

    見つかった時点で即 return（後続の見出しは見ない）。
    H2 が無い場合は、最初の表より前にある最初の見出しを fallback とする。
    """
    # 優先1: 最初の H2（日付・表行以外）
    for line in text.splitlines():
        parsed = _parse_heading_level(line)
        if parsed is None:
            continue
        level, title = parsed
        if level == 2 and _is_valid_cover_title(title):
            return title

    # 優先2: 最初の H1
    for line in text.splitlines():
        parsed = _parse_heading_level(line)
        if parsed is None:
            continue
        level, title = parsed
        if level == 1 and _is_valid_cover_title(title):
            return title

    # 優先3: 最初の Markdown 表より前にある最初の見出し（### 含む）
    for line in text.splitlines():
        if is_markdown_table_row(line):
            break
        parsed = _parse_heading_level(line)
        if parsed is None:
            continue
        _, title = parsed
        if _is_valid_cover_title(title):
            return title

    return pdf_stem


def _guess_title(blocks: list[str], pdf_stem: str) -> str:
    """後方互換 — 全文から表紙タイトルを推定する。"""
    return _find_cover_title("\n\n".join(blocks), pdf_stem)


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
