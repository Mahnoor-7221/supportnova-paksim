@echo off
cd /d "%~dp0frontend"
where node >nul 2>&1
if errorlevel 1 (
  echo Node.js is not installed. Install Node.js 18+ and run this again.
  pause
  exit /b 1
)
if not exist "node_modules\.bin\vite.cmd" (
  echo Installing frontend dependencies...
  call npm install
  if errorlevel 1 (
    echo.
    echo Frontend dependency installation failed.
    pause
    exit /b 1
  )
)
echo.
echo Starting SupportNova frontend on http://localhost:5173 ...
echo Keep this window open while using the website.
call npm run dev
pause
