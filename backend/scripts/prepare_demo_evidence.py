"""Prepare a submission/demo database with seeded roles, KB and 100 unseen evaluations.

This script is safe to run repeatedly. It never requires a live LLM: when no
provider key is configured, SupportNova uses its deterministic offline baseline.
"""
from __future__ import annotations

import logging

from app.database import Base, SessionLocal, engine
from app.config import settings
from app.seed import seed_database
from app.services.analysis_service import analyze_complaint
from app.python_validation import run_validation
from app.models import Complaint, DatasetCase, ValidationResult, User
from app.seed import _log_pipeline_run

logging.basicConfig(level=logging.INFO)


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_database(db)
        admin = db.query(User).filter(User.email == "admin@supportnova.demo").one()
        cases = db.query(DatasetCase).filter(DatasetCase.split == "unseen").order_by(DatasetCase.id).all()
        target = min(settings.demo_unseen_evaluation_limit, len(cases))
        processed = 0
        for case in cases:
            if processed >= target:
                break
            complaint = db.get(Complaint, case.complaint_id)
            if complaint is None:
                continue
            if db.query(ValidationResult).filter(ValidationResult.complaint_id == complaint.id).first():
                continue
            analysis, _ = analyze_complaint(db, complaint, admin.id)
            result = run_validation(db, complaint, analysis, admin.id)
            _log_pipeline_run(db, complaint, result)
            processed += 1
        db.commit()
        compared = sum(
            1 for case in cases
            if db.query(ValidationResult).filter(ValidationResult.complaint_id == case.complaint_id).first()
        )
        print({"unseen_target": target, "newly_processed": processed, "unseen_compared": compared, "minimum_required": 100})
        if compared < min(100, len(cases)):
            raise SystemExit("Unable to prepare the required unseen evaluation evidence")
    finally:
        db.close()


if __name__ == "__main__":
    main()
