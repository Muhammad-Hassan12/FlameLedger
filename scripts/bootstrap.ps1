param([switch]$WithModel, [switch]$ForExport)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed' }
}
& ./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
if ($WithModel -or $ForExport) {
    & ./.venv/Scripts/python.exe -m pip install torch==2.11.0+cpu --index-url https://download.pytorch.org/whl/cpu
    if ($LASTEXITCODE -ne 0) { throw 'CPU PyTorch installation failed' }
    & ./.venv/Scripts/python.exe -m pip install -r requirements-ml.txt
    if ($LASTEXITCODE -ne 0) { throw 'Model dependency installation failed' }
}
if ($ForExport) {
    & ./.venv/Scripts/python.exe -m pip install torchvision==0.26.0+cpu --index-url https://download.pytorch.org/whl/cpu
    if ($LASTEXITCODE -ne 0) { throw 'Builder processor dependency installation failed' }
}
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
Write-Output 'Ready. See README.md for build and launch commands.'
