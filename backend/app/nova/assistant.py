"""PakSim Nova — telecom customer support assistant pipeline.

Microphone -> STT -> Language Detection -> Intent + RAG -> Trust Gate / Firewall
-> Response. Critical cases auto-file a real complaint ticket.

Never claims backend actions (block SIM, refund, etc.) unless confirmed.
Never invents policies. Never asks for OTP/password/PIN/card details.
"""
from __future__ import annotations

import re
import uuid
from collections import Counter
from typing import Optional

from sqlalchemy.orm import Session

from ..models import AppNotification, Complaint, ComplaintHistory, Role, SimCard, User
from ..models_nova import AssistantMessage, AssistantSession
from ..serializers import complaint_brief
from ..services.trust_engine import latest_assessment
from ..utils import extract_pk_mobile, mask_pk_mobile, normalize_pk_mobile, utcnow
from . import language, memory, pii
from .firewall import input_firewall, output_firewall

_OPEN_COMPLAINT = re.compile(r"\bopen\s+complaint\s+#?(\w[\w-]*)\b", re.I)
_EXPLAIN_ESCALATED = re.compile(r"\bwhy\s+(was\s+)?complaint\s+#?(\w[\w-]*)\s+(was\s+)?escalated\b", re.I)
_SLA_RISK = re.compile(r"\b(sla\s+breach|at\s+risk|complaints?\s+at\s+risk)\b", re.I)
_HIGH_RISK_TODAY = re.compile(r"\bhigh[- ]risk\s+complaints?\s+today\b", re.I)
_TOP_DEPARTMENT = re.compile(r"\b(which|what)\s+department\b.*\bunresolved\b", re.I)
_CMP_CODE = re.compile(r"\b(CMP-?\d{3,})\b", re.I)


def get_or_create_session(db: Session, user: User, session_uuid: Optional[str]) -> AssistantSession:
    if session_uuid:
        row = db.query(AssistantSession).filter(
            AssistantSession.uuid == session_uuid, AssistantSession.user_id == user.id
        ).first()
        if row is not None:
            return row
    row = AssistantSession(uuid=session_uuid or str(uuid.uuid4()), user_id=user.id)
    db.add(row)
    db.flush()
    return row


def _find_complaint(db: Session, ref: str, user: User) -> Optional[Complaint]:
    ref = ref.strip().upper().replace("CMP", "CMP").replace("CMP-", "CMP-")
    if not ref.startswith("CMP-") and ref.isdigit():
        ref = f"CMP-{int(ref):05d}"
    elif ref.startswith("CMP") and not ref.startswith("CMP-"):
        ref = "CMP-" + ref[3:]
    q = db.query(Complaint)
    complaint = q.filter(Complaint.code == ref).first()
    if complaint is None and ref.replace("CMP-", "").isdigit():
        complaint = q.filter(Complaint.id == int(ref.replace("CMP-", ""))).first()
    if complaint is None:
        return None
    if not (user.role and user.role.name in {"admin", "agent"}) and complaint.customer_id != user.id:
        return None
    return complaint


