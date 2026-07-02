# Slide-Maker ビルドスクリプト
# 配布形: dist/PDF2PPTX/PDF2PPTX.exe + model/*.gguf（runtime は EXE 内蔵→初回 LOCALAPPDATA 展開）
# 使い方: .\build.ps1 [-SkipModelCopy] [-SkipRuntimeBootstrap]

param(
    [switch]$SkipModelCopy,
    [switch]$SkipRuntimeBootstrap
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Venv = Join-Path $Root ".venv"
$Dist = Join-Path $Root "dist"
$Build = Join-Path $Root "build"
$DistApp = Join-Path $Dist "PDF2PPTX"
$RuntimeHook = Join-Path $Root "pyi_rth_frozen.py"
$Bootstrap = Join-Path $Root "scripts\bootstrap-runtime.ps1"
$PackBundle = Join-Path $Root "scripts\pack-runtime-bundle.ps1"
$BundleZip = Join-Path $Root "assets\runtime-bundle.zip"
$BundleSha = Join-Path $Root "assets\runtime-bundle.sha256"

# venv 作成
if (-not (Test-Path $Venv)) {
    python -m venv $Venv
}

$Python = Join-Path $Venv "Scripts\python.exe"
$Pip = Join-Path $Venv "Scripts\pip.exe"

& $Pip install -q -r (Join-Path $Root "requirements.txt")
& $Pip install -q -r (Join-Path $Root "requirements-build.txt")

if (-not $SkipRuntimeBootstrap) {
    & $Bootstrap
}
& $PackBundle

if (-not (Test-Path $BundleZip)) {
    throw "Missing $BundleZip — pack-runtime-bundle failed"
}

# クリーン（build/ は中間生成物。実行は dist/PDF2PPTX/ のみ）
if (Test-Path $Dist) { Remove-Item -Recurse -Force $Dist }
if (Test-Path $Build) { Remove-Item -Recurse -Force $Build }

$PyInstaller = Join-Path $Venv "Scripts\pyinstaller.exe"
$Args = @(
    "--onefile",
    "--windowed",
    "--noconfirm",
    "--name", "PDF2PPTX",
    "--collect-all", "pymupdf",
    "--collect-all", "pymupdf4llm",
    "--runtime-hook", $RuntimeHook,
    "--add-data", "$BundleZip;.",
    "--add-data", "$BundleSha;.",
    (Join-Path $Root "app.py")
)

# Glaux 低メモリノウハウ: MSVC ランタイムを EXE に同梱（GUI 側の 0xc0000005 回避）
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
    $DstModel = Join-Path $DistApp "model"
    if (-not $SkipModelCopy -and (Test-Path $SrcModel)) {
        New-Item -ItemType Directory -Force -Path $DstModel | Out-Null
        Copy-Item -Path (Join-Path $SrcModel "*.gguf") -Destination $DstModel -Force
        Write-Host "Model copied to: $DstModel"
    } elseif ($SkipModelCopy) {
        Write-Warning "SkipModelCopy: place *.gguf under $DstModel or AI model will not start."
    }

    $ggufFiles = @(Get-ChildItem -Path (Join-Path $DstModel "*.gguf") -ErrorAction SilentlyContinue)
    if ($ggufFiles.Count -eq 0) {
        Write-Warning "No GGUF in $DstModel — AI titles will be skipped."
    }

    Write-Host ""
    Write-Host "Build complete (distribution folder):"
    Write-Host "  $DistApp\PDF2PPTX.exe  (llama-server runtime embedded)"
    Write-Host "  $DistApp\model\*.gguf"
    Write-Host ""
    Write-Host "NOTE: Do not run from build\ — use dist\PDF2PPTX\ only."
} finally {
    Pop-Location
}
