"""Authentication endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..audit import log_action
from ..database import get_db
from ..models import Role, User
from ..schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut, ProfileUpdate, PasswordChange
from ..security import create_access_token, get_current_user, verify_password, hash_password
from ..serializers import user_dict

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    """Public account creation for customers, reachable from the marketing
    site's 'Create account' button. Always assigns the 'customer' role --
    staff accounts are created separately by an admin (see routers/admin.py)."""
    email = payload.email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")

    role = db.query(Role).filter(Role.name == "customer").first()
    if role is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Customer role is not configured")

    user = User(
        email=email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role_id=role.id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user)
    log_action(db, "auth.register", "user", user.id, {"email": email}, user=user, request=request)
    return TokenResponse(access_token=token, user=UserOut.from_user(user))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.strip().lower()).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        log_action(db, "auth.login_failed", "user", payload.email, {"reason": "invalid_credentials"}, request=request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    token = create_access_token(user)
    log_action(db, "auth.login", "user", user.id, {"email": user.email}, user=user, request=request)
    return TokenResponse(
        access_token=token,
        user=UserOut(
            id=user.id, email=user.email, full_name=user.full_name,
            is_active=user.is_active, role=user.role.name if user.role else "",
        ),
    )


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user_dict(user)


@router.patch("/profile")
def update_profile(payload: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.full_name = payload.full_name.strip()
    db.add(user)
    db.commit()
    db.refresh(user)
    return user_dict(user)


@router.post("/password")
def change_password(payload: PasswordChange, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must be different from the current password")
    user.password_hash = hash_password(payload.new_password)
    db.add(user)
    db.commit()
    return {"message": "Password changed successfully"}
