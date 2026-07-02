# Slide-Maker llama-server runtime bootstrap (Glaux 準拠)
# ビルド時に runtime/ を生成し、pack-runtime-bundle.ps1 で EXE に内蔵する
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$Root = Split-Path -Parent $PSScriptRoot
$Runtime = Join-Path $Root "runtime"
$Cache = Join-Path $Root ".cache\bootstrap"

$LlamaZipUrl = "https://github.com/ggml-org/llama.cpp/releases/download/b9760/llama-b9760-bin-win-cpu-x64.zip"

New-Item -ItemType Directory -Force -Path $Runtime, $Cache | Out-Null

$LlamaZip = Join-Path $Cache "llama-b9760-bin-win-cpu-x64.zip"
$ExtractDir = Join-Path $Cache "llama-b9760-bin-win-cpu-x64"

if (-not (Test-Path $LlamaZip)) {
    Write-Host "Downloading llama.cpp CPU runtime (b9760)..."
    curl.exe -L --fail --output $LlamaZip $LlamaZipUrl
}

if (-not (Test-Path $ExtractDir)) {
    Write-Host "Extracting llama.cpp runtime..."
    Expand-Archive -Force -Path $LlamaZip -DestinationPath $ExtractDir
}

$Server = Get-ChildItem -Path $ExtractDir -Recurse -Filter "llama-server.exe" | Select-Object -First 1
if (-not $Server) {
    throw "llama-server.exe was not found in $ExtractDir"
}

$RuntimeSrc = Split-Path -Parent $Server.FullName
Write-Host "Copying runtime to $Runtime ..."
Get-ChildItem -Path $RuntimeSrc -File | ForEach-Object {
    Copy-Item -Force $_.FullName (Join-Path $Runtime $_.Name)
}

$Sys32 = Join-Path $env:SystemRoot "System32"
$VcRedistDlls = @(
    "vcruntime140.dll",
    "vcruntime140_1.dll",
    "msvcp140.dll",
    "msvcp140_1.dll",
    "msvcp140_2.dll",
    "concrt140.dll",
    "vccorlib140.dll",
    "vcruntime140_threads.dll"
)
Write-Host "Bundling MSVC runtime DLLs..."
foreach ($dll in $VcRedistDlls) {
    $src = Join-Path $Sys32 $dll
    if (Test-Path $src) {
        Copy-Item -Force $src (Join-Path $Runtime $dll)
        Write-Host "  + $dll"
    }
}

Write-Host "Runtime ready: $Runtime\llama-server.exe"
