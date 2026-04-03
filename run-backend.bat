@echo off
REM Start FastAPI Backend
REM Usage: Just run this file - it will automatically activate venv and start uvicorn on port 8000

for /f "tokens=5" %%p in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
	taskkill /PID %%p /F >nul 2>&1
)

cd /d "%~dp0backend"
call ..\.venv\Scripts\activate.bat
echo Starting FastAPI Backend on http://localhost:8000
python -m uvicorn main:app --reload --port 8000
pause