def _staff_command(db: Session, text: str, user: User) -> Optional[dict]:
    if not (user.role and user.role.name in {"admin", "agent"}):
        return None
    if _TOP_DEPARTMENT.search(text):
        rows = db.query(Complaint.department).filter(
            Complaint.status.notin_(["RESOLVED", "CLOSED", "REJECTED"])
        ).all()
        counts = Counter(r[0] for r in rows if r[0])
        if not counts:
            return {"answer": "No unresolved complaints with a department assigned right now.", "data": {}}
        dept, n = counts.most_common(1)[0]
        return {
            "answer": f"The {dept} department currently has the highest number of unresolved complaints ({n}).",
            "data": {"department": dept, "count": n},
        }
    if _HIGH_RISK_TODAY.search(text):
        rows = (
            db.query(Complaint)
            .filter(Complaint.priority.in_(["P1", "P2"]), Complaint.status.notin_(["RESOLVED", "CLOSED", "REJECTED"]))
            .limit(10)
            .all()
        )
        return {
            "answer": f"There are {len(rows)} high-risk (P1/P2) open complaints right now.",
            "data": {"complaints": [complaint_brief(c) for c in rows]},
        }
    if _SLA_RISK.search(text):
        from .sla import sla_status

        rows = db.query(Complaint).filter(Complaint.status.notin_(["RESOLVED", "CLOSED", "REJECTED"])).limit(300).all()
        at_risk = [c for c in rows if sla_status(c)["status"] in {"AT_RISK", "BREACHED"}]
        return {
            "answer": f"{len(at_risk)} complaint(s) are at risk of or past SLA breach.",
            "data": {"complaints": [complaint_brief(c) for c in at_risk[:15]]},
        }
    match = _EXPLAIN_ESCALATED.search(text)
    if match:
        complaint = _find_complaint(db, match.group(2), user)
        if complaint is None:
            return {"answer": "I couldn't find that complaint.", "data": {}}
        assessment = latest_assessment(db, complaint.id)
        reason = (assessment.explanation if assessment else None) or complaint.flags
        return {"answer": f"{complaint.code}: {reason}", "data": {"complaint": complaint_brief(complaint)}}
    match = _OPEN_COMPLAINT.search(text)
    if match:
        complaint = _find_complaint(db, match.group(1), user)
        if complaint is None:
            return {"answer": "I couldn't find that complaint or you don't have access to it.", "data": {}}
        return {
            "answer": f"Opening {complaint.code}: {complaint.title} (status {complaint.status}).",
            "data": {
                "complaint": complaint_brief(complaint),
                "action": "navigate",
                "target": f"/complaints/{complaint.id}",
            },
        }
    return None


def _session_context(db: Session, session: AssistantSession) -> dict:
    """Last assistant meta + recent user lines for multi-turn continuity."""
    msgs = (
        db.query(AssistantMessage)
        .filter(AssistantMessage.session_id == session.id)
        .order_by(AssistantMessage.id.desc())
        .limit(12)
        .all()
    )
    last_category = None
    last_clarifications: list = []
    transcript_bits: list[str] = []
    turns: list[dict] = []
    for m in reversed(msgs):
        if m.text:
            turns.append({"role": m.role, "text": m.text})
        if m.role == "assistant" and m.meta:
            last_category = m.meta.get("category") or last_category
            last_clarifications = m.meta.get("clarification_questions") or last_clarifications
        if m.role == "user" and m.text:
            transcript_bits.append(m.text[:300])
    return {
        "last_category": last_category,
        "clarification_questions": last_clarifications,
        "recent_user_texts": transcript_bits[-6:],
        "turns": turns,
    }


def _customer_status_reply(db: Session, text: str, user: User) -> Optional[dict]:
    """If user asks about a CMP code or their open tickets, answer from DB (no invention)."""
    match = _CMP_CODE.search(text)
    if match:
        complaint = _find_complaint(db, match.group(1), user)
        if complaint is None:
            return {
                "answer": (
                    f"Mujhe {match.group(1).upper()} is account par nahi mila. "
                    "Code dobara check karein ya My Complaints page kholein."
                ),
                "data": {},
            }
        status = complaint.status.replace("_", " ").title()
        bits = [
            f"Complaint **{complaint.code}**: {complaint.title}",
            f"Status: **{status}**",
            f"Priority: {complaint.priority or '—'} · Urgency: {complaint.urgency or '—'}",
        ]
        if complaint.assigned_agent_id:
            bits.append("Assigned: support agent")
        if complaint.resolution_text:
            bits.append(f"Resolution note: {complaint.resolution_text[:300]}")
        if complaint.rejection_reason:
            bits.append(f"Rejection reason: {complaint.rejection_reason[:300]}")
        bits.append("Live status hamesha My Complaints / Track page par bhi milti hai.")
        return {"answer": "\n".join(bits), "data": {"complaint": complaint_brief(complaint)}}

    low = text.lower()
    if any(k in low for k in ("my complaint", "meri complaint", "mere complaint", "open ticket", "my tickets")):
        rows = (
            db.query(Complaint)
            .filter(Complaint.customer_id == user.id)
            .order_by(Complaint.updated_at.desc())
            .limit(5)
            .all()
        )
        if not rows:
            return {
                "answer": "Aapke account par abhi koi complaint nahi mili. Naya masla batayein to main help karunga.",
                "data": {},
            }
        lines = ["Aapki recent complaints:"]
        for c in rows:
            lines.append(f"• **{c.code}** — {c.title[:60]} · {c.status}")
        lines.append("Kisi ek ka full status chahiye to CMP code bhejein.")
        return {"answer": "\n".join(lines), "data": {"complaints": [complaint_brief(c) for c in rows]}}
    return None


