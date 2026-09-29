"""Telecom platform APIs: profile, SIMs, packages, orders, lost SIM, notifications, locations."""
from __future__ import annotations

import random
import secrets
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..audit import log_action
from ..database import get_db
from ..models import (
    AppNotification,
    CustomerProfile,
    CustomerSubscription,
    DeviceLocation,
    LostSimRequest,
    SimCard,
    TelecomOrder,
    TelecomPackage,
    User,
)
from ..security import get_current_user, hash_password, require_staff
from ..utils import utcnow

router = APIRouter(prefix="/api/telecom", tags=["telecom"])


def _is_admin(user: User) -> bool:
    return bool(user.role and user.role.name == "admin")


def _is_staff(user: User) -> bool:
    return bool(user.role and user.role.name in {"admin", "agent"})


def _mask_cnic(cnic: str) -> str:
    c = (cnic or "").replace("-", "").strip()
    if len(c) < 5:
        return "****"
    return c[:5] + "*******" + c[-1:] if len(c) >= 6 else "*****"


def _mask_sim(num: str) -> str:
    n = num or ""
    if len(n) < 6:
        return "****"
    return n[:4] + "****" + n[-4:]


def _notify(db: Session, user_id: int, title: str, body: str, category: str = "general", link: str = "") -> None:
    db.add(AppNotification(user_id=user_id, title=title, body=body, category=category, link=link))


