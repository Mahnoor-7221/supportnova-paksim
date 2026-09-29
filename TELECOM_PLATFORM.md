# SupportNova — Complete Telecom Platform

## Run

### Backend
```bash
cd backend
python -m venv venv
# Windows: .\venv\Scripts\python.exe -m pip install -r requirements.txt
#          .\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
SQLite DB is created automatically on first start. Seed loads packages, demo customer SIMs, orders, notifications.

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Demo accounts
| Role | Email | Password |
|------|-------|----------|
| Admin | admin@supportnova.demo | Admin#12345 |
| Agent | agent@supportnova.demo | Agent#12345 |
| Customer | customer@supportnova.demo | Customer#12345 |

Demo OTP for phone verification: **123456**

## New modules (real API + DB)

- **Customer profile** — phone, CNIC (masked), address, verification, OTP
- **SIMs** — list, purchase, report lost → BLOCKED, replacement → new ACTIVE SIM
- **Packages** — catalog from DB, subscribe → order + subscription
- **Orders** — SIM / PACKAGE / REPLACEMENT, customer + staff list
- **Lost SIM requests** — `/api/telecom/lost-requests` (staff)
- **Locations** — staff-only, audited, labelled **SIMULATED_DEMO_LOCATION**
- **Notifications** — registration-style events on purchase/lost/package
- **Customer Services dashboard** — `/services` KPIs + recent data (not empty)

## Customer nav
Nova · Services · My SIMs · Packages · Orders · Complaints · Track · Profile

## Admin nav additions
Orders · Registered SIMs · Customers

## API prefix
`/api/telecom/...` — see OpenAPI at http://localhost:8000/docs

## Existing features preserved
Complaints, Nova AI, Trust Gate, Agent/Admin dashboards, knowledge base, audit, security.