def _auto_file_complaint(
    db: Session,
    user: User,
    session: AssistantSession,
    original_text: str,
    result: dict,
    recent_texts: list[str],
    mobile_number: str = "",
) -> Optional[str]:
    """File a real central complaint for escalations / explicit ticket requests."""
    try:
        title = result.get("title") or "Support request via Nova chat"
        summary_parts = list(recent_texts[-4:]) + [original_text]
        description = (
            "AI conversation summary (Nova chat):\n"
            + "\n---\n".join(t.strip() for t in summary_parts if t and t.strip())
        )
        if mobile_number:
            description = f"Registered PakSim number: {mobile_number}\n" + description
        description = description[:4000]
        priority = result.get("priority") or "P3"
        urgency = "Critical" if priority == "P1" or result.get("severity") == "critical" else (
            "High" if priority == "P2" or result.get("severity") == "urgent" else "Medium"
        )
        # Route live customer cases to the least-loaded active agent. The demo
        # environment has one agent; production can have many without changing
        # the customer-facing flow. Dataset cases are never considered here.
        agents = (db.query(User)
                  .join(Role, User.role_id == Role.id)
                  .filter(Role.name == "agent", User.is_active.is_(True))
                  .all())
        load_map = {}
        for agent in agents:
            load_map[agent.id] = (db.query(Complaint)
                                  .filter(Complaint.assigned_agent_id == agent.id,
                                          Complaint.status.notin_(["RESOLVED", "CLOSED", "REJECTED"]),
                                          Complaint.is_dataset_case.is_(False))
                                  .count())
        selected_agent = min(agents, key=lambda a: (load_map.get(a.id, 0), a.id)) if agents else None

        complaint = Complaint(
            code="TMP",
            title=title[:255],
            description=description or original_text[:4000] or title,
            channel="assistant",
            product_or_service=(f"PakSim SIM {mobile_number}" if mobile_number else ""),
            complaint_date=utcnow(),
            customer_id=user.id,
            created_by=user.id,
            status="PENDING",  # AI could not solve it -> pending human agent action
            assigned_agent_id=selected_agent.id if selected_agent else None,
            source_session_uuid=session.uuid,
            department=result.get("department", "") or "Customer Support",
            priority=priority,
            urgency=urgency,
            issue_category=result.get("category", ""),
            flags=[result.get("escalation_reason", "")] if result.get("escalation_reason") else [],
        )
        db.add(complaint)
        db.flush()
        complaint.code = f"CMP-{complaint.id:05d}"
        db.add(
            ComplaintHistory(
                complaint_id=complaint.id,
                from_status="",
                to_status=complaint.status,
                note=(f"Auto-filed by Nova chat (session {session.uuid})"
                      f" — {result.get('escalation_reason', result.get('category', ''))}"
                      + (f" · Assigned to agent #{selected_agent.id}" if selected_agent else "")),
                actor_id=user.id,
            )
        )
        db.add(AppNotification(
            user_id=user.id, title=f"Complaint {complaint.code} registered",
            body=f"Your complaint for {mask_pk_mobile(mobile_number)} has been registered.",
            category="complaint", link=f"/complaints/{complaint.id}",
        ))
        db.commit()
        return complaint.code
    except Exception:
        db.rollback()
        return None


