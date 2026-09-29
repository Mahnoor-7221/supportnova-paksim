from app.nova.intent_classifier import classify


def test_recharge_message_is_specific():
    result = classify("Recharge ke baad balance show nahi ho raha")
    assert result["id"] == "balance_recharge_issue"
    assert "recharge amount" in result["answer"].lower()
    assert "24–48" not in result["answer"]


def test_recharge_clarification_keeps_topic():
    result = classify("samajh nahi aaya", previous_category="balance_recharge_issue")
    assert result["id"] == "balance_recharge_issue"
    assert result.get("follow_up") is True
    assert result.get("simplify") is True


def test_common_intents_are_not_collapsed_into_generic_support():
    cases = {
        "new sim chahiye ghar par": "new_sim_purchase",
        "sim replace karni hai": "sim_replacement_port",
        "sim activate nahi hui": "sim_activation",
        "package lena hai": "package_purchase",
        "package activate nahi hua": "package_issue",
        "balance kaise check karun": "balance_check",
        "internet nahi chal raha": "no_internet_data",
        "sim kho gai hai": "sim_stolen_snatched",
        "complaint status batao": "check_complaint_status",
    }
    for question, expected in cases.items():
        result = classify(question)
        assert result["id"] == expected, (question, result["id"], expected)


def test_package_purchase_does_not_get_classified_as_package_failure():
    result = classify("package activate karna hai")
    assert result["id"] == "package_purchase"
    assert "payment" in result["answer"].lower()


def test_recharge_clarification_is_short_and_stays_on_topic():
    result = classify("mujhay abhi bhi samajh nhi aaya", previous_category="balance_recharge_issue")
    assert result["id"] == "balance_recharge_issue"
    assert result.get("simplify") is True
    assert "recharge" in result["answer"].lower()
    assert "sim" not in result["answer"].lower().replace("simple", "")
