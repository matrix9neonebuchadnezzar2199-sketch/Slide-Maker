# LLM モデル配置ディレクトリ

`Slide-Maker.exe` と同階層の `model/` に `*.gguf` を置きます。

例（開発環境）:

```powershell
hf download unsloth/gemma-4-E2B-it-qat-mobile-GGUF gemma-4-E2B-it-qat-UD-Q2_K_XL.gguf --local-dir model
```

環境変数 `SLIDEMAKER_LLM_MODEL` でフルパス指定も可能です。GGUF は Git に含めません。
