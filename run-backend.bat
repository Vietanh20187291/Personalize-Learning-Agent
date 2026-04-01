@echo off
REM Start FastAPI Backend
REM Usage: Just run this file - it will automatically activate venv and start uvicorn on port 8000

cd /d "%~dp0backend"
call ..\backend_env\Scripts\activate.bat
echo Starting FastAPI Backend on http://localhost:8000
python -m uvicorn main:app --reload --port 8000
pause
