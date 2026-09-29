"""Generates the public policy/guidance catalogue (120+ entries).

Single source of truth for BOTH the public /policies page (frontend bundle) and
the unauthenticated GET /api/public/policies endpoint. Every entry is general
support guidance; it links to an approved backend policy (kb_ref) so public text
stays consistent with the knowledge base Nova answers from. No customer data,
no numeric promises beyond those already in the approved KB.
Run:  python tools/generate_public_policies.py
"""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
# (category, kb_ref, [(title, guidance, escalates)])
DATA = [
("SIM & Account", "SIM-POL-01", [
 ("SIM registration and ownership", "A SIM is tied to its registered owner. Only the owner, or someone with verified consent, can request changes.", False),
 ("Identity verification before changes", "Identity is verified before any SIM or account change. Nova does not perform sensitive changes inside chat.", False),
 ("SIM activation help", "If a new SIM is not active, share the number and when you got it; guidance and a complaint are available if it stays inactive.", False),
 ("Replacement or duplicate SIM", "Replacement is handled through verified channels with the registered owner's identity documents.", True),
 ("Lost or stolen SIM", "Report it as soon as possible so the number can be blocked. This is treated as a priority case and reviewed by a human.", True),
 ("Snatched phone with SIM inside", "Report immediately; a priority complaint is created and staff review it. Follow local police reporting advice.", True),
 ("Account access problems", "For login problems use the reset options in the app. Nova never asks for your password or OTP.", False),
 ("Changing account contact details", "Contact detail changes require verification and may be routed to an agent.", False),
 ("Multiple SIMs on one identity", "Questions about SIMs linked to your identity are checked by staff, not answered from chat.", True),
 ("Someone else's SIM or account", "Requests about another person's SIM or account are declined unless authorisation is verified.", True)]),
("Mobile Internet", "NET-POL-02", [
 ("Slow internet basics", "Check data balance, signal, airplane mode toggle and a restart before raising a complaint.", False),
 ("Internet not working after recharge", "Confirm the package is active in the app and note the time; if it is not, a complaint is created.", False),
 ("Data balance questions", "Balance shown in the app is the reference. Report mismatches with a screenshot and time.", False),
 ("APN and data settings", "Confirm mobile data is on and settings are default. Reset network settings only if you are comfortable doing so.", False),
 ("Fair usage limits", "Packages follow the fair-usage terms shown at purchase; check the package details before buying.", False),
 ("Data disappearing quickly", "Review background apps and auto-updates; if usage looks wrong, raise a billing or usage complaint.", False),
 ("Social media apps not loading", "Test another app and network to isolate the issue; report with the app name and time.", False),
 ("Hotspot and tethering", "Hotspot use draws from the same package. Check the package terms for any limits.", False),
 ("Data package activation delays", "Wait a short while, restart the phone, and check the app; then report the order reference.", False),
 ("Speed complaints", "Include location, time, and a speed test result so the technical team can investigate.", False)]),
("Calls & SMS", "CALL-POL-03", [
 ("Cannot make calls", "Check balance, package validity and signal, then restart. Report the number you tried and the time.", False),
 ("Cannot receive calls", "Check call forwarding and do-not-disturb settings on the phone first.", False),
 ("Dropped or poor quality calls", "Note locations and times; repeated drops in one area are logged for the technical team.", False),
 ("SMS not sending", "Check balance, the message centre setting and the recipient number; then report it.", False),
 ("SMS not receiving", "Check storage on the phone and blocked-sender settings before reporting.", False),
 ("Unknown or unwanted calls", "Do not share personal details. Report repeated unwanted calls with numbers and times.", True),
 ("Suspicious SMS or links", "Do not click links or reply. Report it; the case is reviewed as a potential fraud attempt.", True),
 ("Call charges questions", "Charges are checked against your package terms and records; a complaint is opened for disputes.", False),
 ("Minutes bundle usage", "Bundle usage can be viewed in the app. Report mismatches with the date and time.", False),
 ("Call forwarding and waiting", "These are phone or network settings you can toggle; ask Nova for general steps.", False)]),
("Network & Coverage", "NET-POL-04", [
 ("No signal", "Restart, reseat the SIM, and try another location; then report your area and time.", False),
 ("Weak signal indoors", "Signal can drop indoors; report the address area so the pattern can be reviewed.", False),
 ("Area-wide outage reports", "Multiple reports from one area are grouped and passed to the technical team.", False),
 ("Network mode settings", "Switching between automatic and preferred network modes can help; steps vary by phone.", False),
 ("Coverage questions before buying", "Coverage varies by location. Nova gives general guidance and does not promise coverage at a specific spot.", False),
 ("Network problems while travelling", "Note the route and time; mobile coverage may vary along the way.", False),
 ("Tower or site complaints", "Site and tower concerns are logged as complaints and reviewed by the technical team.", True),
 ("Emergency services access", "In an emergency contact local emergency services directly; do not rely on chat.", True),
 ("Repeated network complaints", "Repeated issues in the same area are linked so the team sees the pattern.", False),
 ("Planned maintenance notices", "Maintenance notices appear in the app when available; check there first.", False)]),
("Balance & Billing", "BIL-POL-05", [
 ("Recharge not reflected", "Keep the transaction reference ready; a complaint is created and verified against records.", False),
 ("Wrong balance deduction", "Report with date, amount and what you were doing; the charge is verified before any correction.", False),
 ("Refund requests", "Refunds are reviewed against records. Approved corrections are applied as per the approved policy.", True),
 ("Duplicate charge", "Provide both transaction references; staff verify and respond through your complaint.", True),
 ("Unknown deduction", "Check active packages and subscriptions first, then report the amount and time.", False),
 ("Loan or credit balance questions", "Ask Nova for general information; account-specific balances are shown in the app.", False),
 ("Bill or statement questions", "Statements are provided through the app or official channels, not through chat text.", False),
 ("Payment method problems", "Never share a full card or bank number in chat. Use the official payment flow.", True),
 ("Advance or top-up mistakes", "Wrong-number top-ups are reviewed case by case; report the details promptly.", True),
 ("Tax and charge explanations", "Nova gives general information only; official charge breakdowns come from official documents.", False)]),
("Packages & Offers", "PKG-POL-06", [
 ("Choosing a package", "Compare data, minutes, SMS and validity in the Packages page before ordering.", False),
 ("Package activation", "After ordering, check the app for the active package; report if it is not active.", False),
 ("Package validity and expiry", "Validity is shown at purchase. Check the app for current status.", False),
 ("Auto-renewal", "Check package details and settings for renewal behaviour; ask Nova to explain general options.", False),
 ("Unsubscribing from a package", "Use the options in the app; if unavailable, raise a request for an agent.", False),
 ("Package price disputes", "Disputes are compared with the price shown at purchase and handled as a billing complaint.", False),
 ("Offer eligibility", "Eligibility follows the offer terms. Nova does not promise an offer that is not listed.", False),
 ("Bundled subscriptions", "Bundled perks depend on the plan. Check plan details before ordering.", False),
 ("Changing plans", "Plan changes follow the approved terms; check the app or ask Nova for general steps.", False),
 ("Group and family plans", "Group plans require the plan owner's authorisation for changes.", True)]),
("Roaming & Travel", "ROM-POL-09", [
 ("Using the SIM abroad", "Roaming availability depends on the plan and destination. Check plan details before travelling.", False),
 ("Roaming activation", "Activation options are in the app or through an agent; do not assume it is enabled by default.", False),
 ("No service while roaming", "Check roaming is enabled and try selecting a partner network manually; then report it.", False),
 ("Roaming charge questions", "Charges follow the terms in place at the time; disputes are checked by staff.", True),
 ("Data roaming safety", "Turn off background data if you want to control usage while travelling.", False),
 ("Returning from abroad", "Turn off roaming settings on your phone if not needed and restart to reconnect.", False),
 ("Lost phone while travelling", "Report immediately so the SIM can be blocked; a priority case is created.", True),
 ("International calls and SMS", "Rates depend on the plan and destination. Nova does not quote unlisted rates.", False),
 ("Wi-Fi calling and messaging apps", "Availability depends on the device and plan; check the plan details.", False),
 ("Roaming complaints", "Include country, dates and what happened so staff can review your case.", False)]),
("Number Portability", "MNP-POL-08", [
 ("Porting a number in", "Porting follows the official process with identity verification; start it from the app or through an agent.", False),
 ("Porting a number out", "Port-out requests are handled through verified channels and may need staff review.", True),
 ("Port-in status questions", "Check the status in the app; unresolved delays can be raised as a complaint.", False),
 ("Documents for porting", "Identity documents of the registered owner are typically required, as per the approved process.", False),
 ("Porting a number you do not own", "Requests for someone else's number are declined unless authorised and verified.", True),
 ("Number retained after porting", "Your number is kept as part of a completed port; report if it behaves unexpectedly.", False),
 ("Service interruptions during porting", "Short interruptions can occur while a port completes; report long ones.", False),
 ("Cancelling a port request", "Cancellation is handled through the same channel used to place it.", False),
 ("Port complaints", "Provide the request reference and dates; the case is routed to the right team.", False),
 ("Unauthorised port suspected", "Report immediately. This is a security-sensitive case reviewed by a human.", True)]),
("Security & Fraud", "SEC-POL-10", [
 ("OTP, PIN and password safety", "PakSim staff and Nova never ask for OTPs, PINs or passwords. Never share them.", True),
 ("Phishing and fake messages", "Ignore links and do not reply. Report the message so it can be reviewed.", True),
 ("Fake agent or caller", "If a caller asks for private details, end the call and report it.", True),
 ("Unauthorised activity on your number", "Report immediately with details; the case is prioritised and reviewed by a human.", True),
 ("SIM swap concerns", "Report sudden loss of service you did not cause. Staff investigate as a security case.", True),
 ("Account takeover", "Change your password, report the issue, and expect verification before changes.", True),
 ("Fraudulent charges", "Report with dates and amounts; staff verify against records.", True),
 ("Suspicious apps or links", "Install apps only from official stores and avoid unknown links.", False),
 ("Reporting a scam", "Give what you know without sharing secrets; a fraud case is opened for review.", True),
 ("Staying safe online", "Use strong unique passwords and keep your phone updated.", False)]),
("SIM Blocking & Recovery", "SIM-POL-11", [
 ("Temporary SIM block", "A temporary block protects the number while a case is reviewed.", True),
 ("Unblocking a SIM", "Unblocking requires verification and may be done by staff after review.", True),
 ("SIM blocked unexpectedly", "Report your number and what happened; staff review why it was blocked.", True),
 ("Blocked after loss or theft", "Recovery follows the approved process with identity verification.", True),
 ("Recovering a number", "Recovery depends on verification and the case; staff will guide next steps.", True),
 ("Block due to security review", "Some blocks are precautionary; staff explain what is needed to lift them.", True),
 ("Checking block status", "Status is shown in your case; ask Nova for a general explanation.", False),
 ("Multiple block requests", "Repeated requests are linked to your existing case.", False),
 ("Blocking on someone else's behalf", "Requests for another person's SIM require verified authorisation.", True),
 ("Delays in unblocking", "Raise it through your complaint reference so it can be followed up.", False)]),
("Troubleshooting Guides", "NET-POL-12", [
 ("Restart and airplane mode steps", "Toggle airplane mode for a short time and restart before reporting an issue.", False),
 ("SIM reseating", "Power off, remove and reinsert the SIM gently, then power on.", False),
 ("Software updates", "Keeping the phone updated can fix network and app problems.", False),
 ("Resetting network settings", "This clears saved networks; use it only if you are comfortable.", False),
 ("Testing with another phone", "Trying the SIM in another compatible phone helps isolate the fault.", False),
 ("Checking mobile data toggles", "Make sure mobile data and the right SIM slot are enabled.", False),
 ("Battery saver effects", "Battery saver can limit background data and notifications.", False),
 ("App-specific issues", "Clear the app cache or reinstall it before blaming the network.", False),
 ("What to include in a report", "Give the number, time, location and steps already tried.", False),
 ("When Nova will create a complaint", "If steps do not work or the issue needs staff, Nova creates a trackable complaint.", False)]),
("Complaints & Escalation", "SIM-POL-01", [
 ("Filing a complaint", "Describe your issue in your own words; Nova helps create a complaint when needed.", False),
 ("Tracking a complaint", "Use the Track page or your complaint number to see status and timeline.", False),
 ("Complaint priority", "Security-sensitive and urgent cases get higher priority than routine ones.", False),
 ("What agents can do", "Agents review complaints, request details and resolve within approved rules.", False),
 ("What admins oversee", "Admins oversee categories, rules, audit trails and overall service quality.", False),
 ("When cases escalate", "Cases escalate when rules require it, for example security, repeated failures or delays.", True),
 ("Service level targets", "Each category has a target shown in the case; delays are flagged internally.", False),
 ("Adding more details", "Reply on the complaint or in chat with more information to help resolution.", False),
 ("Reopening a case", "If a fix did not work, say so on the complaint so it can be reviewed.", False),
 ("Giving feedback", "Feedback on a resolution helps improve support quality.", False)]),
("Privacy & Data", "SEC-POL-10", [
 ("What data is used", "Data is used to provide service, verify identity and resolve complaints.", False),
 ("Data sharing", "Data is not sold; access is limited to authorised staff and is logged.", False),
 ("Sensitive details in chat", "Do not type OTPs, passwords or full card numbers; Nova masks sensitive patterns.", True),
 ("Access to your records", "Record requests follow verification and approved processes.", True),
 ("Call and chat history", "Your own chat history is visible to you in your account.", False),
 ("Correcting your details", "Update details in your profile or raise a request for verification.", False),
 ("Deleting your data", "Deletion requests are handled through verified channels, subject to record-keeping duties.", True),
 ("Audit trails", "Actions on cases are recorded to keep support traceable.", False),
 ("Third-party requests", "Requests from other people about your data are not answered without authorisation.", True),
 ("Privacy questions to Nova", "Nova gives general privacy information and escalates account-specific requests.", False)]),
("Nova AI Assistant", "SIM-POL-01", [
 ("What Nova can help with", "Nova gives guidance from approved policies and helps create complaints.", False),
 ("Languages Nova understands", "English, Urdu, Roman Urdu and Sindhi are supported for chat.", False),
 ("Answers come from approved knowledge", "Nova answers using approved knowledge and rules and does not invent policy.", False),
 ("When Nova does not know", "If a request is unsupported, Nova says so and offers a human follow-up.", True),
 ("Sensitive requests", "Requests involving identity, security or money changes are escalated rather than handled in chat.", True),
 ("Nova never asks for secrets", "Nova will never ask for OTPs, PINs or passwords.", False),
 ("Human oversight", "Humans review escalated cases, and admins can update rules.", False),
 ("Voice input", "Voice input is available where your device supports it.", False),
 ("Nova and complaints", "Nova can create a trackable complaint when self-help is not enough.", False),
 ("Limits of AI answers", "Nova gives general support guidance, not legal, financial or account-specific promises.", False)]),
]

out = []
for ci, (cat, ref, items) in enumerate(DATA, 1):
    for i, (t, g, esc) in enumerate(items, 1):
        out.append({"id": f"PUB-{ci:02d}-{i:02d}", "category": cat, "title": t,
                    "guidance": g, "escalates": esc, "kb_ref": ref})
assert len(out) >= 120, len(out)
payload = json.dumps({"count": len(out), "policies": out}, ensure_ascii=False, indent=1)
for p in (ROOT / "backend/datasets/public_policies.json", ROOT / "frontend/src/data/publicPolicies.json"):
    p.write_text(payload, encoding="utf-8")
print("wrote", len(out), "policies,", len(DATA), "categories")
