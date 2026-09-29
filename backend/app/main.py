"""SupportNova — FastAPI application entry point.

Wires together every router, initialises the database, seeds the demo
environment on first start and (optionally) serves the built React frontend
so the whole product can run as a single service.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import PROJECT_DIR, STORAGE_DIR, settings
from .database import Base, SessionLocal, engine
from .routers import (
    admin,
    auth,
    complaints,
    dashboard,
    documents,
    lab,
    manual_review,
    policies,
    public,
    reports,
    rules,
    security,
    telecom,
    trust,
    agent,
)
from .seed import run_demo_pipeline, seed_database
from .nova.evidence import seed_transactions
from .routers import nova as nova_router
from .services.genai_client import provider_status
from .services.trust_engine import ensure_trust_assessments
from .nova.migrate import ensure_additive_columns

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("supportnova")

FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"


def _bootstrap() -> dict:
    """Create tables, storage folders and seed the demo environment."""
    Base.metadata.create_all(bind=engine)
    result_migration = ensure_additive_columns(engine)   # v2: additive columns on v1 databases
    (STORAGE_DIR / "documents").mkdir(parents=True, exist_ok=True)
    (STORAGE_DIR / "attachments").mkdir(parents=True, exist_ok=True)

    result: dict = {}
    if result_migration:
        result["migrated_columns"] = result_migration
    db = SessionLocal()
    try:
        if settings.seed_on_startup:
            result["seed"] = seed_database(db)
            result["nova_transactions_seeded"] = seed_transactions(db)
            if settings.resolved_ai_provider == "offline" and settings.demo_analysis_limit > 0:
                result["demo_pipeline"] = run_demo_pipeline(db, settings.demo_analysis_limit)
        # Backfill Trust Gate verdicts for validations created before the gate.
        backfilled = ensure_trust_assessments(db)
        if backfilled:
            result["trust_assessments_backfilled"] = backfilled
    finally:
        db.close()
    return result


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _bootstrap()
    logger.info("SupportNova ready — AI provider: %s", provider_status())
    yield


app = FastAPI(
    title="SupportNova API",
    description=(
        "AI-Powered Complaint Intelligence & Resolution System. "
        "Pipeline 1: GenAI complaint analysis. Pipeline 2: independent Python "
        "ground-truth validation. The validation engine never depends on the "
        "GenAI provider."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API routers -----------------------------------------------------------
app.include_router(auth.router)
app.include_router(complaints.router)
app.include_router(documents.router)
app.include_router(policies.router)
app.include_router(public.router)
app.include_router(rules.router)
app.include_router(manual_review.router)
app.include_router(dashboard.router)
app.include_router(reports.router)
app.include_router(security.router)
app.include_router(trust.router)
app.include_router(lab.router)
app.include_router(admin.router)
app.include_router(telecom.router)
app.include_router(agent.router)
app.include_router(nova_router.router)


@app.get("/api/health", tags=["system"])
def health() -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "provider": provider_status(),
        "frontend_bundled": FRONTEND_DIST.exists(),
    }


# --- Static frontend (single-service deployment) ---------------------------
if FRONTEND_DIST.exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith(("api/", "docs", "openapi.json", "redoc")):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.debug)