# ---------------------------------------------------------------------------
# Complaint intake: every customer complaint typed in Nova chat is registered
# ONLY after the customer's PakSim mobile number is verified against their account.
#   1. no SIM on the account            -> refuse (not a PakSim customer)
#   2. otherwise ask for the mobile no. -> remember the issue as `pending_complaint`
#   3. number unknown / not theirs      -> refuse, ask again (max 3 tries)
#   4. number belongs to the customer   -> complaint saved (shows in My Complaints)
# ---------------------------------------------------------------------------
_INFO_ONLY = {
    "greeting", "balance_check", "new_sim_purchase", "package_purchase", "check_complaint_status",
    "account_login", "verification_identity", "sim_activation", "sim_replacement_port", "general_inquiry",
}
_EXPLICIT_COMPLAINT = re.compile(
    r"(complaint|shikayat|shikayet|شکایت).*(register|darj|file|lodge|karni|karna|karo|karun|karein|dena|dalni|lagani)"
    r"|(register|darj|file|lodge|karni|karna).*(complaint|shikayat|shikayet)", re.I)
_STATUS_WORDS = re.compile(r"\b(status|track|progress|update|kahan|kab\s+tak|check)\b", re.I)
_CANCEL = re.compile(r"\b(cancel|nahi|nahin|nhi|no|rehne\s+do|rehny\s+do|chor\s+do|chhor\s+do|mat\s+karo|stop|skip)\b", re.I)
_MAX_NUMBER_TRIES = 3


def _is_staff_user(user: User) -> bool:
    return bool(user.role and user.role.name in {"admin", "agent", "manager", "reviewer"})


def _pending_complaint(db: Session, session: AssistantSession) -> Optional[dict]:
    row = (
        db.query(AssistantMessage)
        .filter(AssistantMessage.session_id == session.id, AssistantMessage.role == "assistant")
        .order_by(AssistantMessage.id.desc())
        .first()
    )
    pending = (row.meta or {}).get("pending_complaint") if row else None
    return pending if isinstance(pending, dict) else None


def _is_complaint_worthy(cls: dict, text: str) -> bool:
    cid = cls.get("id", "")
    if cid == "create_ticket_request":
        return True
    if cid in _INFO_ONLY:
        return bool(_EXPLICIT_COMPLAINT.search(text)) and not _STATUS_WORDS.search(text) and not _CMP_CODE.search(text)
    return True


def _pending_from(cls: dict, text: str, attempts: int = 0) -> dict:
    return {
        "category": cls.get("id", ""),
        "title": cls.get("title") or "Support request via Nova chat",
        "priority": cls.get("priority") or "P3",
        "severity": cls.get("severity", "normal"),
        "department": cls.get("department") or "Customer Support",
        "escalate": bool(cls.get("escalate")),
        "escalation_reason": cls.get("escalation_reason", ""),
        "issue_text": (text or "")[:1000],
        "attempts": attempts,
    }


def _intake_data(pending: dict, **extra) -> dict:
    data = {
        "category": pending.get("category", ""),
        "severity": pending.get("severity", "normal"),
        "escalate": False,
        "department": pending.get("department", ""),
        "priority": pending.get("priority", ""),
        "title": pending.get("title", ""),
        "clarification_questions": [],
        "needs_details": False,
        "citations": [],
    }
    data.update(extra)
    return data


def _ask_for_number(pending: dict, retry_note: str = "") -> dict:
    lead = retry_note or (
        f"Aapka masla note kar liya hai: **{pending.get('title', 'support request')}**.\n\n"
        "Is ki complaint register karne ke liye pehle apna **PakSim mobile number** bhejein "
        "(jaise 03XX XXXXXXX). Main check karunga ke woh number aapke account par registered hai ya nahi."
    )
    data = _intake_data(
        pending,
        awaiting_mobile=True,
        pending_complaint=pending,
        clarification_questions=["Complaint cancel karein"],
        needs_details=True,
    )
    return {"reply": lead, "data": data}


