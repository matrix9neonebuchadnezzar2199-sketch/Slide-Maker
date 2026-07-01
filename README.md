# Slide-Maker (PDF2PPTX)

PDF を slideData JSON 経由で PowerPoint (.pptx) に変換する Windows 向けデスクトップツール。

リポジトリ: https://github.com/matrix9neonebuchadnezzar2199-sketch/Slide-Maker

## 機能（第1弾 MVP）

- PDF テキスト抽出（PyMuPDF4LLM）
- ルールベース slideData JSON 生成
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
| `llm_mode.py` | LLM モード（スタブ） |
| `validator.py` | JSON 検証 |
| `renderer.py` | PPTX 描画エンジン |
| `schema.py` | スキーマ・デザイン定数 |
| `SPEC.md` | 設計仕様書 |

詳細は [SPEC.md](SPEC.md) を参照。
