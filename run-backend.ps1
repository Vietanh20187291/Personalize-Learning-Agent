# Start FastAPI Backend (PowerShell version)
# Usage: ./run-backend.ps1

$backendPath = Join-Path $PSScriptRoot "backend"
$venvPath = Join-Path $PSScriptRoot ".venv"

# Đảm bảo backend mới luôn nắm cổng 8000 (không bị process cũ giữ cổng)
try {
	$listeners = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
	foreach ($l in $listeners) {
		try { Stop-Process -Id $l.OwningProcess -Force -ErrorAction Stop } catch {}
	}
} catch {}

Set-Location $backendPath
& "$venvPath\Scripts\Activate.ps1"

Write-Host "Starting FastAPI Backend on http://localhost:8000" -ForegroundColor Green
python -m uvicorn main:app --reload --port 8000
