@echo off
REM Start Next.js Frontend Development Server
REM Usage: Just run this file - it will start npm dev on port 3000

cd /d "%~dp0frontend"
echo Starting Next.js Frontend on http://localhost:3000
npm run dev
pause
