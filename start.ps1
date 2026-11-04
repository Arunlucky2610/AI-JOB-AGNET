$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath 'node_modules')) { throw 'Run npm install first. See README.md.' }
$apiProcess = Start-Process -FilePath (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') -ArgumentList '-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru
try { npm run dev } finally { if (-not $apiProcess.HasExited) { Stop-Process -Id $apiProcess.Id } }
