from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AIAnalysis, Complaint, ComplaintHistory, ComplaintRule, ManualReview
from app.python_validation import contradiction_checker, policy_validator, resolution_validator
from app.python_validation.escalation_validator import validate as validate_escalation
from app.python_validation.validator import expected_from_rule, run_validation
from app.schemas import AIAnalysisContent
from app.services import offline_analyzer
from app.services.analysis_service import _without_internal_fields
from app.security import require_roles


def make_context(parsed, expected, policy_lookup=None):
    return SimpleNamespace(
        parsed=parsed,
        expected=expected,
        policy_lookup=policy_lookup or {},
        matched_rule=None,
        complaint=None,
        escalation_decision={},
        chunks=[],
        injection_detected=False,
        schema_valid=True,
    )


def test_expected_from_rule_preserves_action_and_follow_up_rules():
    rule = SimpleNamespace(
        category="Billing",
        subcategory="Duplicate charge",
        department="Billing Team",
        urgency="Low",
        priority="P3",
        escalation=False,
        escalation_reason="",
        escalation_department="",
        rule_id="BIL-001",
        policy_id="BIL-POL-05",
        required_actions=["verify transaction"],
        prohibited_actions=["promise full refund"],
        follow_up=True,
    )

    expected = expected_from_rule(rule)

    assert expected["required_actions"] == ["verify transaction"]
    assert expected["prohibited_actions"] == ["promise full refund"]
    assert expected["follow_up"] is True


def test_rule_mismatches_and_prohibited_resolution_are_failures():
    expected = {
        "category": "Billing",
        "subcategory": "Duplicate charge",
        "department": "Billing Team",
        "urgency": "Low",
        "priority": "P3",
        "escalation": False,
        "required_actions": ["verify transaction"],
        "prohibited_actions": ["promise full refund"],
    }
    parsed = {
        "issue_category": "Refund",
        "subcategory": "Duplicate charge",
        "department": "Billing Team",
        "urgency": "Low",
        "priority": "P0",
        "escalation": False,
        "resolution_steps": ["verify transaction"],
        "professional_response": "We promise full refund.",
    }
    context = make_context(parsed, expected)

    mismatch_names = {check.name for check in contradiction_checker.validate(context)}
    resolution_names = {check.name for check in resolution_validator.validate(context)}

    assert "category_match" in mismatch_names
    assert "priority_match" in mismatch_names
    assert "prohibited_action" in resolution_names
    assert "required_action" not in resolution_names


def test_policy_validation_rejects_unknown_policy_and_stale_version():
    parsed = {
        "policy_id": "BIL-POL-05",
        "policy_version": "v1",
        "policy_section": "4.1",
    }
    context = make_context(
        parsed,
        {"policy_id": "BIL-POL-05"},
        {"BIL-POL-05": {"version": "v2", "sections": ["4.1"]}},
    )

    checks = policy_validator.validate(context)

    assert any(check.name == "policy_version" and check.status == "FAIL" for check in checks)

    context.policy_lookup = {}
    checks = policy_validator.validate(context)
    assert any(check.name == "policy_reference" and check.status == "FAIL" for check in checks)


def test_reviewer_and_manager_role_dependency_rejects_customers():
    allow_review = require_roles("admin", "agent", "reviewer", "manager")
    allow_dashboard = require_roles("admin", "agent", "manager")

    assert allow_review(SimpleNamespace(role=SimpleNamespace(name="reviewer"))).role.name == "reviewer"
    assert allow_review(SimpleNamespace(role=SimpleNamespace(name="manager"))).role.name == "manager"
    assert allow_dashboard(SimpleNamespace(role=SimpleNamespace(name="manager"))).role.name == "manager"

    try:
        allow_dashboard(SimpleNamespace(role=SimpleNamespace(name="reviewer")))
    except HTTPException as error:
        assert error.status_code == 403
    else:
        raise AssertionError("Reviewer unexpectedly received manager dashboard access")

    try:
        allow_review(SimpleNamespace(role=SimpleNamespace(name="customer")))
    except HTTPException as error:
        assert error.status_code == 403
    else:
        raise AssertionError("Customer unexpectedly received review access")


