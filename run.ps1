param([int]$Port = 9000)
$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Project virtualenv not found at $python. Create it and install requirements first."
}

Set-Location -LiteralPath $projectRoot
$sourceRoot = Join-Path $projectRoot "src"
$env:PYTHONPATH = $sourceRoot
& $python -m uvicorn app.main:app --reload --port $Port --app-dir $sourceRoot
exit $LASTEXITCODE
