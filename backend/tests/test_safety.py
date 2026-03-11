from app.services.safety import classify_risk, enforce_no_diagnosis_or_prescription, max_risk


def test_classify_risk_emergency_zh():
    result = classify_risk("我现在胸痛并且呼吸困难")
    assert result.risk_level == "emergency"
    assert "胸痛" in result.triggers


def test_classify_risk_high_en():
    result = classify_risk("I have high fever and severe headache")
    assert result.risk_level == "high"


def test_post_guard_rewrites_unsafe_answer():
    answer = {
        "summary": "You have influenza and take 500mg medicine.",
        "risk_level": "low",
        "next_steps": ["Take 500mg now"],
        "emergency_guidance": None,
        "disclaimer": "",
    }
    safe = enforce_no_diagnosis_or_prescription(answer, "en-US")
    assert safe["risk_level"] in {"medium", "high", "emergency"}
    assert "diagnosis" in safe["summary"].lower()


def test_max_risk():
    assert max_risk("high", "medium") == "high"
    assert max_risk("low", "emergency") == "emergency"
