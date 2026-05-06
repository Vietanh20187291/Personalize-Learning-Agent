@echo off
REM Quick dev server startup batch
REM Usage: dev-start.bat

echo.
echo Killing existing processes...
for /f "tokens=5" %%a in ('netstat -aon ^| find "LISTENING" ^| find ":8000 " ^| find ":3000 " ^| find ":3001 "') do taskkill /PID %%a /F 2>nul

echo Processes killed

echo.
echo Starting backend and frontend...
echo Backend on http://127.0.0.1:8000
echo Frontend on http://127.0.0.1:3000
echo.

start "Backend" cmd /k "cd /d %~dp0backend && set PYTHONIOENCODING=utf-8 && ..\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000"
timeout /t 2 /nobreak
start "Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo Done!
