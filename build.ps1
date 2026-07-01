# Slide-Maker ビルドスクリプト
# 使い方: .\build.ps1 [-OneFile]

param(
    [switch]$OneFile
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Venv = Join-Path $Root ".venv"
$Dist = Join-Path $Root "dist"
$Build = Join-Path $Root "build"

# venv 作成
if (-not (Test-Path $Venv)) {
    python -m venv $Venv
}

$Python = Join-Path $Venv "Scripts\python.exe"
$Pip = Join-Path $Venv "Scripts\pip.exe"

& $Pip install -q -r (Join-Path $Root "requirements.txt")
& $Pip install -q -r (Join-Path $Root "requirements-build.txt")

# クリーン
if (Test-Path $Dist) { Remove-Item -Recurse -Force $Dist }
if (Test-Path $Build) { Remove-Item -Recurse -Force $Build }

$PyInstaller = Join-Path $Venv "Scripts\pyinstaller.exe"
$Args = @(
    "--name", "PDF2PPTX",
    "--windowed",
    "--noconfirm",
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
    Write-Host "Build complete: $Dist"
} finally {
    Pop-Location
}
