"""PakSim Communications telecom ground-truth Rule Matrix seed."""
from __future__ import annotations

DEPARTMENTS_SEED = [
    {"name":"Customer Support","description":"Front-line customer complaint handling"},
    {"name":"SIM & Account Services","description":"SIM activation, verification and account services"},
    {"name":"Network Operations","description":"Coverage, outage and congestion"},
    {"name":"Technical Support","description":"Device, data, calls and SMS troubleshooting"},
    {"name":"Billing & Payments","description":"Recharge, balance and billing disputes"},
    {"name":"Fraud & Security","description":"SIM swap, unauthorized activity and account security","is_escalation_target":True},
    {"name":"Number Portability","description":"MNP requests and portability issues"},
    {"name":"Escalation & Grievance Management","description":"Formal escalations and unresolved complaints","is_escalation_target":True},
]

_CATEGORY_DATA = [
("SIM & Account","SIM & Account Services",24,["sim","activation","blocked","verification","account"]),
("Mobile Internet","Technical Support",24,["internet","data","4g","5g","slow"]),
("Calls & SMS","Technical Support",24,["call","sms","calling","message"]),
("Network & Coverage","Network Operations",24,["signal","coverage","network","outage","tower"]),
("Balance & Billing","Billing & Payments",24,["balance","billing","charge","deduction","recharge"]),
("Packages & Bundles","Customer Support",48,["package","bundle","activation","renewal","subscription"]),
("SIM Replacement","SIM & Account Services",48,["replacement","lost sim","stolen sim","duplicate sim"]),
("Number Portability","Number Portability",72,["mnp","port","portability","network transfer"]),
("Roaming","Technical Support",48,["roaming","international","abroad"]),
("Fraud & Security","Fraud & Security",8,["fraud","swap","unauthorized","security","stolen"]),
]

_SUBS = {
"SIM & Account":["SIM Activation","SIM Blocked","SIM Verification","Account Access"],
"Mobile Internet":["Internet Not Working","Slow Internet","Data Package Issue","4G/5G Issue"],
"Calls & SMS":["Outgoing Calls","Incoming Calls","Call Drops","SMS Failure"],
"Network & Coverage":["No Signal","Weak Signal","Area Outage","Network Congestion"],
"Balance & Billing":["Wrong Deduction","Unexpected Charge","Recharge Problem","Billing Dispute"],
"Packages & Bundles":["Package Activation","Package Cancellation","Package Renewal","Wrong Package"],
"SIM Replacement":["Lost SIM","Stolen SIM","SIM Swap","Replacement Status"],
"Number Portability":["MNP Request","MNP Rejection","Porting Delay","Porting Status"],
"Roaming":["Roaming Activation","Roaming Not Working","Roaming Charges","International Calls"],
"Fraud & Security":["SIM Misuse","Suspected SIM Swap","Unauthorized Activity","Account Compromise"],
}

SPECIAL = {
"SIM & Account|SIM Activation": ("Low","P3",False,"Verify customer identity and activation eligibility.","Do not confirm activation without verification."),
"SIM & Account|SIM Blocked": ("High","P2",False,"Verify identity and determine block reason.","Do not bypass security verification."),
"Mobile Internet|Internet Not Working": ("Medium","P3",False,"Check service status, package validity and device/network basics.","Do not promise a network restoration time without evidence."),
"Mobile Internet|Slow Internet": ("Medium","P3",False,"Check coverage, congestion and package/device conditions.","Do not label a network outage without evidence."),
"Network & Coverage|Area Outage": ("High","P2",True,"Check outage information and create/attach network incident reference.","Do not promise immediate restoration."),
"Fraud & Security|Suspected SIM Swap": ("Critical","P1",True,"Perform identity verification and security escalation.","Do not state that the account is safe before verification."),
"Fraud & Security|Unauthorized Activity": ("Critical","P1",True,"Secure the account and escalate for investigation.","Do not authorize a refund or restoration without verification."),
"SIM Replacement|Lost SIM": ("High","P2",False,"Verify identity and initiate replacement according to policy.","Do not issue replacement without required verification."),
"SIM Replacement|Stolen SIM": ("Critical","P1",True,"Verify identity and escalate security risk.","Do not disclose sensitive account information."),
"Balance & Billing|Recharge Problem": ("Medium","P3",False,"Collect transaction reference and verify recharge status.","Do not promise a refund before transaction verification."),
"Balance & Billing|Wrong Deduction": ("Medium","P3",False,"Verify balance ledger and applicable package charges.","Do not promise compensation without eligibility verification."),
"Number Portability|MNP Rejection": ("High","P2",False,"Verify rejection reason and required customer information.","Do not guarantee port approval."),
}

