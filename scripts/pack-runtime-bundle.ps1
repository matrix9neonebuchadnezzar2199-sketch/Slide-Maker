# runtime/ を ZIP に固め、SHA256 マニフェストを生成（Glaux embedded runtime 相当）
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Runtime = Join-Path $Root "runtime"
$Assets = Join-Path $Root "assets"
$ZipOut = Join-Path $Assets "runtime-bundle.zip"
$ShaOut = Join-Path $Assets "runtime-bundle.sha256"

if (-not (Test-Path (Join-Path $Runtime "llama-server.exe"))) {
    throw "runtime/llama-server.exe not found. Run scripts\bootstrap-runtime.ps1 first."
}

New-Item -ItemType Directory -Force -Path $Assets | Out-Null
if (Test-Path $ZipOut) { Remove-Item -Force $ZipOut }

Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($Runtime, $ZipOut)

$hash = (Get-FileHash -Algorithm SHA256 $ZipOut).Hash.ToLower()
Set-Content -Path $ShaOut -Value $hash -NoNewline -Encoding ascii
Write-Host "Packed: $ZipOut"
Write-Host "SHA256: $hash"
