"""Unauthenticated public endpoints (read-only support guidance)."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/api/public", tags=["public"])

_FILE = Path(__file__).resolve().parents[2] / "datasets" / "public_policies.json"


@router.get("/policies")
def public_policies() -> dict:
    """Public policy/guidance catalogue. Each entry references an approved
    knowledge-base policy (kb_ref) so public text stays consistent with Nova."""
    if not _FILE.exists():
        return {"count": 0, "policies": []}
    return json.loads(_FILE.read_text(encoding="utf-8"))
