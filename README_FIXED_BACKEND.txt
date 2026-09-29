SUPPORTNOVA - FIXED BACKEND

Backend: FastAPI + Python + SQLite
Backend URL: http://localhost:8000
API docs: http://localhost:8000/docs
Health check: http://localhost:8000/api/health

EASIEST WINDOWS START:
1. Double-click RUN_BACKEND.bat from the project root.
2. Wait for: Uvicorn running on http://0.0.0.0:8000
3. Open http://localhost:8000/docs

VS CODE / POWERSHELL:
cd backend
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

Do NOT use Activate.ps1 if PowerShell execution policy blocks scripts. The commands above use the venv Python directly.

DEMO ACCOUNTS:
Admin: admin@supportnova.demo / Admin#12345
Agent: agent@supportnova.demo / Agent#12345
Customer: customer@supportnova.demo / Customer#12345

The repaired source adds the missing audit/security/utils/schemas/python_validation modules, makes prompt/knowledge-base assets self-contained, and fixes validation-check JSON persistence.