def _refuse_no_sim(pending: dict) -> dict:
    reply = (
        "Aapke account par koi **PakSim SIM registered nahi hai**, is liye main is masle ki complaint register nahi kar sakta. "
        "Complaints sirf PakSim SIM wale customers ke liye register hoti hain.\n\n"
        "Agar aap PakSim SIM lena chahte hain to **Services → Buy New SIM** se order karein, "
        "ya us account se login karein jis par aapki SIM registered hai."
    )
    return {"reply": reply, "data": _intake_data(pending, complaint_refused="no_sim")}


def _complaint_intake(db: Session, session: AssistantSession, user: User, raw_text: str,
                      working_text: str, ctx: dict) -> Optional[dict]:
    from . import intent_classifier

    pending = _pending_complaint(db, session)
    number = extract_pk_mobile(raw_text)

    if pending:
        if not number and _CANCEL.search(raw_text) and (len(raw_text.split()) <= 4 or "cancel" in raw_text.lower()):
            return {"reply": "Theek hai, complaint register nahi ki gayi. Koi aur madad chahiye to batayein.",
                    "data": _intake_data(pending)}
        if number:
            return _verify_and_file(db, session, user, pending, number)
        cls = intent_classifier.classify(working_text)
        short_reply = len(raw_text.split()) <= 4
        if int(pending.get("attempts", 0)) < _MAX_NUMBER_TRIES and (
            short_reply or _is_complaint_worthy(cls, raw_text) or cls.get("id") == "general_inquiry"
        ):
            pending = dict(pending, attempts=int(pending.get("attempts", 0)) + 1)
            return _ask_for_number(
                pending,
                "Mujhe valid mobile number nahi mila. Apna PakSim number **03XXXXXXXXX** (11 digits) format mein likhein, "
                "ya complaint cancel karne ke liye 'cancel' likh dein.",
            )
        return None  # customer moved on to another topic -> normal answer

    cls = intent_classifier.classify(working_text, previous_category=ctx.get("last_category"))
    if cls.get("follow_up") or not _is_complaint_worthy(cls, raw_text):
        return None

    pending = _pending_from(cls, raw_text)

    # Same problem already registered in this chat -> don't create a duplicate ticket.
    existing = (
        db.query(Complaint)
        .filter(Complaint.source_session_uuid == session.uuid, Complaint.customer_id == user.id,
                Complaint.issue_category == pending["category"],
                Complaint.status.notin_(["RESOLVED", "CLOSED", "REJECTED"]))
        .order_by(Complaint.id.desc()).first()
    )
    if existing is not None and pending["category"] != "create_ticket_request":
        return {
            "reply": (f"Is masle ki complaint **{existing.code}** pehle se registered hai aur hamari team us par kaam kar rahi hai. "
                      "Status **My Complaints** page par live dekh sakte hain. Koi naya masla ho to batayein."),
            "data": _intake_data(pending, complaint_code=existing.code),
        }

    if db.query(SimCard).filter(SimCard.customer_id == user.id).count() == 0:
        return _refuse_no_sim(pending)

    if number:  # customer already typed the number together with the problem
        return _verify_and_file(db, session, user, pending, number)
    return _ask_for_number(pending)


