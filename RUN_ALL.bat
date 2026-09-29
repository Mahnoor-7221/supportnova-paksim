@echo off
set "ROOT=%~dp0"
echo ================================================
echo SupportNova - Backend + Frontend
echo ================================================
echo.
where python >nul 2>&1
if errorlevel 1 (
  echo Python is not installed. Install Python 3.11+ and try again.
  pause
  exit /b 1
)
where node >nul 2>&1
if errorlevel 1 (
  echo Node.js is not installed. Install Node.js 18+ and try again.
  pause
  exit /b 1
)

start "SupportNova Backend" cmd /k ""%ROOT%RUN_BACKEND.bat""
start "SupportNova Frontend" cmd /k ""%ROOT%RUN_FRONTEND.bat""

echo Backend and frontend launch windows have been opened.
echo Backend:  http://localhost:8000
echo Frontend: http://localhost:5173
pause
