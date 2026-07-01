# Slide-Maker (PDF2PPTX)

PDF を slideData JSON 経由で PowerPoint (.pptx) に変換する Windows 向けデスクトップツール。

リポジトリ: https://github.com/matrix9neonebuchadnezzar2199-sketch/Slide-Maker

## 機能（第1弾 MVP）

- PDF テキスト抽出（PyMuPDF4LLM）
- ルールベース slideData JSON 生成
- 任意: ローカル LLM による長いタイトル短縮補助（既定 OFF）
- JSON 手動編集・スキーマ検証
- 5 パターン描画: `title`, `section`, `content`, `agenda`, `closing`
- 16:9 ワイド PPTX 出力（python-pptx、Office 非依存）

## 起動

```powershell
cd H:\CURSOR\Slide-Maker
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python app.py
```

### LLM タイトル短縮補助（任意）

チェックボックス「LLMでタイトルを整える」を ON にすると、ルール生成後に `content` / `table` の長いタイトルだけをローカル LLM で短縮します。失敗時は元タイトルのまま続行します。

```powershell
.\.venv\Scripts\pip install -r requirements-llm.txt
```

Windows / Python 3.14 などでソースビルドが失敗する場合は CPU 用 wheel を使います:

```powershell
.\.venv\Scripts\pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
```

モデル配置（いずれか）:

| 方法 | パス |
|---|---|
| 既定 | `Slide-Maker/model/*.gguf`（`Slide-Maker.exe` と同階層の `model/`） |
| 環境変数 | `SLIDEMAKER_LLM_MODEL` に GGUF のフルパス |

`llama-cpp-python` 未インストール、またはモデル未配置の場合はスキップされ、通常のルール生成結果がそのまま使われます。

## ビルド（EXE）

```powershell
.\build.ps1          # onedir（推奨）
.\build.ps1 -OneFile # onefile
```

## プロジェクト構成

| ファイル | 責務 |
|---|---|
| `app.py` | tkinter GUI |
| `extractor.py` | PDF テキスト抽出 |
| `json_builder.py` | 生成モード振り分け |
| `rule_mode.py` | ルールベース JSON 生成 |
| `llm_mode.py` | LLM タイトル短縮補助 + 全文生成スタブ |
| `requirements-llm.txt` | LLM 補助用任意依存 |
| `SPEC_LLM_STAGE1.md` | LLM タイトル短縮 設計仕様 |
| `validator.py` | JSON 検証 |
| `renderer.py` | PPTX 描画エンジン |
| `schema.py` | スキーマ・デザイン定数 |
| `SPEC.md` | 設計仕様書 |

## テスト

```powershell
python test.py              # ユーザー行動予測テスト（7シナリオ）
.\.venv\Scripts\python -m pytest tests\ -v
```
