# PakSim Agent Workspace — Live Complaint Flow

Implemented agent flow:

Customer → Nova chatbot → complaint analysis → agent assignment → Agent queue → same complaint conversation → Agent reply/action → Customer sees the reply in the same thread.

## Agent UI
- My Dashboard: only the authenticated agent's live workload.
- My Complaints: only assigned live customer cases.
- Urgent Queue: P1/P2 or Critical/High cases.
- In Progress / Waiting / Escalated / Resolved queues.
- Knowledge Base remains available.
- Removed admin-style management/report/security navigation from the agent sidebar.

## Agent case actions
- Reply to customer
- Approve / continue
- Request information
- Resolve
- Escalate
- Reject with a customer-facing reason
- Reopen resolved/rejected cases

Important: reply/action messages are stored in the same Nova `AssistantSession` linked to the complaint. Customer chat/history and the complaint detail live thread therefore show the agent response in the same conversation.

## Data rules
- Agent endpoints are server-filtered by `assigned_agent_id`.
- Dataset/demo cases are excluded from the live agent queue.
- Live chatbot-created cases are automatically assigned to the least-loaded active agent.
- Complaint `source_session_uuid` links a live complaint to the exact customer chatbot conversation.
- Every important agent action writes complaint history and audit log entries.

## Validation performed
- Python backend compile check passed.
- Existing backend tests: 14 passed with `PYTHONPATH=.`.
- Live API smoke test for agent dashboard, case detail, reply and request-information action passed.
- Frontend TS/TSX syntax transpilation check passed for 55 files.
- Full Vite build was not run in this environment because npm registry dependencies were not available locally.
