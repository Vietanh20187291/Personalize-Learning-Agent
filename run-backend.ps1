# Start FastAPI Backend (PowerShell version)
# Usage: .\run-backend.ps1

$backendPath = Join-Path $PSScriptRoot "backend"
$pythonPath = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

try {
    $listeners = Get-NetTCPConnection -LocalPort 8010 -State Listen -ErrorAction SilentlyContinue
    foreach ($listener in $listeners) {
        try { Stop-Process -Id $listener.OwningProcess -Force -ErrorAction Stop } catch {}
    }
} catch {}

Set-Location $backendPath
$env:PYTHONIOENCODING = "utf-8"

Write-Host "Starting FastAPI Backend on http://localhost:8010" -ForegroundColor Green
& $pythonPath -m uvicorn main:app --reload --port 8010
