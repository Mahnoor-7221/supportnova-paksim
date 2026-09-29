# PakSim Nova — Intelligent Telecom Support AI Upgrade

## What was built

### 1. Accurate issue understanding
- Expanded deterministic classifier for English / Urdu / Roman Urdu / mixed.
- Categories: stolen/lost SIM, fraud, harassment, SIM blocked, SIM not detected, SIM not working, replacement/port, no data, calls, SMS, recharge, package, login, verification, status check, explicit ticket request, greeting.

### 2. Urgent detection
- Lost/stolen, misuse, fraud, harassment → **P1 / Critical**, auto-escalate, auto-create real complaint ticket.
- AI **never** claims "SIM blocked" unless backend/agent confirms.

### 3. Multi-turn context
- Short replies ("nahi", "haan", "still") stay on the previous category thread.
- Session stores category + clarification questions for continuity.

### 4. Troubleshooting
- Step-by-step flows for SIM, network, data, calls, SMS, recharge, packages.
- Follow-up questions adapt; no generic restart.

### 5. Ticket creation (real backend)
- Escalations and "ticket banao" create **CMP-xxxxx** on the same complaints table agents/admin use.
- Description includes conversation summary; priority/urgency/department set from classifier.

### 6. Status updates (real data)
- User can send CMP code or ask "my complaints" → live status from DB.
- No fake status invention.

### 7. Knowledge base
- Added SIM blocking + network troubleshooting policy docs.
- Answers grounded in classifier + RAG policies; no invented charges/deadlines.

### 8. Chat UI
- Quick actions: SIM, network, internet, calls, recharge, package, urgent block, status check.
- Clarification chips, escalation banner with complaint code, voice, language selector.

### Security
- Input/output firewall retained.
- Never asks for OTP / password / PIN / full card details.
- Role-based access on complaints unchanged.

## Demo accounts
See README_FIXED_BACKEND.txt