def test_escalation_validator_does_not_treat_false_string_as_true():
    context = make_context({"escalation_required": "false"}, {"escalation": False})
    context.escalation_decision = {"required": False, "triggers": []}

    assert validate_escalation(context) == []

    context.escalation_decision = {"required": True, "triggers": ["safety_issue"]}
    checks = validate_escalation(context)
    assert checks[0].status == "FAIL"


def test_offline_analysis_meets_strict_schema_and_unknown_fields_fail():
    complaint = SimpleNamespace(
        code="CMP-00001",
        title="Delayed delivery",
        description="My delivery is late.",
        product_or_service="",
        requested_resolution="",
        translated_text="",
        order_reference="",
        complaint_date=None,
    )
    parsed = offline_analyzer.analyze(complaint)
    validated = AIAnalysisContent.model_validate(_without_internal_fields(parsed))

    assert validated.complaint_id == "CMP-00001"

    incomplete = dict(parsed)
    incomplete.pop("compensation_eligibility")
    incomplete.pop("_provider_label")
    incomplete.pop("_category_scores")
    try:
        AIAnalysisContent.model_validate(incomplete)
    except ValueError:
        pass
    else:
        raise AssertionError("Missing critical field unexpectedly passed schema validation")

    with_unknown = dict(parsed, fabricated_decision="approve refund")
    try:
        AIAnalysisContent.model_validate(with_unknown)
    except ValueError:
        pass
    else:
        raise AssertionError("Unknown output key unexpectedly passed schema validation")


def test_validation_mismatch_opens_review_and_records_lifecycle_history():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as db:
        complaint = Complaint(
            code="CMP-VAL-1",
            title="Duplicate charge",
            description="I was billed twice for my monthly plan.",
            status="ANALYZED",
        )
        db.add(complaint)
        db.flush()
        db.add(ComplaintRule(
            rule_id="BIL-TEST-1",
            category="Billing",
            subcategory="Duplicate charge",
            keywords=["billed twice"],
            department="Billing Team",
            urgency="Low",
            priority="P3",
            escalation=False,
            required_actions=[],
            prohibited_actions=[],
            follow_up=True,
        ))
        analysis = AIAnalysis(
            complaint_id=complaint.id,
            parsed={
                "issue_category": "Refund",
                "subcategory": "Duplicate charge",
                "department": "Billing Team",
                "urgency": "Low",
                "priority": "P3",
                "escalation": False,
                "professional_response": "We will review the duplicate charge.",
            },
            is_valid_schema=True,
        )
        db.add(analysis)
        db.flush()

        result = run_validation(db, complaint, analysis)

        review = db.query(ManualReview).filter_by(complaint_id=complaint.id, status="OPEN").one()
        history = db.query(ComplaintHistory).filter_by(complaint_id=complaint.id).one()
        assert result.status == "MISMATCH"
        assert complaint.status == "MANUAL_REVIEW"
        assert review.source == "validation"
        assert "category" in review.reason.casefold()
        assert history.from_status == "ANALYZED"
        assert history.to_status == "MANUAL_REVIEW"

    engine.dispose()


def test_safety_trigger_overrides_non_escalating_rule():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as db:
        complaint = Complaint(
            code="CMP-SAFE-1",
            title="Device emits smoke",
            description="Smoke is coming from the device and it feels hot.",
            status="ANALYZED",
        )
        db.add(complaint)
        db.flush()
        db.add(ComplaintRule(
            rule_id="SAF-TEST-1",
            category="Safety",
            subcategory="Overheating",
            keywords=["smoke"],
            department="Quality & Safety",
            urgency="High",
            priority="P2",
            escalation=False,
            required_actions=[],
            prohibited_actions=[],
            follow_up=True,
        ))
        analysis = AIAnalysis(
            complaint_id=complaint.id,
            parsed={
                "issue_category": "Safety",
                "subcategory": "Overheating",
                "department": "Quality & Safety",
                "urgency": "High",
                "priority": "P2",
                "escalation_required": False,
                "professional_response": "Please stop using the device.",
            },
            is_valid_schema=True,
        )
        db.add(analysis)
        db.flush()

        result = run_validation(db, complaint, analysis)

        assert result.status == "MISMATCH"
        assert complaint.verified_escalation is True
        assert any(check.check_name == "escalation" for check in result.checks)
        assert db.query(ManualReview).filter_by(complaint_id=complaint.id, status="OPEN").count() == 1

    engine.dispose()