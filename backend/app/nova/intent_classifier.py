"""Deterministic customer-message classifier for Nova chat (Pipeline 1 fallback layer).

Guarantees every customer message gets an issue-specific reply — never a single
generic "please give more details" repeated for every question. Safety-critical
issues (theft, fraud, harassment) are always flagged for a human agent.

Supports English, Urdu, Roman Urdu, mixed language, informal spelling.
"""
from __future__ import annotations

import re
from typing import Optional

CATEGORIES: list[dict] = [
    # ── CRITICAL / URGENT (checked first) ──────────────────────────────────
    {
        "id": "sim_stolen_snatched",
        "severity": "critical",
        "escalate": True,
        "department": "Account Security",
        "priority": "P1",
        "title": "Phone/SIM reported lost, stolen or snatched",
        "keywords": [
            "snatch", "snetch", "sanetch", "chori", "chura", "chhori", "cheen", "cheeni",
            "chheen", "looted", "loot liya", "robbed", "gunpoint", "phone kho", "mobile kho",
            "sim kho", "phone khogaya", "phone khogya", "kidnap", "stolen", "lost phone",
            "lost my phone", "lost sim", "sim lost", "phone stolen", "sim stolen",
            "block my sim", "sim block karo", "sim block kar do", "foran block",
            "immediately block", "urgent block", "sim misuse", "number misuse",
            "someone using my number", "kisi ne mera number",
        ],
        "answer": (
            "Yeh bohot sensitive maamla hai aur hum ise foran priority par le rahe hain. "
            "Ghabraiye mat — hum aapke sath hain. Please turant yeh steps follow karein:\n\n"
            "1. Apna number humein confirm karein taake support team aapki SIM ko temporarily block kar sake "
            "(main khud SIM block nahi kar sakta — yeh sirf verified agent backend se karta hai).\n"
            "2. Nearest police station mein FIR darj karwayein aur uski copy sambhal kar rakhein — duplicate SIM ke liye yeh zaroori hai.\n"
            "3. Apna original CNIC le kar nearest PakSim franchise jayein taake aapko wahi number par naya SIM mil sake.\n\n"
            "Agar is number se koi bank ya mobile wallet (JazzCash/Easypaisa) linked hai, unhein bhi abhi inform karein. "
            "Maine yeh case Security team ko bhej diya hai — ek human agent jald aap se raabta karega."
        ),
        "clarification_questions": [
            "Block / process ke liye aapka mobile number kya hai?",
            "Yeh ghatna kab aur kis area mein hui?",
            "Kya aapne FIR darj karwa li hai?",
        ],
        "escalation_reason": (
            "Lost/stolen SIM ya phone ke case mein SIM block, identity verify aur law-enforcement coordination "
            "sirf Security team kar sakti hai — AI khud SIM block nahi karta."
        ),
    },
    {
        "id": "unauthorized_charges_fraud",
        "severity": "critical",
        "escalate": True,
        "department": "Billing & Fraud",
        "priority": "P1",
        "title": "Unauthorized charge / suspected fraud",
        "keywords": [
            "fraud", "scam", "unauthorized", "without my permission", "meri permission ke baghair",
            "paise kat gaye", "paisay kat gaye", "balance kat gaya khud", "otp se paisay",
            "someone used my card", "ghalat tarah se paisay", "hacked", "hack ho gaya",
            "mera account hack", "fraudulent", "unauthorized transaction",
        ],
        "answer": (
            "Main samajh sakta hoon yeh pareshan karne wali baat hai. Sabse zaroori: agar koi call/SMS "
            "karke OTP, PIN ya password maang raha hai to kabhi share na karein — PakSim ya koi bank aap se yeh nahi maangta.\n\n"
            "Main yeh maamla foran Billing & Fraud team ko forward kar raha hoon taake transaction investigate ho "
            "aur agar galti humari taraf se hui ho to reverse ki ja sake.\n\n"
            "OTP, password ya full card details share na karein — sirf transaction details chahiye."
        ),
        "clarification_questions": [
            "Kitni amount kaati gayi aur kab (date/time)?",
            "Transaction/reference ID kya hai, agar available ho?",
            "Kya aapko koi call/SMS mila tha OTP maangte hue?",
        ],
        "escalation_reason": (
            "Unauthorized charges/fraud mein transaction verify aur reversal sirf Billing & Fraud team ke ikhtiyar mein hai."
        ),
    },
    {
        "id": "harassment_threat",
        "severity": "critical",
        "escalate": True,
        "department": "Compliance & Legal",
        "priority": "P1",
        "title": "Harassment, threats or blackmail",
        "keywords": [
            "dhamki", "dhamkiya", "threat", "harass", "blackmail", "blackmailing",
            "batameezi", "pareshan kar raha", "pareshan kar rahi", "stalking", "ghalat call kar",
            "gaali", "abuse kar raha", "threatening",
        ],
        "answer": (
            "Aapki safety humare liye sabse zyada important hai. Please yeh steps le lein:\n\n"
            "1. Calls/messages ke screenshots ya call log save kar lein — evidence ke liye zaroori hai.\n"
            "2. Us number ko apni phone settings se block kar dein.\n"
            "3. Agar khatra mehsoos ho to nearest police station ya FIA Cyber Crime (1991) ko inform karein.\n\n"
            "Maine yeh case Compliance & Legal team ko turant forward kar diya hai."
        ),
        "clarification_questions": [
            "Jis number se aapko pareshan kiya ja raha hai wo kya hai?",
            "Yeh kab se ho raha hai aur kitni dafa hua?",
            "Kya aapke paas screenshot/recording hai?",
        ],
        "escalation_reason": (
            "Harassment/blackmail mein formal action aur law-enforcement referral sirf Compliance & Legal team le sakti hai."
        ),
    },
    # ── SIM issues ─────────────────────────────────────────────────────────
    {
        "id": "sim_blocked",
        "severity": "urgent",
        "escalate": False,
        "department": "Product Support",
        "priority": "P2",
        "title": "SIM blocked or deactivated",
        "keywords": [
            "sim block", "sim blocked", "sim band ho", "sim deactivate", "sim deactivated",
            "number block", "account suspended", "service suspended", "sim suspend",
            "mera number band", "number band ho gaya",
        ],
        "answer": (
            "SIM block/deactivate hone ke kai reasons ho sakte hain (security, unpaid dues, verification, ya temporary network hold).\n\n"
            "1. Pehle check karein: phone par 'No Service', 'Emergency calls only', ya koi message show ho raha hai?\n"
            "2. Agar aapne khud block request nahi ki, to yeh security hold ho sakta hai — identity verify karni padegi.\n"
            "3. CNIC le kar nearest PakSim franchise se unblock/reactivate karwa sakte hain (biometric verification).\n\n"
            "Agar foran unblock ki zarurat ho, authorized support/franchise se verification karwani hogi; chat se main SIM ko khud unblock nahi kar sakta."
        ),
        "clarification_questions": [
            "Phone par exact message kya dikh raha hai?",
            "Kya aapne khud SIM block karwai thi?",
            "Aapka registered CNIC number confirm kar sakte hain?",
        ],
    },
    {
        "id": "sim_not_detected",
        "severity": "normal",
        "escalate": False,
        "department": "Product Support",
        "priority": "P3",
        "title": "SIM not detected by phone",
        "keywords": [
            "sim not detected", "sim detect nahi", "no sim", "insert sim", "sim card error",
            "sim invalid", "invalid sim", "sim nahi mil rahi", "phone sim nahi pehchan",
        ],
        "answer": (
            "SIM detect na hone ka masla aksar phone/SIM contact se related hota hai:\n\n"
            "1. Phone power off karein, SIM nikaalein, contacts saaf karein, dobara lagayein.\n"
            "2. SIM tray sahi direction mein hai ya nahi check karein.\n"
            "3. Kisi doosre compatible phone mein yeh SIM try karein.\n"
            "4. Agar doosre phone mein bhi detect na ho to SIM physical damage ho sakti hai — replacement chahiye hogi.\n\n"
            "Batayein in steps ke baad kya hua."
        ),
        "clarification_questions": [
            "Kya doosre phone mein yeh SIM detect hoti hai?",
            "SIM par koi scratch ya damage dikhai de raha hai?",
        ],
    },
    {
        "id": "sim_not_working",
        "severity": "normal",
        "escalate": False,
        "department": "Product Support",
        "priority": "P3",
        "title": "SIM not working / no network signal",
        "keywords": [
            "sim kaam nahi", "sim kam nahi", "sim band", "sim dead", "sim ban gai", "sim ban gayi",
            "network nahi aa raha", "signal nahi", "no service", "no signal", "sim not working",
            "signal gayab", "sim response nahi de rahi", "signal", "signals", "network",
            "sim nahi chal rahi", "sim nahi chalrahi", "mera sim", "meri sim",
        ],
        "answer": (
            "Main aapki SIM ka masla check karta hoon. Pehle yeh quick steps try kar lein:\n\n"
            "1. Phone ko restart karein.\n"
            "2. SIM ko nikaal kar dobara sahi tarah lagayein (edges check karein ke scratch/damage na ho).\n"
            "3. Settings mein Network mode ko Auto select karein.\n"
            "4. Kisi doosre phone mein yeh SIM laga kar dekhein — agar wahan bhi signal nahi to masla SIM/network side ka hai.\n\n"
            "Agar in steps ke baad bhi signal na aaye, support request ke liye apna area, issue ka start time aur SIM status ready rakhein."
        ),
        "clarification_questions": [
            "Phone par 'No Service', 'SIM not detected', ya koi aur message dikh raha hai?",
            "Yeh masla kab se ho raha hai?",
            "Kya doosre phone mein yeh SIM chal rahi hai?",
            "Aap kis city/area mein hain?",
        ],
    },
    {
        "id": "new_sim_purchase",
        "severity": "normal",
        "escalate": False,
        "department": "Sales & SIM Services",
        "priority": "P3",
        "title": "New SIM purchase / delivery",
        "keywords": [
            "new sim", "new sim chahiye", "nayi sim", "naya sim", "new number",
            "sim khareed", "sim purchase", "buy sim", "buy a sim", "sim order",
            "sim ghar par", "sim deliver", "home delivery", "new connection",
        ],
        "answer": (
            "New SIM ke liye SIM ko sirf button click se activate nahi kiya jata. Pehle registration/order details complete hoti hain.\n\n"
            "1. Full name aur required CNIC details dein.\n"
            "2. Contact number, SIM type (Prepaid/Postpaid) aur 4G/5G option select karein.\n"
            "3. Delivery ke liye complete address, city aur area/postal details dein.\n"
            "4. Available offer select karein. Offer valid ho to price Rs. 0 ho sakta hai; warna checkout par applicable SIM price show hoga.\n"
            "5. Agar payment required ho to payment method select karke order confirm karein.\n\n"
            "Order create hone ke baad delivery/status track ki ja sakti hai. CNIC/biometric verification jahan required ho, woh official verification process ka hissa hota hai."
        ),
        "clarification_questions": [
            "Aap Prepaid SIM chahte hain ya Postpaid?",
            "Aapki delivery city aur area kya hai?",
            "Kya aap koi available offer use karna chahte hain?",
        ],
    },
    {
        "id": "sim_activation",
        "severity": "normal",
        "escalate": False,
        "department": "SIM Services",
        "priority": "P3",
        "title": "SIM activation",
        "keywords": [
            "sim activation", "activate sim", "sim activate", "sim activate karni",
            "sim chalu karni", "sim chaloo karni", "activation nahi hui", "sim active nahi",
        ],
        "answer": (
            "SIM activation ke liye pehle verify karein ke SIM registration/ownership process complete hai.\n\n"
            "1. SIM phone mein insert karke phone restart karein.\n"
            "2. Agar network nahi aa raha to 'No Service' / 'SIM not detected' message check karein.\n"
            "3. Agar nayi SIM hai aur activation complete nahi hui, official SIM verification/support process follow karna hoga.\n\n"
            "CNIC ya biometric verification jahan required ho, woh authorized verification point par hoti hai. OTP, PIN ya password chat mein share na karein."
        ),
        "clarification_questions": [
            "SIM nayi purchase ki hai ya existing SIM hai?",
            "Phone par exact message kya dikh raha hai?",
        ],
    },
    {
        "id": "sim_replacement_port",
        "severity": "normal",
        "escalate": False,
        "department": "Product Support",
        "priority": "P3",
        "title": "SIM replacement / number port / eSIM",
        "keywords": [
            "sim replace", "sim replacement", "sim change karni", "sim change karwani",
            "duplicate sim", "replacement sim", "nano sim", "esim",
            "number port", "port out", "mnp", "sim upgrade",
        ],
        "answer": (
            "Agar aap existing number ki replacement/upgrade SIM chahte hain, to nayi SIM aapke existing number ke liye issue hoti hai; number change nahi hota.\n\n"
            "1. Original CNIC aur required biometric verification complete hoti hai.\n"
            "2. Replacement ke baad naya SIM/ICCID issue ho sakta hai, lekin existing mobile number retain hota hai.\n"
            "3. Agar aap number ko kisi doosre operator par le jana chahte hain, woh MNP process hai aur separate verification hoti hai.\n\n"
            "Aap bata dein: replacement SIM, eSIM/upgrade, ya number port mein se kya chahiye?"
        ),
        "clarification_questions": [
            "Aapko SIM replace, duplicate, ya number port chahiye?",
            "Aap kis city mein hain?",
        ],
    },
    # ── Network / calls / SMS / data ───────────────────────────────────────
    {
        "id": "no_internet_data",
        "severity": "normal",
        "escalate": False,
        "department": "Product Support",
        "priority": "P3",
        "title": "Mobile internet / data not working",
        "keywords": [
            "internet nahi chal raha", "internet nahi chalraha", "data nahi chal raha", "net band",
            "4g nahi", "5g nahi", "3g nahi", "data slow", "internet slow", "net nahi chal raha",
            "mobile data band", "data not working", "internet not working", "no data",
        ],
        "answer": (
            "Internet ka masla aksar in steps se theek ho jata hai:\n\n"
            "1. Settings > Mobile Network mein APN check/reset karein.\n"
            "2. Mobile Data on/off karein, ya Airplane mode 10 second on-off karein.\n"
            "3. Active internet package/balance check karein — package khatam hone par speed slow ho jati hai.\n"
            "4. Network mode ko 4G/LTE (ya 5G agar support ho) par set karein.\n\n"
            "Agar in steps ke baad bhi net na chale, support request ke liye apna area, issue ka start time aur active package status ready rakhein."
        ),
        "clarification_questions": [
            "Kya aapka koi active internet package hai?",
            "Yeh masla sirf ek app mein hai ya poore phone mein?",
            "Aap kis area mein hain?",
        ],
    },
    {
        "id": "call_quality",
        "severity": "normal",
        "escalate": False,
        "department": "Product Support",
        "priority": "P3",
        "title": "Calls not working / poor call quality",
        "keywords": [
            "call drop", "call cut ho", "awaz nahi aa rahi", "call kat jati", "voice break",
            "call clear nahi", "aawaz cut", "call disconnect", "calls not working",
            "outgoing call", "incoming call", "call nahi ja rahi", "call nahi aa rahi",
            "call fail", "unable to call",
        ],
        "answer": (
            "Call issues ke liye yeh try karein:\n\n"
            "1. Signal bars check karein — weak signal par calls drop ho sakti hain.\n"
            "2. Open area ya window ke paas se call try karein.\n"
            "3. Wi-Fi Calling on karein agar phone support karta hai.\n"
            "4. Network mode 4G/LTE par set karein.\n"
            "5. Agar sirf incoming ya sirf outgoing fail ho rahi hain, wo alag network/routing issue ho sakta hai.\n\n"
            "Agar masla continue rahe to support request mein area, start time aur affected number/SIM details deni hongi."
        ),
        "clarification_questions": [
            "Sirf incoming, sirf outgoing, ya dono fail ho rahe hain?",
            "Yeh sirf ek jagah par hota hai ya har jagah?",
            "Aap kis area mein hain?",
        ],
    },
    {
        "id": "sms_issue",
        "severity": "normal",
        "escalate": False,
        "department": "Product Support",
        "priority": "P3",
        "title": "SMS not sending or receiving",
        "keywords": [
            "sms nahi", "message nahi ja", "sms fail", "otp nahi aa", "otp nahi mil",
            "sms not working", "text message", "message nahi aa raha", "sms not received",
        ],
        "answer": (
            "SMS/OTP issues ke liye:\n\n"
            "1. Signal check karein aur phone restart karein.\n"
            "2. Message centre number correct hai ya nahi (carrier settings).\n"
            "3. Storage full to nahi — purane SMS delete karein.\n"
            "4. Agar sirf OTP nahi aa rahe, spam/blocked numbers filter check karein.\n"
            "5. Doosre number par test SMS bhej kar dekhein.\n\n"
            "Agar phir bhi na chale to support complaint create ki ja sakti hai."
        ),
        "clarification_questions": [
            "Sirf OTP nahi aa rahe ya har SMS?",
            "Sending fail ho raha hai, receiving, ya dono?",
        ],
    },
    # ── Account / package / billing ────────────────────────────────────────
    {
        "id": "balance_check",
        "severity": "normal",
        "escalate": False,
        "department": "Billing & Account",
        "priority": "P3",
        "title": "Balance check",
        "keywords": [
            "balance check", "balance kaise check", "mera balance kitna", "balance kitna hai",
            "remaining balance", "current balance", "balance dekhna", "balance batao",
        ],
        "answer": (
            "Aap apna current balance official PakSim app/account ke balance section mein check kar sakte hain.\n\n"
            "Agar balance expected amount se kam dikh raha hai, recharge/deduction ka issue alag se check karna hoga.\n"
            "Agar aap bata dein ke balance check karna hai ya recharge ke baad balance missing hai, main sahi steps bata dunga."
        ),
        "clarification_questions": [],
    },
    {
        "id": "package_purchase",
        "severity": "normal",
        "escalate": False,
        "department": "Packages & Billing",
        "priority": "P3",
        "title": "Package purchase / activation",
        "keywords": [
            "package lena", "package chahiye", "package buy", "package purchase",
            "package subscribe", "package karna hai", "package lagwana", "bundle lena",
            "package activate karna", "package on karna", "offer lena",
        ],
        "answer": (
            "Package lene ke liye flow simple hai:\n\n"
            "1. Available packages mein se package select karein.\n"
            "2. Apna SIM/number select karein.\n"
            "3. Package details, validity aur price/offer review karein.\n"
            "4. Available payment method select karein.\n"
            "5. Payment confirm hone ke baad package activation ka status show hoga.\n\n"
            "Exact price aur offer checkout par jo current amount show ho, wahi applicable hoga."
        ),
        "clarification_questions": [
            "Aap data, call, SMS ya mixed package chahte hain?",
        ],
    },
    {
        "id": "balance_recharge_issue",
        "severity": "normal",
        "escalate": False,
        "department": "Billing & Refunds",
        "priority": "P3",
        "title": "Recharge done but balance not received",
        "keywords": [
            "recharge", "balance", "top up", "top-up", "credit balance", "easyload",
            "recharge nahi hua", "balance nahi aya", "balance nahi aaya", "load nahi hua",
            "balance show nahi", "balance nahi dikh",
        ],
        "answer": (
            "Agar recharge successful ho gaya hai lekin balance abhi show nahi ho raha, pehle recharge/payment ka status check karein. "
            "Agar payment successful hai aur balance phir bhi update nahi hua, main isay Billing team ko verify karne ke liye complaint mein bhej sakta hoon.\n\n"
            "Mujhe sirf yeh 3 cheezein batayein: recharge amount, recharge ki date/time, aur transaction/reference ID. "
            "OTP, password ya full card/bank details share na karein."
        ),
        "clarification_questions": [
            "Recharge amount kitna tha?",
            "Recharge kis date/time par kiya tha?",
            "Transaction/reference ID kya hai?",
            "Payment method kya tha (app, bank, wallet)?",
        ],
        "simplified_answer": (
            "Simple baat: aapne recharge kiya hai lekin balance update nahi hua. "
            "Agar payment successful hai, mujhe sirf recharge amount, date/time aur transaction/reference ID bhej dein. "
            "Main us basis par Billing team ko verification ke liye complaint route karunga. "
            "OTP, password ya full card/bank details mat bhejein."
        ),
    },
    {
        "id": "package_issue",
        "severity": "normal",
        "escalate": False,
        "department": "Billing & Refunds",
        "priority": "P3",
        "title": "Package not activated / wrong deduction",
        "keywords": [
            "bundle", "package activate nahi", "package nahi", "package expire",
            "activate nahi hua", "wrong package", "ghalat package", "package deduct", "package kat",
            "data package", "call package", "sms package",
        ],
        "answer": (
            "Package activate na hone ya ghalat deduction ke liye:\n\n"
            "1. App/account mein active package aur remaining balance check karein.\n"
            "2. Agar payment ho chuki hai lekin package active nahi hua, transaction/reference ID sambhal kar rakhein.\n"
            "3. Agar ghalat amount kata hai, support ko amount, date/time aur reference ID ke sath report karein.\n\n"
            "Main chat mein payment ko khud reverse ya package ko manually activate nahi kar sakta; zarurat par support request route ki ja sakti hai."
        ),
        "clarification_questions": [
            "Kaun sa package activate karna tha?",
            "Amount kitna kata aur kab?",
            "Transaction/reference ID available hai?",
        ],
    },
    {
        "id": "account_login",
        "severity": "normal",
        "escalate": False,
        "department": "Account Security",
        "priority": "P2",
        "title": "Account login / password issue",
        "keywords": [
            "password bhool", "login nahi ho raha", "account block", "account lock",
            "sign in nahi ho raha", "otp nahi aa raha login", "app login issue",
            "forgot password", "cannot login",
        ],
        "answer": (
            "Login/account access ke liye:\n\n"
            "1. 'Forgot Password' use karein aur registered number par aane wala OTP app mein enter karein.\n"
            "2. Agar OTP nahi aa raha, signal aur registered number check karein.\n"
            "3. Agar account 'blocked' dikhe to security hold ho sakta hai — identity verify karni padegi.\n\n"
            "OTP, password ya PIN kabhi kisi se share na karein — sirf app verification screen par enter karein."
        ),
        "clarification_questions": [
            "Login par exact error kya show ho raha hai?",
            "Kya aapko OTP mil raha hai?",
            "App se try kar rahe hain ya website se?",
        ],
    },
    {
        "id": "verification_identity",
        "severity": "normal",
        "escalate": False,
        "department": "Account Security",
        "priority": "P2",
        "title": "Identity / SIM ownership verification",
        "keywords": [
            "cnic", "verification", "biometric", "identity", "ownership", "sim verify",
            "documents", "registration fail", "nadra", "verify nahi",
        ],
        "answer": (
            "SIM ownership / identity verification ke liye official process franchise par biometric + original CNIC se hota hai. "
            "Main government requirements invent nahi karta — approved knowledge base / agent confirm karega.\n\n"
            "Generally aapko original CNIC aur registered number chahiye hota hai. "
            "Agar verification fail ho rahi hai, details dein taake case agent ko ja sake."
        ),
        "clarification_questions": [
            "Verification kahan fail ho rahi hai (app, franchise, SMS)?",
            "Exact error message kya hai?",
        ],
    },
    # ── Status / ticket check ──────────────────────────────────────────────
    {
        "id": "check_complaint_status",
        "severity": "normal",
        "escalate": False,
        "department": "",
        "priority": "",
        "title": "",
        "keywords": [
            "complaint status", "ticket status", "mera complaint", "meri complaint",
            "status check", "track complaint", "complaint kahan", "ticket number",
            "cmp-", "complaint no", "my ticket",
        ],
        "answer": (
            "Complaint status check karne ke liye apna complaint code bhejein (jaise CMP-00012), "
            "ya app mein My Complaints / Track Complaint page khol lein. "
            "Main aapke account ki open complaints bhi dekh sakta hoon agar aap logged in hain."
        ),
        "clarification_questions": [
            "Aapka complaint code kya hai (CMP-xxxxx)?",
        ],
    },
    {
        "id": "create_ticket_request",
        "severity": "normal",
        "escalate": True,
        "department": "Customer Support",
        "priority": "P3",
        "title": "Customer requested support ticket",
        "keywords": [
            "complaint register", "ticket banao", "ticket create", "agent se baat",
            "human agent", "representative", "complaint file", "register karo",
            "complaint darj", "escalate karo",
        ],
        "answer": (
            "Bilkul — main aapke liye support ticket / complaint register kar raha hoon taake human agent follow-up kare. "
            "Please issue ki short detail confirm kar dein agar pehle se clear nahi hai."
        ),
        "clarification_questions": [
            "Issue ek line mein summarize kar dein?",
            "Mobile number confirm karein?",
        ],
        "escalation_reason": "Customer ne explicitly ticket/agent request ki hai.",
    },
    {
        "id": "greeting",
        "severity": "normal",
        "escalate": False,
        "department": "",
        "priority": "",
        "title": "",
        "keywords": [
            "assalam", "asalam", "salam", "hello", "hi ", "hey", "shukriya", "thank you", "thanks",
            "good morning", "good evening",
        ],
        "answer": (
            "Wa alaikum assalam! Main Nova hoon — PakSim ki AI customer support assistant. "
            "Aap SIM, network, calls, internet, package, recharge, ya security se related masla bata dein; "
            "main troubleshooting, policy guidance, aur zarurat par ticket create karne mein madad karta hoon."
        ),
        "clarification_questions": [],
    },
]