def _verify_and_file(db: Session, session: AssistantSession, user: User, pending: dict, number: str) -> dict:
    from . import intent_classifier

    variants = {number, "+92" + number[1:], "92" + number[1:], number[:4] + "-" + number[4:]}
    sim = db.query(SimCard).filter(SimCard.phone_number.in_(variants)).first()
    if sim is None:  # tolerate other stored formats on the customer's own SIMs
        sim = next((s for s in db.query(SimCard).filter(SimCard.customer_id == user.id).all()
                    if normalize_pk_mobile(s.phone_number) == number), None)
    masked = mask_pk_mobile(number)

    if sim is None or sim.customer_id != user.id:
        tries = int(pending.get("attempts", 0)) + 1
        if tries >= _MAX_NUMBER_TRIES:
            return {"reply": ("Number verify nahi ho saka, is liye complaint register nahi hui. "
                              "Jab aapke paas apne account ka sahi PakSim number ho to masla dobara batayein."),
                    "data": _intake_data(pending, complaint_refused="number_not_verified")}
        pending = dict(pending, attempts=tries)
        if sim is None:
            note = (f"Yeh number (**{masked}**) PakSim par **registered nahi hai**, is liye complaint register nahi ho saki. "
                    "Sahi PakSim number dobara bhejein, ya 'cancel' likh dein.")
        else:
            note = (f"Yeh number (**{masked}**) aapke account se linked nahi hai, is liye complaint register nahi ho sakti. "
                    "Apne account wala PakSim number bhejein, ya 'cancel' likh dein.")
        return _ask_for_number(pending, note)

    result = {
        "title": pending.get("title"), "priority": pending.get("priority"), "severity": pending.get("severity"),
        "department": pending.get("department"), "category": pending.get("category"),
        "escalation_reason": pending.get("escalation_reason", ""),
    }
    code = _auto_file_complaint(db, user, session, pending.get("issue_text", ""), result, [], mobile_number=number)
    if not code:
        return {"reply": "Complaint abhi save nahi ho saki. Thori der baad dobara koshish karein.",
                "data": _intake_data(pending, complaint_refused="save_failed")}

    cls = intent_classifier.classify(pending.get("issue_text", ""))
    advice = cls.get("answer", "") if cls.get("id") == pending.get("category") else ""
    lines = [
        f"✅ Aapki complaint register ho gayi hai — **Complaint {code}**",
        f"Number: {masked} · Priority: {pending.get('priority') or '—'}",
        "Aap ise **My Complaints** page par live track kar sakte hain.",
    ]
    if pending.get("escalate"):
        lines.append("Hamari team isay dashboard par dekh rahi hai. Main SIM block ya refund tabhi confirm karunga jab backend/agent confirm kare.")
    reply = "\n".join(lines)
    if advice:
        reply += "\n\nTab tak yeh steps try karein:\n\n" + advice
    data = _intake_data(
        pending, complaint_code=code, escalate=bool(pending.get("escalate")),
        escalation_reason=pending.get("escalation_reason", ""),
        clarification_questions=cls.get("clarification_questions", []) if advice else [],
        needs_details=bool(cls.get("clarification_questions")) if advice else False,
    )
    return {"reply": reply, "data": data}


