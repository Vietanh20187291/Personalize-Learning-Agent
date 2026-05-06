@echo off
REM Start FastAPI Backend
REM Usage: Just run this file - it starts uvicorn on port 8010 with the root .venv

for /f "tokens=5" %%p in ('netstat -ano ^| findstr :8010 ^| findstr LISTENING') do (
	taskkill /PID %%p /F >nul 2>&1
)

cd /d "%~dp0backend"
set PYTHONIOENCODING=utf-8
echo Starting FastAPI Backend on http://localhost:8010
"%~dp0.venv\Scripts\python.exe" -m uvicorn main:app --reload --port 8010
pause
