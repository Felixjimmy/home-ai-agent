$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
$workerPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $workerPython -m app.document_worker
exit $LASTEXITCODE
