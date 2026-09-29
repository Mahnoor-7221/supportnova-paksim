# SupportNova — UI & Flow Update

## What changed

### Professional Admin + Agent layout
- **Admin** keeps the dedicated dark sidebar console (cleaner spacing, KPI cards with hover).
- **Agent** now uses the same professional **sidebar workspace** (no more cramped top-nav only).
  - My Dashboard · Urgent Queue · My Complaints · Unassigned · In Progress · Pending · Escalated · Resolved · AI Review · Knowledge · Policies · Reports
- Content areas use more padding and clearer hierarchy so panels no longer feel “rushed”.

### Complaint assignment (central record)
- `complaints.assigned_agent_id` added (migrated automatically on backend start).
- `resolution_text` and `rejection_reason` added.
- Status lifecycle extended: `ASSIGNED`, `PENDING`, `REJECTED`.
- PUT `/api/complaints/{id}` accepts `assigned_agent_id`, `resolution_text`, `rejection_reason`.
  - Rejecting without a reason is blocked.
  - Assignment writes history and can move status to `ASSIGNED`.

### Agent dashboard
- Agent-focused hero: prioritize → resolve.
- KPI strip: Critical / High / In progress / Resolved / Escalated / Trust verified.
- Urgent callout when P1/Critical exist → link to urgent queue.

### Complaints list (staff)
- Quick filter chips: All · Urgent · New · Assigned · In Progress · Pending · Escalated · Resolved · Rejected.
- URL supports `?filter=urgent`, `?status=…`, `?q=…` (sidebar links work).

### Admin dashboard
- KPIs include **Unassigned** and **In Progress**.
- Clearer page title: Monitor · Assign · Escalate · Audit.

## Flow (unchanged principle)
One complaint = one central record (same `CMP-xxxx`).
User creates → AI analyzes → Admin/system assigns → Agent works (status + notes) → User sees updates → Accept / Reopen → Feedback → Admin reports.

## Run
Backend: see `README_FIXED_BACKEND.txt` (demo accounts listed there).
Frontend: `cd frontend && npm install && npm run dev`

New DB columns are applied automatically via `nova.migrate` on startup.