def handle_message(db: Session, session: AssistantSession, text: str, user: User, modality: str = "text") -> dict:
    fw_in = input_firewall(text, source="user", channel="assistant")
    if not fw_in["allowed"]:
        reply = (
            "I can't act on that request — it looks like an attempt to override instructions or access "
            "unauthorised data. Agar complaint help chahiye to masla batayein ya CMP code bhejein."
        )
        _store(db, session, text, reply, "en", modality, {"blocked": True, "reason": fw_in["categories"]})
        return {"reply": reply, "blocked": True, "data": {}}

    detected = language.detect_language(text)
    translated = language.translate(text, detected["language"])
    working_text = translated["translation"] or text
    ctx = _session_context(db, session)

    command = _staff_command(db, working_text, user)
    intake = None
    if command is None and not _is_staff_user(user):
        intake = _complaint_intake(db, session, user, text, working_text, ctx)
    if command is not None:
        reply = command["answer"]
        data = command["data"]
    elif intake is not None:
        reply = intake["reply"]
        data = intake["data"]
    else:
        status_reply = _customer_status_reply(db, working_text, user)
        if status_reply is not None:
            reply = status_reply["answer"]
            data = status_reply.get("data") or {}
        else:
            from . import rag
            from . import intent_classifier

            # Multi-turn: pass previous category so short "No"/"Haan" stay on topic
            classification_hint = intent_classifier.classify(
                working_text, previous_category=ctx.get("last_category")
            )
            result = rag.customer_answer(
                db,
                working_text,
                top_k=5,
                original_question=text,
                language_label=detected.get("label", "English"),
                previous_category=ctx.get("last_category"),
                history=ctx.get("turns") or [],
            )
            # Prefer classifier follow-up continuity
            if classification_hint.get("follow_up") and classification_hint.get("answer"):
                result["category"] = classification_hint["id"]
                result["severity"] = classification_hint.get("severity", result.get("severity"))
                result["escalate"] = classification_hint.get("escalate", result.get("escalate"))
                # Append next clarification if troubleshooting continues
                qs = classification_hint.get("clarification_questions") or []
                from ..config import settings as _s
                # A comprehension request already has a simplified answer. Do not append
                # another question to it; that was making "samajh nahi aaya" replies
                # look generic and confusing. For ordinary follow-ups, one next-step
                # question is useful when the answer does not already contain one.
                if (qs and _s.resolved_ai_provider == "offline"
                        and not classification_hint.get("simplify")
                        and "batayein" not in (result.get("answer") or "").lower()):
                    result["answer"] = (
                        (result.get("answer") or classification_hint["answer"])
                        + "\n\nAgla step: "
                        + qs[0]
                    )
                    result["clarification_questions"] = qs

            reply = result["answer"]
            data = {
                "citations": result.get("citations", []),
                "insufficient": False,
                "needs_details": result.get("needs_details", False),
                "clarification_questions": result.get("clarification_questions", []),
                "category": result.get("category", ""),
                "severity": result.get("severity", "normal"),
                "escalate": result.get("escalate", False),
                "escalation_reason": result.get("escalation_reason", ""),
                "department": result.get("department", ""),
                "priority": result.get("priority", ""),
                "title": result.get("title", ""),
            }
            if data["escalate"] and not _is_staff_user(user):
                # Complaints are only registered through the verified intake above. Never
                # claim a case was forwarded when nothing was saved.
                existing = (
                    db.query(Complaint)
                    .filter(Complaint.source_session_uuid == session.uuid, Complaint.customer_id == user.id)
                    .order_by(Complaint.id.desc()).first()
                )
                if existing is not None:
                    data["complaint_code"] = existing.code
                else:
                    data["escalate"] = False
                    data["escalation_reason"] = ""

    fw_out = output_firewall(db, reply, allow_own_pii=False)
    if not fw_out["allowed"]:
        reply = "I'm not able to confirm that safely from an approved source. I'll route this to a human agent."
        data["blocked_output"] = fw_out["categories"]

    reply_redacted = pii.redact_text(reply)
    _store(db, session, text, reply_redacted, detected["language"], modality, data)
    memory.remember(
        db,
        scope="session",
        key="last_topic",
        value=reply_redacted[:200],
        source="assistant",
        owner_user_id=user.id,
        session_uuid=session.uuid,
    )
    return {
        "reply": reply_redacted,
        "blocked": False,
        "data": data,
        "language": detected,
        "tts_hint": language.LANGUAGES.get(detected["language"], language.LANGUAGES["en"])["tts"],
    }


def _store(
    db: Session,
    session: AssistantSession,
    user_text: str,
    reply: str,
    lang: str,
    modality: str,
    meta: dict,
) -> None:
    db.add(
        AssistantMessage(
            session_id=session.id,
            role="user",
            text=pii.redact_text(user_text),
            language=lang,
            modality=modality,
            meta={},
        )
    )
    safe_meta = {
        k: v
        for k, v in (meta or {}).items()
        if k
        in {
            "category",
            "severity",
            "escalate",
            "escalation_reason",
            "complaint_code",
            "needs_details",
            "clarification_questions",
            "department",
            "priority",
            "title",
            "blocked",
            "pending_complaint",
            "awaiting_mobile",
            "complaint_refused",
        }
    }
    db.add(
        AssistantMessage(
            session_id=session.id,
            role="assistant",
            text=reply,
            language=lang,
            modality=modality,
            meta=safe_meta,
        )
    )
    db.commit()


def history(db: Session, session: AssistantSession, limit: int = 30) -> list[dict]:
    rows = (
        db.query(AssistantMessage)
        .filter(AssistantMessage.session_id == session.id)
        .order_by(AssistantMessage.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "role": r.role,
            "text": r.text,
            "language": r.language,
            "modality": r.modality,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "data": r.meta or {},
        }
        for r in reversed(rows)
    ]
