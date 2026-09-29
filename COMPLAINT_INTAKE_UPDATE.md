# Complaint intake update (Nova chat)

Problem: chatbot complaints were saved only for "critical" issues, so a normal issue
(e.g. "SIM not detected") never reached My Complaints. There was also no check that the
customer really owns a PakSim number.

New flow (backend/app/nova/assistant.py):
1. Customer describes a problem in Nova.
2. No SIM on the account  -> Nova says "PakSim SIM registered nahi hai", complaint NOT saved.
3. Has a SIM              -> Nova asks for the PakSim mobile number.
4. Number not in system   -> "PakSim par registered nahi hai" (3 tries, or type "cancel").
   Number of another user -> "aapke account se linked nahi hai".
5. Number belongs to the customer -> complaint is saved automatically, assigned to the
   least-loaded agent, appears at the top of My Complaints, and Nova shows the code
   (with the usual troubleshooting steps below it).
Other rules: same problem in the same chat is not filed twice; greetings, balance,
package/SIM purchase and status questions do not ask for a number; typing
"complaint register karni hai" always starts the flow.

Also: POST /api/complaints now rejects customers without a SIM (403), and accepts an optional
`mobile_number` that must belong to the customer (staff are not restricted).

Tests: backend/tests/test_nova_complaint_intake.py  (run: python -m pytest tests -q)
