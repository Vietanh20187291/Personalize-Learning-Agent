# Quick dev server startup script
# Usage: .\dev-start.ps1

Write-Host "Killing existing processes..." -ForegroundColor Yellow
$ports = @(8000, 3000, 3001, 8010)
$pids = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $ports -contains $_.LocalPort } |
    Select-Object -ExpandProperty OwningProcess -Unique
foreach ($pid in $pids) {
    try { Stop-Process -Id $pid -Force -ErrorAction Stop } catch {}
}
if ($pids) { Write-Host "Killed PIDs: $($pids -join ', ')" -ForegroundColor Green }
else { Write-Host "No processes to kill" -ForegroundColor Green }

$rootPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = Join-Path $rootPath ".venv\Scripts\python.exe"

Write-Host "`nStarting backend and frontend..." -ForegroundColor Cyan

# Start Backend
Write-Host "Backend starting on http://127.0.0.1:8000" -ForegroundColor Blue
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$rootPath\backend'; " +
    "`$env:PYTHONIOENCODING='utf-8'; " +
    "& '$pythonPath' -m uvicorn main:app --reload --port 8000"
) -NoNewWindow

Start-Sleep -Milliseconds 1000

# Start Frontend
Write-Host "Frontend starting on http://127.0.0.1:3000" -ForegroundColor Magenta
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$rootPath\frontend'; npm run dev"
) -NoNewWindow

Write-Host "`nBoth servers started." -ForegroundColor Green
