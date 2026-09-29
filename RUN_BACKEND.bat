@echo off
cd /d "%~dp0backend"
if not exist "venv\Scripts\python.exe" (
  echo Creating Python virtual environment...
  python -m venv venv
)
echo Installing/updating backend dependencies...
venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Dependency installation failed. Make sure Python is installed and try again.
  pause
  exit /b 1
)
echo.
echo Starting SupportNova backend on http://localhost:8000 ...
echo Keep this window open while using the website.
venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
