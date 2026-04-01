# Start FastAPI Backend (PowerShell version)
# Usage: ./run-backend.ps1

$backendPath = Join-Path $PSScriptRoot "backend"
$venvPath = Join-Path $PSScriptRoot "backend_env"

Set-Location $backendPath
& "$venvPath\Scripts\Activate.ps1"

Write-Host "Starting FastAPI Backend on http://localhost:8000" -ForegroundColor Green
python -m uvicorn main:app --reload --port 8000
