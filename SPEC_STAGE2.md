# 第2弾 実装指示書 — 数値・比較系4パターン

## 0. 前提と共通ルール

第2弾では `renderer.py` に `kpi`・`barCompare`・`compare`・`table` の4つの `render_*` 関数を追加し、`RENDERERS` 辞書に4行追加する。既存の第1弾コード・`schema.py` 定数・`set_jp_font()` ヘルパーを再利用し、新しい色や寸法をハードコードしないこと。

各パターンは共通して、タイトル帯（`TITLE_Y`/`SIZE_TITLE`/左アクセントバー）と、`subhead` があれば小見出し（`SUBHEAD_Y`/`SIZE_SUBHEAD`/`TEXT_SUB`）を第1弾と同じ描き方で先に描画し、その下（`BODY_Y` 以降）に各パターン固有の要素を配置する。この「タイトル＋subhead描画」は `_draw_header(slide, s)` ヘルパーにまとめ、4パターンとも冒頭で呼ぶこと。

各パターンの本文描画は `try-except` を外側（`build_pptx`）に委ねる前提で書き、関数内では例外を握りつぶさない。`rule_mode.py` 側の生成ロジック強化はセクション6にまとめる。

## 1. kpi（KPIカード）

`items`（最大4件）を横並びのカードで表示。`columns` 指定があればその列数、なければ `items` 件数（1〜4）。

カード領域横幅 `CONTENT_W`、カード間 `CARD_GAP` を (列数−1) 個引いた残りを均等割り。カード高さ `KPI_CARD_H`（約3inch）、`BODY_Y` から配置。

各カードは角丸矩形（`MSO_SHAPE.ROUNDED_RECTANGLE`）、塗り `BG_LIGHT`、枠線 `BORDER`。カード内は label / value / change を縦配置。`change` 色は `status`（`good`/`bad`/`neutral`）で `STATUS_*` を使用。カード上端にステータスバー（高さ `KPI_STATUS_BAR_H`）。

## 2. barCompare（棒グラフ比較）

`stats` 各項目を横棒で左右比較。最大6行。左ラベル領域22%、中央に2色横棒（左=`PRIMARY`、右=`ACCENT`）。`parse_number()` で正規化。`showTrends` が true のとき trend 三角を描画。

## 3. compare（対比・2カラム）

左右2カラム。ヘッダー帯左 `PRIMARY`、右 `PRIMARY_LT`。本文 `BG_LIGHT` カード、丸箇条点。

## 4. table（表）

`add_table` 使用。ヘッダー行 `PRIMARY`、データ行ゼブラ。全セル `set_jp_font()`。

## 5. RENDERERS への登録

```python
RENDERERS.update({
    "kpi": render_kpi,
    "barCompare": render_barCompare,
    "compare": render_compare,
    "table": render_table,
})
```

## 6. rule_mode.py の生成ロジック強化

正規表現ベースで kpi / barCompare / compare / table を検出。`parse_number()` は `utils.py` に共通化。

## 7. validator.py の追加検査

kpi: items 4件以内、各 item に label/value/change/status。barCompare: stats 必須。compare: 左右必須。table: 列数一致検査。

## 8. テスト追加

`tests/test_validator.py` に正常系・異常系。`test.py` にユーザー行動予測テスト。第2弾完了条件: pytest 全件 pass、4パターンが16:9で描画され色/余白が統一されていること。
