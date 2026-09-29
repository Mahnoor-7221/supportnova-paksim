"""Versioned prompt management.

Prompts live as files under backend/prompt_templates/ and are registered in
the prompt_versions table (name, version, checksum, active flag). The active
version of each prompt is used at runtime and recorded on every AI analysis.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from string import Template
from typing import Optional

from sqlalchemy.orm import Session

from ..config import PROMPT_DIR
from ..models import PromptVersion


class PromptManager:
    def __init__(self) -> None:
        manifest_path = PROMPT_DIR / "manifest.json"
        if manifest_path.exists():
            with open(manifest_path, "r", encoding="utf-8") as fh:
                manifest = json.load(fh)
            self._entries: list[dict] = manifest.get("prompts", [])
        else:
            self._entries = [
                {"name": "complaint_analysis", "version": "v1", "file": "complaint_analysis.txt", "active": True},
                {"name": "validation_repair", "version": "v1", "file": "validation_repair.txt", "active": True},
                {"name": "response_generation", "version": "v1", "file": "response_generation.txt", "active": True},
            ]
            PROMPT_DIR.mkdir(parents=True, exist_ok=True)
            defaults = {
                "complaint_analysis.txt": "Analyze this complaint using the approved policy context. Return JSON with issue_category, subcategory, sentiment, urgency, priority, department, policy_id, professional_response, recommended_action, escalation.",
                "validation_repair.txt": "Repair the previous JSON response so it is valid and contains the required complaint analysis fields. Error: $error\nPrevious: $previous",
                "response_generation.txt": "Generate a concise professional customer response grounded only in the supplied complaint and policy context.\nComplaint: $complaint\nPolicy: $policy_context",
            }
            for filename, text in defaults.items():
                path = PROMPT_DIR / filename
                if not path.exists(): path.write_text(text, encoding="utf-8")
        self._texts: dict[str, str] = {}

    # -- file access -------------------------------------------------------
    def _load_text(self, file_name: str) -> str:
        if file_name not in self._texts:
            with open(PROMPT_DIR / file_name, "r", encoding="utf-8") as fh:
                self._texts[file_name] = fh.read()
        return self._texts[file_name]

    def _entry(self, name: str, version: Optional[str] = None) -> dict:
        candidates = [e for e in self._entries if e["name"] == name]
        if version:
            for e in candidates:
                if e["version"] == version:
                    return e
            raise KeyError(f"Prompt {name} {version} not found")
        for e in candidates:
            if e.get("active"):
                return e
        if candidates:
            return candidates[-1]
        raise KeyError(f"Prompt {name} not found in manifest")

    # -- public API --------------------------------------------------------
    def get_prompt(self, name: str, version: Optional[str] = None) -> tuple[str, dict]:
        entry = self._entry(name, version)
        text = self._load_text(entry["file"])
        return text, entry

    def render(self, name: str, variables: dict, version: Optional[str] = None) -> tuple[str, dict]:
        text, entry = self.get_prompt(name, version)
        rendered = Template(text).safe_substitute(**variables)
        return rendered, entry

    @staticmethod
    def checksum(file_name: str) -> str:
        try:
            with open(PROMPT_DIR / file_name, "rb") as fh:
                return hashlib.sha256(fh.read()).hexdigest()[:32]
        except OSError:
            return ""

    def sync_db(self, db: Session) -> dict[str, PromptVersion]:
        """Ensure every manifest entry has a prompt_versions row. Returns active map."""
        active_map: dict[str, PromptVersion] = {}
        for entry in self._entries:
            row = (
                db.query(PromptVersion)
                .filter(PromptVersion.name == entry["name"], PromptVersion.version == entry["version"])
                .first()
            )
            if row is None:
                row = PromptVersion(
                    name=entry["name"],
                    version=entry["version"],
                    file_path=str(PROMPT_DIR / entry["file"]),
                    is_active=bool(entry.get("active")),
                    checksum=self.checksum(entry["file"]),
                    notes=entry.get("notes", ""),
                )
                db.add(row)
                db.flush()
            else:
                row.is_active = bool(entry.get("active"))
                row.checksum = self.checksum(entry["file"])
            if entry.get("active"):
                active_map[entry["name"]] = row
        db.commit()
        return active_map

    def active_version_row(self, db: Session, name: str) -> Optional[PromptVersion]:
        return (
            db.query(PromptVersion)
            .filter(PromptVersion.name == name, PromptVersion.is_active.is_(True))
            .first()
        )


@lru_cache(maxsize=1)
def get_prompt_manager() -> PromptManager:
    return PromptManager()
