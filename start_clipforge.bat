@echo off
title ClipForge - AI Video to Shorts Engine
echo ========================================================
echo               CLIPFORGE LAUNCHER
echo ========================================================
echo Starting Backend API (FastAPI) on http://127.0.0.1:8000...
start "ClipForge Backend" cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

timeout /t 3 /nobreak >nul

echo Starting Frontend UI (Next.js) on http://localhost:3000...
start "ClipForge Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo ========================================================
echo ClipForge is running!
echo Frontend: http://localhost:3000
echo Backend : http://127.0.0.1:8000
echo ========================================================
pause
