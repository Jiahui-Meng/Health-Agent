from app.services.safety import (
    classify_risk,
    enforce_intake_questioning,
    enforce_no_diagnosis_or_prescription,
    enforce_sex_consistency,
    max_risk,
)


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
        "advice_sections": {
            "medication_guidance": {
                "title": "Medication Guidance",
                "items": ["Take 500mg now"],
                "priority": "primary",
            }
        },
    }
    safe = enforce_no_diagnosis_or_prescription(answer, "en-US")
    assert safe["risk_level"] in {"medium", "high", "emergency"}
    assert "diagnosis" in safe["summary"].lower()
    assert safe["advice_sections"] is None


def test_max_risk():
    assert max_risk("high", "medium") == "high"
    assert max_risk("low", "emergency") == "emergency"


def test_intake_guard_rewrites_conclusion_like_content():
    answer = {
        "summary": "初步判断属于中风险，建议先观察。",
        "risk_level": "medium",
        "next_steps": ["继续观察"],
        "emergency_guidance": None,
        "disclaimer": "",
        "stage": "intake",
        "follow_up_questions": [],
    }
    safe = enforce_intake_questioning(answer, "zh-CN")
    assert safe["stage"] == "intake"
    assert safe["next_steps"] == []
    assert len(safe["follow_up_questions"]) >= 1
    assert "中风险" not in safe["summary"]


def test_sex_consistency_rewrites_male_intake_questions():
    answer = {
        "summary": "我想先确认一下末次月经和是否怀孕。",
        "risk_level": "medium",
        "next_steps": [],
        "emergency_guidance": None,
        "disclaimer": "",
        "stage": "intake",
        "follow_up_questions": ["最近一次月经是什么时候？", "有没有怀孕可能？"],
        "advice_sections": None,
    }
    safe = enforce_sex_consistency(answer, "zh-CN", "male")
    assert safe["stage"] == "intake"
    assert "月经" not in safe["summary"]
    assert all("月经" not in item and "怀孕" not in item for item in safe["follow_up_questions"])


def test_sex_consistency_rewrites_female_conclusion_advice():
    answer = {
        "summary": "建议同时评估前列腺相关问题。",
        "risk_level": "medium",
        "next_steps": ["如需可挂前列腺相关专科。"],
        "emergency_guidance": None,
        "disclaimer": "",
        "stage": "conclusion",
        "follow_up_questions": None,
        "advice_sections": {
            "visit_guidance": {
                "title": "就医建议",
                "items": ["可考虑前列腺专科门诊评估。", "必要时线下复诊。"],
                "priority": "primary",
            }
        },
    }
    safe = enforce_sex_consistency(answer, "zh-CN", "female")
    assert "前列腺" not in safe["summary"]
    assert all("前列腺" not in item for item in safe["next_steps"])
    assert all(
        "前列腺" not in item
        for item in safe["advice_sections"]["visit_guidance"]["items"]  # type: ignore[index]
    )