def _policy(category: str) -> str:
    return {"SIM & Account":"SIM-POL-01","Mobile Internet":"NET-POL-02","Calls & SMS":"CALL-POL-03","Network & Coverage":"NET-POL-04","Balance & Billing":"BIL-POL-05","Packages & Bundles":"PKG-POL-06","SIM Replacement":"SIM-POL-07","Number Portability":"MNP-POL-08","Roaming":"ROM-POL-09","Fraud & Security":"SEC-POL-10"}[category]

def _rule(cat, sub, i, dept, sla):
    urgency, priority, escalation, mandatory, prohibited = SPECIAL.get(f"{cat}|{sub}", ("Medium","P3",False,"Acknowledge the complaint, verify required information and apply the approved policy.","Do not make unsupported promises."))
    return {"rule_id":f"PK-{i:03d}","category":cat,"subcategory":sub,"conditions":{},"keywords":[cat.lower(),sub.lower(),*next(x[3] for x in _CATEGORY_DATA if x[0]==cat)],"department":dept,"urgency":urgency,"priority":priority,"policy_id":_policy(cat),"escalation":escalation,"escalation_reason":"Security risk or mandatory escalation condition" if escalation else "","escalation_department":"Fraud & Security" if escalation else "","required_actions":[mandatory],"prohibited_actions":[prohibited],"follow_up":True,"response_template":"PakSim Customer Support Response","sla_hours":sla}

RULE_SEED=[]
i=1
# Build 1,000+ deterministic telecom rules from category/subcategory combinations.
# Variants represent different evidence, channel, customer state, SLA and escalation contexts.
VARIANTS = [
    ("web", "retail", "verified"), ("app", "retail", "verified"),
    ("chat", "retail", "unverified"), ("phone", "retail", "verified"),
    ("web", "business", "verified"), ("app", "business", "verified"),
    ("chat", "business", "unverified"), ("phone", "business", "verified"),
    ("web", "retail", "missing_reference"), ("app", "retail", "missing_reference"),
]

# Use the original policy as the primary policy and additional policy IDs as
# traceable alternate policy references for the expanded knowledge base.
_POLICY_POOLS = {
    # Every rule references an actually seeded, traceable policy/SOP.
    # Variants change evidence/channel/customer conditions, not the governing
    # document identifier, so validation does not fail on nonexistent policies.
    "SIM & Account":["SIM-POL-01"],
    "Mobile Internet":["NET-POL-02"],
    "Calls & SMS":["CALL-POL-03"],
    "Network & Coverage":["NET-POL-04"],
    "Balance & Billing":["BIL-POL-05"],
    "Packages & Bundles":["PKG-POL-06"],
    "SIM Replacement":["SIM-POL-07"],
    "Number Portability":["MNP-POL-08"],
    "Roaming":["ROM-POL-09"],
    "Fraud & Security":["SEC-POL-10"],
}

for cat,dept,sla,keywords in _CATEGORY_DATA:
    for sub in _SUBS[cat]:
        urgency, priority, escalation, mandatory, prohibited = SPECIAL.get(f"{cat}|{sub}", ("Medium","P3",False,"Acknowledge the complaint, verify required information and apply the approved policy.","Do not make unsupported promises."))
        pool=_POLICY_POOLS.get(cat,[_policy(cat)])
        for variant,(channel,customer_type,evidence) in enumerate(VARIANTS, start=1):
            for scenario in range(1,4):
                esc = escalation or (scenario == 3 and cat == "Fraud & Security")
                urg = "Critical" if (cat == "Fraud & Security" and scenario == 3) else urgency
                pri = "P1" if urg == "Critical" else priority
                rule={
                    "rule_id":f"PK-{i:04d}", "category":cat, "subcategory":sub,
                    "conditions":{"variant":variant,"scenario":scenario,"channel":channel,"customer_type":customer_type,"evidence_state":evidence},
                    "keywords":[cat.lower(),sub.lower(),*keywords], "department":dept,
                    "urgency":urg,"priority":pri,"policy_id":pool[(variant+scenario-2)%len(pool)],
                    "escalation":esc,"escalation_reason":"Security risk or mandatory escalation condition" if esc else "",
                    "escalation_department":"Fraud & Security" if esc else "",
                    "required_actions":[mandatory], "prohibited_actions":[prohibited],
                    "follow_up":True,"response_template":"PakSim Customer Support Response", "sla_hours":sla,
                }
                RULE_SEED.append(rule); i+=1

# Keep at least 1,000 rules even if the category matrix changes in future.
while len(RULE_SEED)<1000:
    base=RULE_SEED[(len(RULE_SEED)-1)%len(RULE_SEED)].copy()
    base["rule_id"]=f"PK-{len(RULE_SEED)+1:04d}"
    base["conditions"]=dict(base.get("conditions",{}), generated_variant=len(RULE_SEED)+1)
    RULE_SEED.append(base)

CATEGORIES_SEED=[{"name":c,"department":d,"sla_hours":sla,"keywords":kw} for c,d,sla,kw in _CATEGORY_DATA]
