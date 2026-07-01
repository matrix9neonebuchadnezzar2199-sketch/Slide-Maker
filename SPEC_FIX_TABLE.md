# 表パース修正指示書（実機フィードバック対応）

## 対象問題

1. **タイトル誤検出** — 日付行が表紙タイトルになる
2. **Markdown表の未認識** — `|...|` 行が content/compare に流れる
3. **compare 誤発火** — 注釈が compare になる
4. **巨大表** — 警告表示（エラーではない）＋ render 時フォント縮小

## rule_mode.py

- タイトル: 最初の `##` 見出しのうち日付パターン以外を採用。日付は `date` フィールドへ
- `detect_markdown_tables()`: 連続 `|...|` 行を table に変換。`|---|` 区切り対応、`<br>` 除去、空列圧縮
- パース済み表行は content/compare 入力から除外
- compare: 明示的対比語（vs、対比、メリット/デメリット、従来/新）必須

## validator.py / renderer.py

- 列数 > 8 または cells > 80 で**警告**（検証は通過）
- `render_table`: 列数多いとき `SIZE_CAPTION` に縮小、列幅均等

## 巨大表の再構成

第4弾 LLM モードのユースケース。ルールベースは「崩さず table として出す」まで。

## test.py

- Markdown 表入力 → `table` 生成、`|---|` / `<br>` が JSON に残らないこと