_DEFAULT = {
    "id": "general_inquiry",
    "severity": "normal",
    "escalate": False,
    "department": "Customer Support",
    "priority": "P3",
    "title": "General customer support inquiry",
    "answer": (
        "Main aapki help kar sakta hoon. Behtar guidance ke liye issue thora detail mein batayein — "
        "jaise kya problem aa rahi hai, kab se, aur agar payment/recharge related hai to amount "
        "aur transaction/reference ID. OTP, password ya full card details share na karein."
    ),
    "clarification_questions": [
        "Problem exactly kya aa rahi hai?",
        "Yeh issue kab se ho raha hai?",
        "Agar payment hui hai to amount aur reference ID kya hai?",
    ],
    "escalation_reason": "",
}

_SHORTHAND = {
    r"\bnhi\b": "nahi",
    r"\bnai\b": "nahi",
    r"\bkr\b": "kar",
    r"\bkro\b": "karo",
    r"\bhra\b": "ho raha",
    r"\bhy\b": "hai",
    r"\bha\b": "hai",
}


def _normalize(text: str) -> str:
    for pattern, replacement in _SHORTHAND.items():
        text = re.sub(pattern, replacement, text)
    return text


def _keyword_matches(keyword: str, text: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(keyword.strip()) + r"(?![a-z0-9])"
    return re.search(pattern, text) is not None


def classify(question: Optional[str], previous_category: Optional[str] = None) -> dict:
    """Return best-matching category. Optional previous_category helps short replies
    like 'No' / 'Haan' stay in the same troubleshooting thread.
    """
    text = _normalize((question or "").lower().strip())
    # Short confirmations and comprehension requests must stay on the previous topic.
    # Customers commonly say "samajh nahi aaya", "phir se batao", or "clear nahi hua"
    # after Nova asks for details. Treat these as a continuation instead of falling back
    # to the generic support message.
    if previous_category:
        clarification_phrases = (
            "samajh nahi aaya", "samajh nahin aaya", "samajh nhi aya",
            "samajh nahi aya", "clear nahi", "clear nahin", "phir se batao",
            "dobara batao", "simple batao", "asan alfaaz", "asaan alfaaz",
            "kya karun", "ab kya karun", "what do i do", "i dont understand",
            "i don't understand", "still confused", "not clear", "explain again",
        )
        short = text in {
            "no", "nahi", "nhi", "haan", "han", "yes", "ji", "ok", "theek", "done",
            "ho gaya", "nahi hua", "still", "abhi bhi", "same", "wahi",
        } or text.startswith(("no ", "nahi ", "haan ", "yes "))
        is_clarification = any(phrase in text for phrase in clarification_phrases)
        if short or is_clarification:
            for category in CATEGORIES:
                if category["id"] == previous_category:
                    out = dict(category)
                    out.setdefault("escalation_reason", "")
                    out.pop("keywords", None)
                    out["follow_up"] = True
                    out["simplify"] = is_clarification
                    if is_clarification and out.get("simplified_answer"):
                        out["answer"] = out["simplified_answer"]
                    out.pop("simplified_answer", None)
                    return out

    # Score every category instead of taking the first keyword hit, so a message
    # like "internet nahi chal raha, sim theek hai" goes to internet, not SIM.
    best, best_score = None, 0.0
    for category in CATEGORIES:
        hits = [kw for kw in category["keywords"] if _keyword_matches(kw, text)]
        if not hits:
            continue
        score = sum(len(kw.split()) + len(kw) / 20 for kw in hits)
        if category["severity"] == "critical":
            score += 1.5  # safety issues win ties
        if score > best_score:
            best, best_score = category, score
    if best is not None:
        out = dict(best)
        out.setdefault("escalation_reason", "")
        out.pop("keywords", None)
        out["confidence"] = round(min(1.0, best_score / 4), 2)
        return out
    return dict(_DEFAULT)
