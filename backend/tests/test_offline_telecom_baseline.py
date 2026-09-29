from types import SimpleNamespace

from app.services.offline_analyzer import analyze


def make_complaint(description, product="Mobile Internet"):
    return SimpleNamespace(
        code="CMP-OFFLINE",
        title="PakSim service complaint",
        description=description,
        product_or_service=product,
        requested_resolution="Please resolve this issue.",
        translated_text="",
        order_reference="PKSIM-TEST-01",
        complaint_date=None,
    )


def test_offline_baseline_uses_paksim_categories():
    result = analyze(make_complaint("My mobile internet data is not working on 4G."))
    assert result["issue_category"] == "Mobile Internet"
    assert result["department"] == "Technical Support"
    assert result["policy_id"] == "NET-POL-02"


def test_offline_baseline_detects_security_escalation():
    result = analyze(make_complaint("I suspect an unauthorized SIM swap on my account.", "Fraud & Security"))
    assert result["issue_category"] == "Fraud & Security"
    assert result["urgency"] == "Critical"
    assert result["escalation_required"] is True
