from __future__ import annotations
from datetime import datetime, timedelta, timezone
import hashlib, hmac
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from .config import settings
from .database import get_db
from .models import User

bearer = HTTPBearer(auto_error=False)

def hash_password(password: str) -> str:
    salt = hashlib.sha256((settings.secret_key + password).encode()).hexdigest()[:32]
    digest = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"sha256${salt}${digest}"

def verify_password(password: str, encoded: str) -> bool:
    try:
        _, salt, digest = encoded.split("$", 2)
        return hmac.compare_digest(hashlib.sha256((salt + password).encode()).hexdigest(), digest)
    except Exception:
        return False

def create_access_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({"sub": str(user.id), "role": user.role.name if user.role else "", "exp": exp}, settings.secret_key, algorithm=settings.jwt_algorithm)

def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        payload = jwt.decode(credentials.credentials, settings.secret_key, algorithms=[settings.jwt_algorithm])
        uid = int(payload.get("sub"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user = db.get(User, uid)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user")
    return user

def require_staff(user: User = Depends(get_current_user)) -> User:
    if not user.role or user.role.name not in {"admin", "agent"}:
        raise HTTPException(status_code=403, detail="Staff access required")
    return user

def require_roles(*allowed_roles: str):
    allowed = set(allowed_roles)

    def dependency(user: User = Depends(get_current_user)) -> User:
        if not user.role or user.role.name not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient role permissions")
        return user

    return dependency

def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.role or user.role.name != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user
