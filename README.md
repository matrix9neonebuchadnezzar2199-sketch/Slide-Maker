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
| 既定 | `Slide-Maker/model/gemma-4-E2B-it-qat-UD-Q2_K_XL.gguf`（`Slide-Maker.exe` と同階層の `model/`） |
| フォールバック | 上記が無い場合は `model/*.gguf` の先頭 |
| 環境変数 | `SLIDEMAKER_LLM_MODEL` に GGUF のフルパス（最優先） |

低メモリロード（Glaux 低メモリノウハウ準拠）:

- `n_ctx=1000`, `n_threads=2`, `n_batch=512`, `n_ubatch=128`
- KV キャッシュ `q8_0`, GPU オフ（`n_gpu_layers=0`）
- タイトル短縮は短い入出力前提のため ctx 1000 で十分

`llama-cpp-python` 未インストール、またはモデル未配置の場合はスキップされ、通常のルール生成結果がそのまま使われます。

## ビルド（EXE）

```powershell
.\build.ps1          # onefile（推奨・配布形）
.\build.ps1 -SkipModelCopy  # モデルコピーを省略（EXE のみ更新）
```

配布フォルダ構成（これ以外のファイルは不要）:

```
dist/PDF2PPTX/
  PDF2PPTX.exe
  model/
    gemma-4-E2B-it-qat-UD-Q2_K_XL.gguf
```

- Python / llama-cpp-python / MSVC ランタイムは **EXE に同梱**
- GGUF のみ `model/` に外部配置（Glaux と同様、巨大モデルは EXE 外）
- **実行は `dist\PDF2PPTX\PDF2PPTX.exe` のみ**（`build\` 配下は中間生成物で実行不可）

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
