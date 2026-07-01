# SPEC_LLM_STAGE1.md — 分割LLM処理 第1弾「タイトル短縮」

## 0. 目的とスコープ

ルールベースが生成した slideData に対し、**長すぎるタイトルだけ**を小型ローカルLLMで1件ずつ短縮する。文書全体の再構成はしない。要点圧縮・章立て判定は本SPECの対象外(第2弾以降)。

大原則(絶対に守る):

1. **1スライド1タスク** — LLMには常に1件のタイトル文字列と単純な指示だけを渡す。slideData配列全体をLLMに渡さない。
2. **小さい入出力** — 入力は1タイトル(最大数百字)、出力は短い見出し文字列1つのみ。JSONを生成させない。
3. **必ずフォールバック** — LLMが失敗・タイムアウト・不正出力した場合は、元のタイトルをそのまま使う。全体処理は絶対に止めない。

## 1. 全体フロー(既存パイプラインへの差し込み位置)

```
extractor → rule_mode(slideData生成) → 【新規】llm_titlefix → validator → UI表示 → renderer
```

- llm_titlefix は rule_mode の直後、validator の直前に入る。
- **既定はOFF**。UIのチェックボックス「LLMでタイトルを整える(下書き補助)」がONのときだけ実行する。OFFなら従来どおり素通り。

## 2. 新規ファイル `llm_mode.py`(スタブを本実装に置換)

### 2.1 モデルロード

- `llama-cpp-python` を使用。モデルは **EXEに同梱せず**、外部パスから読む。
- モデルパスの取得順: ①環境変数 `SLIDEMAKER_LLM_MODEL` → ②既定パス `./model/` 内の `*.gguf` 最初の1件（配布版: `Slide-Maker.exe` と同階層の `model/`）。
- `config.json` は使わない（既存ツールに設定管理が無いため）。
- モデルが見つからない/ロード失敗した場合は、例外を投げず `None` を返し、呼び出し側は「LLMなしで続行」する(全スライド素通り)。UIに「モデル未検出のためLLM補助をスキップしました」と1行表示。
- ロードは1回だけ行い、プロセス内でキャッシュ(グローバル or シングルトン)。スライド毎の再ロード禁止。

### 2.2 タイトル短縮関数

```
def shorten_title(model, original_title: str) -> str
```

- 入力チェック(この関数を呼ぶ前に呼び出し側で判定):
  - `len(original_title) <= TITLE_SHORTEN_THRESHOLD`(既定30文字)なら**LLMを呼ばず**元のタイトルを返す。
  - `type` が `title`(表紙)/`section`/`closing` のスライドは**対象外**。表紙タイトルはユーザー手入力済みなので絶対に上書きしない。対象は `content` と `table` の title のみ。
- プロンプト(システム+ユーザー、日本語、極力単純に):

```
system: あなたは日本語の見出しを短くする編集者です。入力された文の内容を表す、15文字以内の簡潔な見出しだけを出力してください。説明・記号・カギ括弧・句点は付けないでください。見出し以外は一切出力しないでください。

user: 次の文を15文字以内の見出しにしてください。
文: {original_title}
見出し:
```

- 生成パラメータ: `max_tokens=32`, `temperature=0.1`, `top_p=0.9`, `stop=["\n"]`。
- **出力サニタイズ(必須)**: HTMLタグ除去、先頭記号除去、末尾句読点除去、禁止記号除去、カギ括弧除去。
- **検証つきフォールバック(必須)**: 空/1文字/20文字超/元と同一/指示文復唱 → 元タイトル。
- タイムアウト: 1件あたり最大 `LLM_TIMEOUT_SEC`(既定15秒)。

### 2.3 バッチ適用関数

```
def apply_title_fix(slide_data: list, progress_callback=None) -> tuple[list, str | None]
```

- slideData をコピーして走査。対象スライドのみ `shorten_title` を呼ぶ。
- 各スライド処理後に `progress_callback(current_index, total, "タイトル整形中")` を呼ぶ。
- 1件でも例外が出たらそのスライドは元のまま、次へ進む。
- 戻り値: `(新slide_data, ステータスメッセージ or None)`。

## 3. UI 変更(`app.py`)

- チェックボックス: `LLMでタイトルを整える(実験的・下書き補助)` — 既定OFF。
- ON時: rule_mode生成 → `apply_title_fix` → JSON表示。
- 別スレッド実行、`after` でUI更新。
- モデル未検出時はエラーにせずスキップメッセージ表示。

## 4. `schema.py` に追加する定数

```
TITLE_SHORTEN_THRESHOLD = 30
TITLE_SHORTEN_MAX = 20
LLM_TIMEOUT_SEC = 15
LLM_MAX_TOKENS = 32
LLM_TEMPERATURE = 0.1
```

## 5. `requirements-llm.txt`

- `llama-cpp-python` を任意依存として分離。
- README に「LLM補助を使う場合のみ `pip install -r requirements-llm.txt` と `model/*.gguf` 配置が必要」と明記。

## 6. テスト(`tests/test_llm.py`)

モデル本体は呼ばない。モックで周辺ロジックを検証。

## 7. 完成の定義

- チェックボックスOFFで従来と完全同一(回帰なし)。
- チェックONかつモデル配置済みで長大タイトルが短縮される。失敗分は元のまま。
- モデル未配置でもチェックONでエラーにならず素通り。
- `tests/` 全緑。
