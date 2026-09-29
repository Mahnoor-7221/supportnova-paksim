"""Tiny additive schema migration.

``Base.metadata.create_all`` creates the new v2 tables but never alters an
existing one. Databases created by v1 therefore miss the two multilingual
columns on ``complaints``; this adds them (idempotently, additive only).
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger("supportnova.migrate")

ADDITIVE_COLUMNS: list[tuple[str, str, str]] = [
    ("complaints", "original_language", "VARCHAR(16) DEFAULT ''"),
    ("complaints", "translated_text", "TEXT DEFAULT ''"),
    ("complaints", "assigned_agent_id", "INTEGER"),
    ("complaints", "resolution_text", "TEXT DEFAULT ''"),
    ("complaints", "rejection_reason", "TEXT DEFAULT ''"),
    ("complaints", "source_session_uuid", "VARCHAR(36) DEFAULT ''"),
]


def ensure_additive_columns(engine: Engine) -> list[str]:
    """Add missing v2 columns to v1 tables. Returns the list of columns added."""
    added: list[str] = []
    inspector = inspect(engine)
    for table, column, ddl in ADDITIVE_COLUMNS:
        if not inspector.has_table(table):
            continue
        existing = {col["name"] for col in inspector.get_columns(table)}
        if column in existing:
            continue
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        added.append(f"{table}.{column}")
        logger.info("Added column %s.%s", table, column)
    return added
