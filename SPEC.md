# PDF → PowerPoint 変換ツール 開発指示書

## 0. このドキュメントの位置づけ

これは Cursor でゼロから開発するデスクトップアプリの完全設計書である。実装者（AI/人間）はこの指示書に厳密に従うこと。不明点は「セクション9. 実装順序」の第1弾から着手し、動く MVP を最優先で完成させること。

## 1. プロダクト概要

Windows 11 上で単独 EXE として動作する、PDF を高品質な PowerPoint（.pptx）に変換する軽量ツール。単なるページ画像化ではなく、PDF の内容を「論理的なスライド設計図（slideData JSON）」という中間表現に変換し、その設計図を人間が確認・修正したうえで、多彩なレイアウトパターンで美しいスライドに描画することを核とする。設計思想は「魔人式スライド生成」を踏襲し、JSON 生成と描画エンジンを完全分離する。

## 2. 動作環境・前提

対象 OS は Windows 11。Microsoft Office はインストール済みだが、**本アプリは描画に python-pptx を用い Office や COM には一切依存しない**（生成した pptx をユーザーが Office で開く用途のみ）。最終成果物は PyInstaller による単一 EXE。スライドは **16:9 ワイド（幅 12192000 EMU × 高さ 6858000 EMU）固定**とする。GUI は Python 標準の tkinter を用い、追加 GUI 依存を持たない。

### 第1弾の範囲外（明記）

- スキャン PDF / OCR フォールバック（PyMuPDF4LLM で抽出できない PDF は警告付き最低限スライド）
- `notes` の PPTX スピーカーノート埋め込み（スキーマ検証のみ対応、描画は後続）
- LLM モードの本実装（UI 上はスタブ）

## 3. コア設計原則（厳守）

最重要原則は、**② JSON 生成部と ⑤ 描画エンジン部の完全分離**である。両者を繋ぐのは「slideData スキーマ（セクション6）」だけであり、JSON 生成の方式（LLM/ルールベース/手動）が何であっても、描画エンジンは一切変更しないこと。描画エンジンは `RENDERERS` という「パターン名→描画関数」の辞書によるディスパッチ方式で実装し、新パターン追加が既存コードを壊さない構造にする。1 枚のスライド描画でエラーが発生しても `try-except` で捕捉し、そのスライドをスキップして全体処理は継続する（魔人式の SAFETY 思想）。

### validator と renderer の役割分担

- **validator（strict）**: UI の「検証」および PPTX 作成直前は未知 `type` をエラーとする。
- **renderer（fallback）**: 直接呼び出し時の安全弁として未知 `type` は `content` で代替描画する。

## 4. ユーザーフロー（UI 要件）

アプリは以下の 5 ステップを 1 画面で完結させる。

1. **PDF 選択** — ファイル選択ダイアログで PDF を 1 つ指定
2. **JSON 化** — 「LLM モード」「ルールベースモード」をラジオボタンで選択し、実行ボタンで slideData(JSON) を生成
3. **JSON 表示** — 生成された JSON を画面中央の大きな編集可能テキストエリアに `indent=2` で整形表示
4. **確認・修正** — テキストエリア上で直接 JSON を編集し、「検証」ボタンで構文とスキーマの妥当性をチェック
5. **スライド作成** — 出力先フォルダを指定し「スライド作成」ボタンで pptx を生成

UI レイアウト: 上部に PDF 選択とモード選択、中央に広い JSON 編集エリア、下部に検証・出力先選択・スライド作成ボタン。処理中はボタンを無効化し、ステータスラベルで状態を表示する。

## 5. モジュール構成

| ファイル | 責務 |
|---|---|
| `app.py` | エントリポイント・tkinter UI のみ |
| `extractor.py` | PDF からの生テキスト抽出（PyMuPDF4LLM） |
| `json_builder.py` | slideData 生成の司令塔 |
| `llm_mode.py` | LLM による JSON 生成（第1弾はスタブ） |
| `rule_mode.py` | ルールベースの JSON 生成 |
| `validator.py` | slideData の構文・スキーマ検証 |
| `renderer.py` | 描画エンジン本体 |
| `schema.py` | slideData スキーマ定義・定数 |

## 6. slideData スキーマ定義

トップレベルは **スライドオブジェクトの配列**。各オブジェクトは必ず `type` キーを持つ。全オブジェクトに任意で `notes`（プレーンテキスト）を持てる。

### 第1弾パターン

- `title`: `{ "type":"title", "title":str, "date":"YYYY.MM.DD", "notes"?:str }`
- `section`: `{ "type":"section", "title":str, "sectionNo"?:int, "notes"?:str }`
- `content`: `{ "type":"content", "title":str, "subhead"?:str, "points"?:[str], "twoColumn"?:bool, "columns"?:[[str],[str]], "notes"?:str }`
- `agenda`: `{ "type":"agenda", "title":str, "subhead"?:str, "items":[str], "notes"?:str }`
- `closing`: `{ "type":"closing", "notes"?:str }`

### 第2弾以降

`kpi`, `barCompare`, `compare`, `table`, `pyramid`, `triangle`, `timeline`, `process`, `cycle` — 詳細は元設計書セクション6参照。

## 7. テキスト・描画ルール

- 箇条書き要素に改行（`\n`）を含めない
- 箇条書き文末に句点「。」を付けない
- 禁止記号: `■`, `→`
- 自動番号描画パターンではテキスト先頭に番号を含めない
- インライン強調: `**太字**` と `[[重要語]]`（本文カラムのみ）
- `notes` にはマークアップ記法を含めない

## 8. デザイン定数（schema.py）

色・フォント・寸法は `schema.py` に一元管理。日本語フォントは Meiryo / Yu Gothic UI を優先し、無い環境では標準サンセリフにフォールバック。

## 9. 実装順序

### 第1弾（MVP）

`app.py` UI、`extractor.py`、`validator.py`、`rule_mode.py`、`renderer.py`（5 パターン）、LLM モードはスタブ。

### 第2弾

`kpi` / `barCompare` / `compare` / `table` と rule_mode 強化。

### 第3弾

図形系 `pyramid` / `triangle` / `timeline` / `process` / `cycle`。

### 第4弾

LLM モード本実装。

## 10. LLM モード実装方針（llm_mode.py）

**PDF-SCAN からは PDF 抽出・設定ファイル・GUI/CLI 分離パターンを参照する。** LLM API キー管理・LLM 呼び出し・JSON 修復は PDF-SCAN に存在しないため、第4弾で新規実装する。魔人式プロンプトをシステムプロンプトとし、返却 JSON は必ず `validator.py` を通す。

## 11. 描画エンジン（renderer.py）

`RENDERERS` 辞書によるディスパッチ。`build_pptx(slide_data, out_path)` がエントリポイント。

## 12. 検証ロジック（validator.py）

- `validate_json_text(text) -> (data | None, errors)`
- `validate_slide_data(data) -> errors`

第1段: JSON 構文。第2段: スキーマ（配列、`type`、必須プロパティ、固定数制約、禁止記号）。

## 13. EXE 化

依存: `pymupdf4llm`, `python-pptx`。ビルドはまず `--onedir` で検証し、最後に `--onefile --windowed` を検討。

出力ファイル名: 入力 PDF の stem + `.pptx`。同名衝突時はタイムスタンプ付与。

## 14. 完成の定義

第1弾: 任意のテキスト主体 PDF をルールベースで JSON 化し、UI で確認・検証・5 パターンの 16:9 pptx 出力ができること。
