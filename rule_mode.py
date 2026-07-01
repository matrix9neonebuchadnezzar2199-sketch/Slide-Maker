"""ルールベース slideData 生成."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from table_parser import detect_markdown_tables, is_markdown_table_row
from utils import parse_number

# 見出しパターン（Markdown / 日本語文書向け）— H1〜H6
_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_H2_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_H3_RE = re.compile(r"^###\s+(.+)$", re.MULTILINE)
_H4_RE = re.compile(r"^####\s+(.+)$", re.MULTILINE)
_H5_RE = re.compile(r"^#####\s+(.+)$", re.MULTILINE)
_H6_RE = re.compile(r"^######\s+(.+)$", re.MULTILINE)
_HEADING_MARKERS_RE = re.compile(r"^#{1,6}\s+")
_HTML_BREAK_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HEADING_PATTERNS: tuple[tuple[int, re.Pattern[str]], ...] = (
    (1, _H1_RE), (2, _H2_RE), (3, _H3_RE),
    (4, _H4_RE), (5, _H5_RE), (6, _H6_RE),
)
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

# 表紙候補から除外する括弧のみ・日付風文字列
_PAREN_ONLY_RE = re.compile(r"^（.+）$")

# kpi ラベル妥当性
_KPI_LABEL_MAX_LEN = 20
_KPI_LINE_MAX_LEN = 40
_MID_SENTENCE_END_RE = re.compile(r"[、。，．でがはをにのへ]$")
_MID_SENTENCE_START_RE = re.compile(r"^(政府|当|本|その|これ|また|さらに|景気|物価)")

# 表セル由来の疑似見出し（表紙候補から除外）
_SPURIOUS_HEADING_RE = re.compile(
    r"^(\d{1,2}Q|Q\d|年度|\d{1,2}月|上半期|下半期|通期)$"
    r"|^年度\b"
    r"|^[\d\s月Qq]+$",
    re.IGNORECASE,
)
_STEM_DATE_SUFFIX_RE = re.compile(
    r"[_\-\s]?(?:\d{4}[\-_]?\d{2}[\-_]?\d{2}|\d{8}|v\d+)$",
    re.IGNORECASE,
)
_GENERIC_STEM_NAMES = frozenset({
    "fallback", "document", "output", "untitled", "presentation",
    "プレゼンテーション", "slide", "slides", "temp", "test",
})


def build_slide_data(
    text: str,
    *,
    pdf_stem: str = "プレゼンテーション",
    cover_title: str | None = None,
) -> list[dict[str, Any]]:
    """抽出テキストからルールベースで slideData を生成する。"""
    if not text or not text.strip():
        return _empty_fallback(pdf_stem)

    blocks = _split_blocks(text)
    slides: list[dict[str, Any]] = []
    section_counter = 0
    agenda_items: list[str] = []
    pending_agenda = False

    resolved_cover = _resolve_cover_title(text, pdf_stem, cover_title)
    cover_date = _extract_cover_date(blocks) or date.today().strftime("%Y.%m.%d")
    slides.append({
        "type": "title",
        "title": resolved_cover,
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
            slides.extend(_slides_from_body(heading, body_lines, cover_title=resolved_cover))
            continue

        if block_type == "closing":
            slides.append({"type": "closing"})
            continue

        # 日付のみブロックは表紙で処理済み — 独立スライドにしない
        if _is_date_only(heading) and not body_lines:
            continue

        slides.extend(_slides_from_body(heading, body_lines, cover_title=resolved_cover))

    if agenda_items:
        slides.insert(1, {
            "type": "agenda",
            "title": "アジェンダ",
            "items": agenda_items[:12],
        })

    if not any(s.get("type") == "closing" for s in slides):
        slides.append({"type": "closing"})

    return [_sanitize_slide(slide) for slide in slides]


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
    """KPI 的数値列から kpi を生成する（文章主体文書での暴発を抑制）。"""
    kpi_lines = [ln for ln in lines if _KPI_KEYWORDS.search(ln) or _NUMERIC_UNIT_RE.search(ln)]
    if len(kpi_lines) < 3:
        return None

    # 長い段落に埋まった % は kpi にしない
    if any(len(ln) > _KPI_LINE_MAX_LEN for ln in kpi_lines):
        return None
    if not _lines_look_structured_kpi(kpi_lines):
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

        if not _is_valid_kpi_label(label):
            return None

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


def _is_valid_kpi_label(label: str) -> bool:
    """kpi ラベルとして妥当か（迷ったら False）。"""
    if not label or len(label) > _KPI_LABEL_MAX_LEN:
        return False
    if _MID_SENTENCE_END_RE.search(label):
        return False
    if _MID_SENTENCE_START_RE.search(label):
        return False
    return True


def _lines_look_structured_kpi(lines: list[str]) -> bool:
    """短い指標名＋値が規則的に並ぶ構造かどうか。"""
    structured = 0
    for line in lines:
        if re.match(r"^.+?[:：]\s*.+", line):
            structured += 1
        elif _KPI_KEYWORDS.search(line) and len(line) <= 30:
            structured += 1
    return structured >= 3


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


def _is_spurious_table_heading(text: str) -> bool:
    """表セル由来の短い見出し（1Q / 2月 / 年度 等）かどうか。"""
    t = text.strip()
    if len(t) <= 3:
        return True
    if _SPURIOUS_HEADING_RE.match(t):
        return True
    # 「年度 11月 12月 1月」のような月名羅列
    if t.startswith("年度") and "月" in t:
        return True
    return False


def _lines_outside_tables(lines: list[str]) -> list[str]:
    """Markdown 表ブロック内の行を除いた行リストを返す。"""
    result: list[str] = []
    i = 0
    while i < len(lines):
        if is_markdown_table_row(lines[i]):
            while i < len(lines) and is_markdown_table_row(lines[i]):
                i += 1
            continue
        result.append(lines[i])
        i += 1
    return result


def _lines_before_first_table(lines: list[str]) -> list[str]:
    """最初の Markdown 表より前の行だけを返す。"""
    before: list[str] = []
    for line in lines:
        if is_markdown_table_row(line):
            break
        before.append(line)
    return before


def _is_valid_cover_title(text: str) -> bool:
    """表紙タイトル候補として妥当かどうか。"""
    if not text or not text.strip():
        return False
    stripped = text.strip()
    if _is_date_only(stripped):
        return False
    if _PAREN_ONLY_RE.match(stripped):
        return False
    if is_markdown_table_row(stripped) or stripped.startswith("|"):
        return False
    if _is_spurious_table_heading(stripped):
        return False
    return True


def _clean_pdf_stem_for_title(stem: str) -> str:
    """PDF ファイル名から表紙タイトル候補を得る。"""
    name = stem.strip()
    while True:
        cleaned = _STEM_DATE_SUFFIX_RE.sub("", name).strip(" _-")
        if cleaned == name or not cleaned:
            break
        name = cleaned
    return name or stem


def _stem_usable_as_cover(stem: str) -> bool:
    """ファイル名を表紙タイトルのフォールバックに使えるか。"""
    candidate = _clean_pdf_stem_for_title(stem)
    if not candidate:
        return False
    if candidate.lower() in _GENERIC_STEM_NAMES:
        return False
    return _is_valid_cover_title(candidate)


def _resolve_cover_title(
    text: str,
    pdf_stem: str,
    user_title: str | None,
) -> str:
    """表紙タイトルを決定する（人間入力 > ファイル名 > 本文推測）。"""
    if user_title and user_title.strip():
        return user_title.strip()

    stem_candidate = _clean_pdf_stem_for_title(pdf_stem)
    if _stem_usable_as_cover(pdf_stem):
        return stem_candidate

    found = _find_cover_title(text, pdf_stem)
    if found and _is_valid_cover_title(found):
        return found

    return stem_candidate or pdf_stem


def _parse_heading_level(line: str) -> tuple[int, str] | None:
    """見出し行のレベルとタイトル文字列を返す。"""
    stripped = line.strip()
    for level, pattern in _HEADING_PATTERNS:
        m = pattern.match(stripped)
        if m:
            return level, m.group(1).strip()
    return None


def _find_cover_title(text: str, pdf_stem: str) -> str:
    """表紙タイトルを選定する。

    決算PDFでは表セルが ``## 1Q`` 等の H2 として誤抽出されるため、
    1. 最初の表より前の見出し / プレーンテキストを最優先
    2. 表ブロック外の行から最初の有効 H2
    3. 短い四半期・月名見出しは除外
  """
    lines = text.splitlines()

    # フェーズ1: 最初の Markdown 表より前（文書タイトルは通常ここにある）
    for line in _lines_before_first_table(lines):
        parsed = _parse_heading_level(line)
        if parsed is not None:
            _, title = parsed
            if _is_valid_cover_title(title):
                return title
        stripped = line.strip()
        if (
            stripped
            and not _is_date_only(stripped)
            and _parse_heading_level(line) is None
            and not is_markdown_table_row(stripped)
            and len(stripped) >= 4
            and not _is_spurious_table_heading(stripped)
            and not _PAREN_ONLY_RE.match(stripped)
        ):
            return stripped

    # フェーズ2: 表ブロック外の行から最初の有効 H2
    for line in _lines_outside_tables(lines):
        parsed = _parse_heading_level(line)
        if parsed is None:
            continue
        level, title = parsed
        if level == 2 and _is_valid_cover_title(title):
            return title

    # フェーズ3: 表ブロック外の最初の有効 H1
    for line in _lines_outside_tables(lines):
        parsed = _parse_heading_level(line)
        if parsed is None:
            continue
        level, title = parsed
        if level == 1 and _is_valid_cover_title(title):
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
    return _parse_heading_level(line) is not None


def _extract_heading(line: str) -> str | None:
    """見出し行からタイトル文字列を取り出す。"""
    parsed = _parse_heading_level(line)
    if parsed is None:
        return None
    return _clean_inline_text(parsed[1])


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
    """箇条書き記号・見出し記号・HTMLタグ・末尾句点を除去する。"""
    stripped = _clean_inline_text(line)
    stripped = _HEADING_MARKERS_RE.sub("", stripped).strip()
    for pattern in (_BULLET_RE, _NUMBERED_RE):
        m = pattern.match(stripped)
        if m:
            stripped = m.group(1).strip()
            break
    if stripped.endswith("。"):
        stripped = stripped[:-1]
    return stripped


def _clean_inline_text(text: str) -> str:
    """PDF抽出由来のインライン装飾タグを除去する。"""
    cleaned = _HTML_BREAK_RE.sub(" ", text)
    cleaned = _HTML_TAG_RE.sub("", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip()


def _sanitize_value(value: Any) -> Any:
    """slideData の文字列値を再帰的に正規化する。"""
    if isinstance(value, str):
        return _clean_inline_text(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _sanitize_value(item) for key, item in value.items()}
    return value


def _sanitize_slide(slide: dict[str, Any]) -> dict[str, Any]:
    """最終JSONに入る直前で title / points / table セル等を正規化する。"""
    return {key: _sanitize_value(value) for key, value in slide.items()}
