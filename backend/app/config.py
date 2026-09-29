"""SupportNova — application configuration.

All secrets and environment specific behaviour are configured through
environment variables (see backend/.env.example). Never hardcode keys.
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
PROJECT_DIR = BASE_DIR.parent                              # repository root
PROMPT_DIR = BASE_DIR / "prompt_templates"
DATASET_DIR = BASE_DIR / "datasets"
STORAGE_DIR = BASE_DIR / "storage"


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables / .env file."""

    app_name: str = "SupportNova"
    app_env: str = "development"          # development | production
    debug: bool = True

    # --- database ---------------------------------------------------------
    # Default: SQLite (zero config, perfect for a hackathon demo).
    # Production: set DATABASE_URL to postgresql+psycopg2://... or mysql+pymysql://...
    database_url: str = f"sqlite:///{(BASE_DIR / 'supportnova.db').as_posix()}"

    # --- security ---------------------------------------------------------
    secret_key: str = "change-me-in-env-supportnova-dev-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 12 * 60
    max_upload_mb: int = 10
    allowed_upload_extensions: str = "pdf,docx,md,txt"

    # --- GenAI ------------------------------------------------------------
    # provider: gemini | offline
    #   gemini  -> real GenAI pipeline (requires GEMINI_API_KEY)
    #   offline -> deterministic heuristic baseline, clearly labelled in the
    #              UI as "offline baseline (not GenAI)". Used for demos and
    #              CI where no API key is available. The validation pipeline
    #              never depends on the provider and stays authoritative.
    ai_provider: str = "lovable"
    lovable_api_key: str = ""
    lovable_model: str = "openai/gpt-6-astra"
    lovable_api_base: str = "https://ai.gateway.lovable.dev/v1"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    gemini_api_base: str = "https://generativelanguage.googleapis.com/v1beta"
    ai_timeout_seconds: int = 60
    ai_max_retries: int = 2                   # schema-repair retries

    # --- seeding ----------------------------------------------------------
    seed_on_startup: bool = True
    seed_complaint_count: int = 5000          # expanded PakSim dataset; spec minimum is 500
    seed_unseen_count: int = 120              # reserved for the unseen comparison report
    # Run Pipeline 1 + Pipeline 2 on a sample of dataset complaints at first
    # startup (offline provider only) so dashboards are populated. The real
    # GenAI provider is never called automatically at startup.
    demo_analysis_limit: int = 48
    # Number of unseen cases to prepare automatically for the SRS comparison evidence.
    demo_unseen_evaluation_limit: int = 100

    # --- Nova intelligence layer (v2) -------------------------------------
    # Governance limits. AI may only auto-resolve low-risk, strongly verified
    # cases; everything else needs a human. Set NOVA_AUTO_RESOLVE_ENABLED=false
    # to disable autonomous resolution entirely (kill switch).
    nova_auto_resolve_enabled: bool = True
    nova_auto_resolve_min_trust: int = 95
    nova_financial_approval_threshold: float = 100.0   # amounts above this need a human
    nova_currency: str = "USD"
    # Optional LLM assistance for narrative agents (only used with a Gemini key;
    # deterministic agents remain authoritative and every LLM text is re-checked
    # by the output firewall).
    nova_llm_agents_enabled: bool = True
    # Voice: "browser" = Web Speech API in the client (no key needed);
    # "gemini" = server-side transcription of uploaded audio (needs GEMINI_API_KEY).
    nova_stt_provider: str = "browser"
    nova_rate_limit_per_minute: int = 40
    nova_evidence_extensions: str = "png,jpg,jpeg,webp,pdf,docx,md,txt"
    nova_audio_extensions: str = "wav,mp3,m4a,webm,ogg"
    nova_audio_max_mb: int = 15
    # Financial model assumptions (shown next to every estimate; edit to match your org).
    nova_support_cost_per_contact: float = 6.0
    nova_escalation_cost: float = 45.0
    nova_agent_hourly_cost: float = 18.0
    nova_compensation_pct: float = 0.10

    # --- CORS -------------------------------------------------------------
    cors_origins: str = "*"                    # comma separated; dev default: http://localhost:5173

    @property
    def allowed_extensions(self) -> set[str]:
        return {e.strip().lower() for e in self.allowed_upload_extensions.split(",") if e.strip()}

    @property
    def resolved_ai_provider(self) -> str:
        """Effective provider: falls back to offline when no key is configured."""
        if self.ai_provider == "gemini" and not self.gemini_api_key:
            return "offline"
        if self.ai_provider == "lovable" and not self.lovable_api_key:
            return "offline"
        return self.ai_provider

    @property
    def genai_live(self) -> bool:
        """True when a real GenAI provider (not the offline baseline) is active."""
        return self.resolved_ai_provider in ("gemini", "lovable")

    model_config = {"env_file": os.environ.get("SUPPORTNOVA_ENV_FILE", ".env"), "extra": "ignore"}


settings = Settings()
