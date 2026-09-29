"""Trusted Pakistan SIM / telecom knowledge given to Nova so it answers real questions accurately.

Keep facts general and widely true in Pakistan. Operator-specific codes and prices change,
so Nova is told to point customers to the official app/helpline for exact figures.
"""

KNOWLEDGE = """
SIM ownership & registration (PTA rules, Pakistan):
- To check how many SIMs are registered on a CNIC: SMS the CNIC number (without dashes) to 668. Also available on the PTA DIRBS / "SIM information" service.
- Max 8 SIMs per CNIC across all operators (max 5 per operator for most individuals).
- New SIM, SIM replacement (duplicate SIM) and ownership transfer need the owner's original CNIC and biometric (thumb) verification at an operator franchise/service centre. It cannot be done over chat.
- Unknown SIM on your CNIC: visit a franchise with CNIC to deactivate it, or report to the operator/PTA.
- Mobile Number Portability (MNP): keep the same number and switch operator; visit the new operator's franchise with CNIC and biometrics. Takes about 4 working days.
- Mobile phones must be PTA-approved (DIRBS). Check IMEI by sending the 15-digit IMEI to 8484.

Lost / stolen / snatched SIM or phone:
- Immediately call the operator helpline to block the SIM (only the helpline/agent can block it).
- Report to police (15) and the PTA / operator for phone blocking via IMEI; file an FIR if snatched.
- Get a duplicate SIM on the same number with CNIC + biometrics at a franchise.
- Secure JazzCash/Easypaisa/bank apps linked to the number and change passwords.

SIM not working / "No service" / "SIM not detected":
1. Restart the phone. 2. Remove and reinsert the SIM, clean the gold chip. 3. Try the SIM in another phone.
4. Check airplane mode is off and network mode is set to Auto (4G/3G/2G).
5. If it works in another phone, the phone slot/settings are the issue; if not, the SIM may be damaged or blocked -> SIM replacement at a franchise.
- SIM blocked due to non-verification, inactivity (usually ~90 days without usage) or a complaint: visit franchise with CNIC.

Mobile internet / data not working:
1. Check you have an active data bundle and balance. 2. Mobile data ON, airplane mode OFF.
3. Correct APN for the operator (reset APN to default). 4. Restart phone, switch network mode to 4G/Auto.
5. Check if the issue is only in one area (network coverage) - then it's a network complaint with location details.

Calls / signal problems: note the exact location, time, and whether calls drop, don't connect, or voice is unclear; this goes to the network team.

Balance, recharge, packages:
- Balance check codes, package subscription codes and prices differ by operator and change often -> tell the customer to use the operator's official app or dial the operator's balance code; never invent a code or price.
- Recharge not received: collect amount, date/time, method (card, JazzCash, Easypaisa, bank, retailer) and transaction ID, then register a complaint. Advance/loan balance is deducted on next recharge.
- Unwanted deductions / VAS subscriptions: customer can ask the helpline to unsubscribe value-added services; refunds only after agent verification.

Fraud & scams:
- No operator, bank or PTA will ever ask for OTP, PIN or password. Fake "prize/lucky draw", "BISP" or "account blocked" calls are scams.
- Report fraud calls/SMS to PTA complaint portal or forward scam SMS to 9000 (PTA spam reporting); for financial fraud contact the bank/wallet and FIA Cyber Crime (helpline 1799).

Harassment / threatening calls: advise not to engage, save evidence (number, time, screenshots), report to PTA / FIA Cyber Crime (1799) and police (15); Nova registers a priority complaint.

Useful numbers: Police 15, Rescue 1122, FIA Cyber Crime 1799, PTA complaint portal complaint.pta.gov.pk.
"""
