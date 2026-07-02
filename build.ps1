# Slide-Maker ビルドスクリプト
# 配布形: dist/PDF2PPTX/PDF2PPTX.exe + dist/PDF2PPTX/model/*.gguf
# 使い方: .\build.ps1 [-SkipModelCopy]

param(
    [switch]$SkipModelCopy
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Venv = Join-Path $Root ".venv"
$Dist = Join-Path $Root "dist"
$Build = Join-Path $Root "build"
$DistApp = Join-Path $Dist "PDF2PPTX"
$RuntimeHook = Join-Path $Root "pyi_rth_frozen.py"

# venv 作成
if (-not (Test-Path $Venv)) {
    python -m venv $Venv
}

$Python = Join-Path $Venv "Scripts\python.exe"
$Pip = Join-Path $Venv "Scripts\pip.exe"

& $Pip install -q -r (Join-Path $Root "requirements.txt")
& $Pip install -q -r (Join-Path $Root "requirements-build.txt")
& $Pip install -q "llama-cpp-python>=0.2.90" --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu

# クリーン（build/ は中間生成物。実行は dist/PDF2PPTX/ のみ）
if (Test-Path $Dist) { Remove-Item -Recurse -Force $Dist }
if (Test-Path $Build) { Remove-Item -Recurse -Force $Build }

$PyInstaller = Join-Path $Venv "Scripts\pyinstaller.exe"
$Args = @(
    "--onefile",
    "--windowed",
    "--noconfirm",
    "--name", "PDF2PPTX",
    "--collect-all", "llama_cpp",
    "--runtime-hook", $RuntimeHook,
    (Join-Path $Root "app.py")
)

# Glaux 低メモリノウハウ: MSVC ランタイムを EXE に同梱（0xc0000005 回避）
$VcDlls = @(
    "$env:SystemRoot\System32\vcruntime140.dll",
    "$env:SystemRoot\System32\vcruntime140_1.dll",
    "$env:SystemRoot\System32\msvcp140.dll",
    "$env:SystemRoot\System32\concrt140.dll",
    "$env:SystemRoot\System32\vccorlib140.dll",
    "$env:SystemRoot\System32\vcruntime140_threads.dll"
)
foreach ($dll in $VcDlls) {
    if (Test-Path $dll) {
        $Args += @("--add-binary", "$dll;.")
    }
}

Push-Location $Root
try {
    & $PyInstaller @Args

    $BuiltExe = Join-Path $Dist "PDF2PPTX.exe"
    if (-not (Test-Path $BuiltExe)) {
        throw "PyInstaller output not found: $BuiltExe"
    }

    New-Item -ItemType Directory -Force -Path $DistApp | Out-Null
    Move-Item -Force $BuiltExe (Join-Path $DistApp "PDF2PPTX.exe")

    $SrcModel = Join-Path $Root "model"
    if (-not $SkipModelCopy -and (Test-Path $SrcModel)) {
        $DstModel = Join-Path $DistApp "model"
        New-Item -ItemType Directory -Force -Path $DstModel | Out-Null
        Copy-Item -Path (Join-Path $SrcModel "*.gguf") -Destination $DstModel -Force
        Write-Host "Model copied to: $DstModel"
    }

    Write-Host ""
    Write-Host "Build complete (distribution folder):"
    Write-Host "  $DistApp\PDF2PPTX.exe"
    Write-Host "  $DistApp\model\*.gguf"
    Write-Host ""
    Write-Host "NOTE: Do not run from build\ — use dist\PDF2PPTX\ only."
} finally {
    Pop-Location
}