def _profile_dict(p: CustomerProfile, user: User, full: bool = False) -> dict:
    return {
        "user_id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "phone_number": p.phone_number,
        "cnic_masked": _mask_cnic(p.cnic),
        "cnic": p.cnic if full and _is_admin(user) else None,
        "address": p.address,
        "date_of_birth": p.date_of_birth,
        "verification_status": p.verification_status,
        "account_status": "ACTIVE" if user.is_active else "INACTIVE",
        "last_login": p.last_login.isoformat() if p.last_login else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _sim_dict(s: SimCard, package: Optional[TelecomPackage] = None) -> dict:
    return {
        "id": s.id,
        "sim_number": s.sim_number,
        "sim_number_masked": _mask_sim(s.sim_number),
        "phone_number": s.phone_number,
        "customer_id": s.customer_id,
        "sim_type": s.sim_type,
        "network": s.network,
        "status": s.status,
        "activation_date": s.activation_date.isoformat() if s.activation_date else None,
        "registration_date": s.registration_date.isoformat() if s.registration_date else None,
        "current_package_id": s.current_package_id,
        "current_package": package.name if package else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _pkg_dict(p: TelecomPackage) -> dict:
    return {
        "id": p.id,
        "code": p.code,
        "name": p.name,
        "description": p.description,
        "category": p.category,
        "price": p.price,
        "validity_days": p.validity_days,
        "internet_data_mb": p.internet_data_mb,
        "call_minutes": p.call_minutes,
        "sms_count": p.sms_count,
        "status": p.status,
    }


def _order_dict(o: TelecomOrder) -> dict:
    return {
        "id": o.id,
        "order_code": o.order_code,
        "customer_id": o.customer_id,
        "order_type": o.order_type,
        "product_id": o.product_id,
        "product_label": o.product_label,
        "sim_id": o.sim_id,
        "amount": o.amount,
        "payment_status": o.payment_status,
        "order_status": o.order_status,
        "notes": o.notes,
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "completed_at": o.completed_at.isoformat() if o.completed_at else None,
    }


# ── Profile / me ──────────────────────────────────────────────────────────

@router.get("/me")
def get_me(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.query(CustomerProfile).filter(CustomerProfile.user_id == user.id).first()
    if not p:
        return {
            "user_id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "phone_number": "",
            "cnic_masked": "",
            "address": "",
            "verification_status": "N/A",
            "account_status": "ACTIVE" if user.is_active else "INACTIVE",
            "role": user.role.name if user.role else "",
        }
    data = _profile_dict(p, user, full=_is_admin(user))
    data["role"] = user.role.name if user.role else ""
    return data


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    address: Optional[str] = None
    date_of_birth: Optional[str] = None


@router.put("/me")
def update_me(payload: ProfileUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.full_name:
        user.full_name = payload.full_name
    p = db.query(CustomerProfile).filter(CustomerProfile.user_id == user.id).first()
    if p:
        if payload.address is not None:
            p.address = payload.address
        if payload.date_of_birth is not None:
            p.date_of_birth = payload.date_of_birth
        p.updated_at = utcnow()
    db.commit()
    return get_me(db, user)


# ── OTP verify (demo: accept 123456 or stored code) ───────────────────────

class OtpVerify(BaseModel):
    otp: str


@router.post("/me/verify-otp")
def verify_otp(payload: OtpVerify, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.query(CustomerProfile).filter(CustomerProfile.user_id == user.id).first()
    if not p:
        raise HTTPException(404, "Profile not found")
    code = (payload.otp or "").strip()
    ok = code == "123456" or (p.otp_code and code == p.otp_code)
    if not ok:
        raise HTTPException(400, "Invalid OTP. Demo OTP is 123456.")
    p.verification_status = "VERIFIED"
    p.otp_code = ""
    p.updated_at = utcnow()
    _notify(db, user.id, "Account verified", "Your phone number has been verified.", "account", "/profile")
    db.commit()
    return {"ok": True, "verification_status": "VERIFIED"}


@router.post("/me/send-otp")
def send_otp(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.query(CustomerProfile).filter(CustomerProfile.user_id == user.id).first()
    if not p:
        raise HTTPException(404, "Profile not found")
    p.otp_code = "123456"
    p.otp_expires_at = utcnow() + timedelta(minutes=15)
    _notify(db, user.id, "OTP sent", "Your demo OTP is 123456 (valid 15 min).", "account", "")
    db.commit()
    return {"ok": True, "message": "OTP sent. Demo code: 123456"}


# ── Packages ──────────────────────────────────────────────────────────────

@router.get("/packages")
def list_packages(
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(TelecomPackage).filter(TelecomPackage.status == "ACTIVE")
    if category:
        q = q.filter(TelecomPackage.category == category)
    rows = q.order_by(TelecomPackage.price).all()
    return {"items": [_pkg_dict(p) for p in rows], "total": len(rows)}


@router.get("/packages/{package_id}")
def get_package(package_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.query(TelecomPackage).filter(TelecomPackage.id == package_id).first()
    if not p:
        raise HTTPException(404, "Package not found")
    return _pkg_dict(p)


class SubscribeBody(BaseModel):
    sim_id: Optional[int] = None
    payment_method: str = "Wallet/Balance"
    payment_reference: Optional[str] = None


@router.post("/packages/{package_id}/subscribe")
def subscribe_package(
    package_id: int,
    body: SubscribeBody = SubscribeBody(),
    request: Request = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pkg = db.query(TelecomPackage).filter(TelecomPackage.id == package_id, TelecomPackage.status == "ACTIVE").first()
    if not pkg:
        raise HTTPException(404, "Package not found")
    sim = None
    if body.sim_id:
        sim = db.query(SimCard).filter(SimCard.id == body.sim_id, SimCard.customer_id == user.id).first()
        if not sim:
            raise HTTPException(404, "SIM not found on your account")
    else:
        sim = (
            db.query(SimCard)
            .filter(SimCard.customer_id == user.id, SimCard.status == "ACTIVE")
            .order_by(SimCard.id)
            .first()
        )
    order = TelecomOrder(
        order_code="TMP",
        customer_id=user.id,
        order_type="PACKAGE",
        product_id=pkg.id,
        product_label=pkg.name,
        sim_id=sim.id if sim else None,
        amount=pkg.price,
        payment_status="PAID",
        order_status="COMPLETED",
        notes=f"Package subscription | Payment: {body.payment_method} | Ref: {body.payment_reference or 'DEMO-' + secrets.token_hex(4).upper()}",
        completed_at=utcnow(),
    )
    db.add(order)
    db.flush()
    order.order_code = f"ORD-{order.id:05d}"
    sub = CustomerSubscription(
        customer_id=user.id,
        sim_id=sim.id if sim else None,
        package_id=pkg.id,
        status="ACTIVE",
        start_date=utcnow(),
        end_date=utcnow() + timedelta(days=pkg.validity_days),
    )
    db.add(sub)
    if sim:
        sim.current_package_id = pkg.id
        sim.updated_at = utcnow()
    _notify(
        db,
        user.id,
        "Package activated",
        f"{pkg.name} is now active on your account.",
        "package",
        "/packages",
    )
    log_action(db, "package.subscribe", "order", order.order_code, {"package": pkg.code}, user=user, request=request)
    db.commit()
    return {"order": _order_dict(order), "subscription_id": sub.id, "package": _pkg_dict(pkg)}


# ── SIMs ──────────────────────────────────────────────────────────────────

@router.get("/sims")
def list_sims(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if _is_staff(user):
        rows = db.query(SimCard).order_by(SimCard.id.desc()).limit(200).all()
    else:
        rows = db.query(SimCard).filter(SimCard.customer_id == user.id).order_by(SimCard.id.desc()).all()
    pkgs = {p.id: p for p in db.query(TelecomPackage).all()}
    return {"items": [_sim_dict(s, pkgs.get(s.current_package_id)) for s in rows], "total": len(rows)}


@router.get("/sims/{sim_id}")
def get_sim(sim_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    s = db.query(SimCard).filter(SimCard.id == sim_id).first()
    if not s:
        raise HTTPException(404, "SIM not found")
    if not _is_staff(user) and s.customer_id != user.id:
        raise HTTPException(403, "Not your SIM")
    pkg = db.query(TelecomPackage).filter(TelecomPackage.id == s.current_package_id).first() if s.current_package_id else None
    return _sim_dict(s, pkg)


class BuySimBody(BaseModel):
    sim_type: str = "Prepaid"
    network: str = "4G"
    plan_package_id: Optional[int] = None
    full_name: str = ""
    cnic: str = ""
    date_of_birth: Optional[str] = None
    contact_number: str = ""
    delivery_address: str = ""
    city: str = ""
    postal_area: str = ""
    offer_code: Optional[str] = None
    payment_method: Optional[str] = None


@router.post("/sims/purchase")
def purchase_sim(
    body: BuySimBody,
    request: Request = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not body.full_name.strip() or not body.cnic.strip() or not body.contact_number.strip() or not body.delivery_address.strip() or not body.city.strip():
        raise HTTPException(400, "Full name, CNIC, contact number, delivery address and city are required.")
    if len(body.cnic.replace("-", "")) != 13:
        raise HTTPException(400, "Enter a valid 13-digit CNIC.")

    phone = "03" + "".join(str(random.randint(0, 9)) for _ in range(9))
    while db.query(SimCard).filter(SimCard.phone_number == phone).first():
        phone = "03" + "".join(str(random.randint(0, 9)) for _ in range(9))
    sim_number = "8992" + "".join(str(random.randint(0, 9)) for _ in range(12))

    # Demo offer handling: an explicitly named FREE offer makes the SIM free; otherwise normal price applies.
    is_free = bool(body.offer_code and body.offer_code.upper().startswith("FREE"))
    price = 0.0 if is_free else (500.0 if body.sim_type == "Prepaid" else 1500.0)
    payment_status = "PAID" if price == 0 else ("PAID" if body.payment_method else "PENDING")
    order_status = "PROCESSING" if price > 0 and payment_status == "PENDING" else "DELIVERY"

    sim = SimCard(
        sim_number=sim_number, phone_number=phone, customer_id=user.id, sim_type=body.sim_type,
        network=body.network, status="PENDING", registration_date=utcnow(), current_package_id=body.plan_package_id,
    )
    db.add(sim)
    db.flush()
    payment_ref = body.payment_method and f"DEMO-{secrets.token_hex(4).upper()}" or ""
    details = (
        f"Registration: {body.full_name} | CNIC: {_mask_cnic(body.cnic)} | DOB: {body.date_of_birth or 'Not provided'} | "
        f"Contact: {body.contact_number} | Delivery: {body.delivery_address}, {body.city} {body.postal_area} | "
        f"Offer: {body.offer_code or 'Standard'} | Payment: {body.payment_method or 'Pending'} | Ref: {payment_ref or 'Required'}"
    )
    order = TelecomOrder(
        order_code="TMP", customer_id=user.id, order_type="SIM", product_id=sim.id,
        product_label=f"{body.sim_type} SIM — delivery to {body.city}", sim_id=sim.id, amount=price,
        payment_status=payment_status, order_status=order_status, notes=details,
    )
    db.add(order)
    db.flush()
    order.order_code = f"ORD-{order.id:05d}"

    if payment_status == "PAID":
        sim.status = "ACTIVE"
        sim.activation_date = utcnow()
    else:
        sim.status = "PENDING"

    _notify(db, user.id, "New SIM order received", f"{order.order_code} is being processed. Your SIM will be delivered to {body.city}.", "sim", "/orders")
    log_action(db, "sim.purchase", "order", order.order_code, {"price": price, "offer": body.offer_code, "payment": body.payment_method}, user=user, request=request)
    db.commit()
    return {"sim": _sim_dict(sim), "order": _order_dict(order), "payment_required": price > 0 and payment_status != "PAID", "payment_reference": payment_ref or None}


class LostSimBody(BaseModel):
    reason: str
    description: str = ""
    confirm: bool = False

@router.post("/sims/{sim_id}/lost")
def report_lost(
    sim_id: int,
    body: LostSimBody,
    request: Request = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = db.query(SimCard).filter(SimCard.id == sim_id, SimCard.customer_id == user.id).first()
    if not s:
        raise HTTPException(404, "SIM not found on your account")
    if s.status in {"LOST", "BLOCKED", "DEACTIVATED"}:
        raise HTTPException(400, f"SIM already {s.status}")
    if body.reason not in {"Lost", "Stolen", "Damaged", "Other"}:
        raise HTTPException(400, "Choose a valid reason.")
    if not body.confirm:
        raise HTTPException(400, "Please confirm that you want to block this SIM.")
    s.status = "LOST"
    s.updated_at = utcnow()
    req = LostSimRequest(
        request_code="TMP",
        customer_id=user.id,
        sim_id=s.id,
        verification_status="VERIFIED",
        sim_status_after="LOST",
        notes=f"Reason: {body.reason}. {body.description.strip()}".strip(),
    )
    db.add(req)
    db.flush()
    req.request_code = f"LSR-{req.id:05d}"
    # Block after report
    s.status = "BLOCKED"
    _notify(
        db,
        user.id,
        "Lost SIM request submitted",
        f"{s.phone_number} marked LOST/BLOCKED. Request {req.request_code}. You can request a replacement.",
        "sim",
        "/sims",
    )
    log_action(db, "sim.lost", "sim", s.phone_number, {"request": req.request_code}, user=user, request=request)
    db.commit()
    return {
        "request_code": req.request_code,
        "sim": _sim_dict(s),
        "message": "SIM reported lost and blocked pending replacement. Location access is role-restricted.",
    }


@router.post("/sims/{sim_id}/replacement")
def request_replacement(
    sim_id: int,
    request: Request = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    old = db.query(SimCard).filter(SimCard.id == sim_id, SimCard.customer_id == user.id).first()
    if not old:
        raise HTTPException(404, "SIM not found")
    if old.status not in {"LOST", "BLOCKED", "REPLACEMENT_REQUESTED"}:
        raise HTTPException(400, "Report SIM as lost first")
    old.status = "REPLACEMENT_REQUESTED"
    phone = old.phone_number
    new_sim_number = "8992" + "".join(str(random.randint(0, 9)) for _ in range(12))
    new_sim = SimCard(
        sim_number=new_sim_number,
        phone_number=phone + "-NEW",
        customer_id=user.id,
        sim_type=old.sim_type,
        network=old.network,
        status="PENDING",
        registration_date=utcnow(),
        current_package_id=old.current_package_id,
    )
    # Keep the old database row for audit/history, but free the unique MSISDN so the
    # replacement row can carry the customer's original number.
    old.phone_number = f"ARCHIVED-{old.id}-{phone}"
    new_sim.phone_number = phone
    db.add(new_sim)
    db.flush()
    old.replaced_by_id = new_sim.id
    order = TelecomOrder(
        order_code="TMP",
        customer_id=user.id,
        order_type="REPLACEMENT",
        product_id=new_sim.id,
        product_label=f"Replacement SIM for {phone}",
        sim_id=new_sim.id,
        amount=300.0,
        payment_status="PAID",
        order_status="PROCESSING",
        notes=f"Replaces SIM id {old.id}",
    )
    db.add(order)
    db.flush()
    order.order_code = f"ORD-{order.id:05d}"
    # Activate immediately for demo continuity
    new_sim.status = "ACTIVE"
    new_sim.activation_date = utcnow()
    order.order_status = "COMPLETED"
    order.completed_at = utcnow()
    lsr = (
        db.query(LostSimRequest)
        .filter(LostSimRequest.sim_id == old.id)
        .order_by(LostSimRequest.id.desc())
        .first()
    )
    if lsr:
        lsr.replacement_order_id = order.id
        lsr.updated_at = utcnow()
    _notify(db, user.id, "Replacement SIM activated", f"New SIM for {phone} is active.", "sim", "/sims")
    log_action(db, "sim.replacement", "sim", phone, {"order": order.order_code}, user=user, request=request)
    db.commit()
    return {"new_sim": _sim_dict(new_sim), "order": _order_dict(order), "old_sim_id": old.id}


# ── Location (staff only, audited, simulated) ─────────────────────────────

@router.get("/locations/{sim_id}/latest")
def latest_location(
    sim_id: int,
    request: Request = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not _is_staff(user):
        raise HTTPException(403, "Location is restricted to authorized staff")
    s = db.query(SimCard).filter(SimCard.id == sim_id).first()
    if not s:
        raise HTTPException(404, "SIM not found")
    loc = (
        db.query(DeviceLocation)
        .filter(DeviceLocation.sim_id == sim_id)
        .order_by(DeviceLocation.recorded_at.desc())
        .first()
    )
    log_action(db, "location.view", "sim", s.phone_number, {"sim_id": sim_id}, user=user, request=request)
    db.commit()
    if not loc:
        return {
            "location_available": False,
            "location_status": "Unavailable",
            "source": "SIMULATED_DEMO_LOCATION",
            "note": "No location snapshot on file. Demo mode only — not live tracking.",
        }
    return {
        "location_available": True,
        "latitude": loc.latitude,
        "longitude": loc.longitude,
        "accuracy_m": loc.accuracy_m,
        "timestamp": loc.recorded_at.isoformat() if loc.recorded_at else None,
        "source": "SIMULATED_DEMO_LOCATION",
        "location_status": loc.location_status,
        "note": "SIMULATED DEMO LOCATION — not real telecom tracking.",
    }


# ── Orders ────────────────────────────────────────────────────────────────

@router.get("/orders")
def list_orders(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if _is_staff(user):
        rows = db.query(TelecomOrder).order_by(TelecomOrder.id.desc()).limit(200).all()
    else:
        rows = db.query(TelecomOrder).filter(TelecomOrder.customer_id == user.id).order_by(TelecomOrder.id.desc()).all()
    return {"items": [_order_dict(o) for o in rows], "total": len(rows)}


class OrderStatusBody(BaseModel):
    order_status: str
    payment_status: Optional[str] = None


@router.put("/orders/{order_id}")
def update_order(
    order_id: int,
    body: OrderStatusBody,
    request: Request = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    o = db.query(TelecomOrder).filter(TelecomOrder.id == order_id).first()
    if not o:
        raise HTTPException(404, "Order not found")
    o.order_status = body.order_status
    if body.payment_status:
        o.payment_status = body.payment_status
    if body.order_status == "COMPLETED":
        o.completed_at = utcnow()
    log_action(db, "order.update", "order", o.order_code, body.model_dump(), user=user, request=request)
    db.commit()
    return _order_dict(o)


# ── Lost SIM admin list ───────────────────────────────────────────────────

@router.get("/lost-requests")
def list_lost(db: Session = Depends(get_db), user: User = Depends(require_staff)):
    rows = db.query(LostSimRequest).order_by(LostSimRequest.id.desc()).limit(100).all()
    out = []
    for r in rows:
        sim = db.query(SimCard).filter(SimCard.id == r.sim_id).first()
        cust = db.query(User).filter(User.id == r.customer_id).first()
        out.append(
            {
                "id": r.id,
                "request_code": r.request_code,
                "customer_id": r.customer_id,
                "customer_name": cust.full_name if cust else "",
                "sim_id": r.sim_id,
                "phone_number": sim.phone_number if sim else "",
                "sim_status": sim.status if sim else "",
                "verification_status": r.verification_status,
                "replacement_order_id": r.replacement_order_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
        )
    return {"items": out, "total": len(out)}


# ── Notifications ─────────────────────────────────────────────────────────

@router.get("/notifications")
def list_notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (
        db.query(AppNotification)
        .filter(AppNotification.user_id == user.id)
        .order_by(AppNotification.id.desc())
        .limit(50)
        .all()
    )
    return {
        "items": [
            {
                "id": n.id,
                "title": n.title,
                "body": n.body,
                "category": n.category,
                "is_read": n.is_read,
                "link": n.link,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in rows
        ],
        "unread": sum(1 for n in rows if not n.is_read),
    }


@router.post("/notifications/{nid}/read")
def mark_read(nid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = db.query(AppNotification).filter(AppNotification.id == nid, AppNotification.user_id == user.id).first()
    if not n:
        raise HTTPException(404, "Not found")
    n.is_read = True
    db.commit()
    return {"ok": True}


# ── Customer dashboard aggregate ──────────────────────────────────────────

@router.get("/dashboard")
def customer_dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    sims = db.query(SimCard).filter(SimCard.customer_id == user.id).all()
    orders = (
        db.query(TelecomOrder)
        .filter(TelecomOrder.customer_id == user.id)
        .order_by(TelecomOrder.id.desc())
        .limit(5)
        .all()
    )
    subs = (
        db.query(CustomerSubscription)
        .filter(CustomerSubscription.customer_id == user.id, CustomerSubscription.status == "ACTIVE")
        .all()
    )
    pkgs = {p.id: p for p in db.query(TelecomPackage).all()}
    notes = (
        db.query(AppNotification)
        .filter(AppNotification.user_id == user.id)
        .order_by(AppNotification.id.desc())
        .limit(5)
        .all()
    )
    from ..models import Complaint

    complaints = (
        db.query(Complaint)
        .filter(Complaint.customer_id == user.id)
        .order_by(Complaint.id.desc())
        .limit(5)
        .all()
    )
    profile = db.query(CustomerProfile).filter(CustomerProfile.user_id == user.id).first()
    return {
        "profile": _profile_dict(profile, user) if profile else {"full_name": user.full_name, "email": user.email},
        "sims": [_sim_dict(s, pkgs.get(s.current_package_id)) for s in sims],
        "active_subscriptions": [
            {
                "id": s.id,
                "package": _pkg_dict(pkgs[s.package_id]) if s.package_id in pkgs else None,
                "sim_id": s.sim_id,
                "end_date": s.end_date.isoformat() if s.end_date else None,
            }
            for s in subs
        ],
        "recent_orders": [_order_dict(o) for o in orders],
        "notifications": [
            {"id": n.id, "title": n.title, "body": n.body, "is_read": n.is_read, "created_at": n.created_at.isoformat() if n.created_at else None}
            for n in notes
        ],
        "recent_complaints": [
            {"id": c.id, "code": c.code, "title": c.title, "status": c.status, "priority": c.priority}
            for c in complaints
        ],
        "counts": {
            "sims": len(sims),
            "active_sims": sum(1 for s in sims if s.status == "ACTIVE"),
            "active_packages": len(subs),
            "open_complaints": sum(1 for c in complaints if c.status not in {"RESOLVED", "CLOSED", "REJECTED"}),
        },
    }


# ── Admin stats ───────────────────────────────────────────────────────────

@router.get("/admin/stats")
def admin_telecom_stats(db: Session = Depends(get_db), user: User = Depends(require_staff)):
    from ..models import Complaint

    return {
        "total_customers": db.query(CustomerProfile).count(),
        "active_sims": db.query(SimCard).filter(SimCard.status == "ACTIVE").count(),
        "lost_blocked_sims": db.query(SimCard).filter(SimCard.status.in_(["LOST", "BLOCKED"])).count(),
        "active_packages_catalog": db.query(TelecomPackage).filter(TelecomPackage.status == "ACTIVE").count(),
        "orders_today": db.query(TelecomOrder).count(),
        "pending_orders": db.query(TelecomOrder).filter(TelecomOrder.order_status == "PENDING").count(),
        "open_complaints": db.query(Complaint).filter(Complaint.status.notin_(["RESOLVED", "CLOSED", "REJECTED"])).count(),
        "lost_requests": db.query(LostSimRequest).count(),
    }


@router.get("/admin/customers")
def admin_customers(
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    rows = db.query(CustomerProfile).order_by(CustomerProfile.id.desc()).limit(100).all()
    out = []
    for p in rows:
        u = db.query(User).filter(User.id == p.user_id).first()
        if not u:
            continue
        if q:
            qq = q.lower()
            if qq not in (u.full_name or "").lower() and qq not in (p.phone_number or "") and qq not in (u.email or "").lower():
                continue
        sim_count = db.query(SimCard).filter(SimCard.customer_id == u.id).count()
        out.append({**_profile_dict(p, u, full=_is_admin(user)), "sim_count": sim_count})
    return {"items": out, "total": len(out)}
