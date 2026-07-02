# Slide-Maker ビルドスクリプト
# 使い方: .\build.ps1 [-OneFile] [-SkipModelCopy]

param(
    [switch]$OneFile,
    [switch]$SkipModelCopy
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Venv = Join-Path $Root ".venv"
$Dist = Join-Path $Root "dist"
$Build = Join-Path $Root "build"
$DistApp = Join-Path $Dist "PDF2PPTX"

# venv 作成
if (-not (Test-Path $Venv)) {
    python -m venv $Venv
}

$Python = Join-Path $Venv "Scripts\python.exe"
$Pip = Join-Path $Venv "Scripts\pip.exe"

& $Pip install -q -r (Join-Path $Root "requirements.txt")
& $Pip install -q -r (Join-Path $Root "requirements-build.txt")
& $Pip install -q "llama-cpp-python>=0.2.90" --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu

# クリーン
if (Test-Path $Dist) { Remove-Item -Recurse -Force $Dist }
if (Test-Path $Build) { Remove-Item -Recurse -Force $Build }

$PyInstaller = Join-Path $Venv "Scripts\pyinstaller.exe"
$Args = @(
    "--name", "PDF2PPTX",
    "--windowed",
    "--noconfirm",
    "--collect-all", "llama_cpp",
    (Join-Path $Root "app.py")
)

if ($OneFile) {
    $Args = @("--onefile") + $Args
} else {
    $Args = @("--onedir") + $Args
}

Push-Location $Root
try {
    & $PyInstaller @Args

    # EXE 実行時は PDF2PPTX.exe 同階層の model/ を参照する
    $SrcModel = Join-Path $Root "model"
    if (-not $SkipModelCopy -and (Test-Path $SrcModel)) {
        $DstModel = Join-Path $DistApp "model"
        New-Item -ItemType Directory -Force -Path $DstModel | Out-Null
        Copy-Item -Path (Join-Path $SrcModel "*.gguf") -Destination $DstModel -Force
        Write-Host "Model copied to: $DstModel"
    }

    Write-Host "Build complete: $Dist"
} finally {
    Pop-Location
}
