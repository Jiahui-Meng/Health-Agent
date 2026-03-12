from app.services.advice_builder import advice_sections_to_next_steps, build_advice_sections


def test_build_advice_sections_for_respiratory_conclusion():
    answer = {
        "stage": "conclusion",
        "summary": "更像是上呼吸道感染样不适，建议先做对症处理并观察变化。",
        "risk_level": "medium",
        "next_steps": ["观察变化"],
    }
    sections = build_advice_sections(
        locale="zh-CN",
        message="我今天发烧、喉咙痛，还有点咳嗽",
        answer=answer,
        health_profile={"allergies": ["青霉素"]},
    )
    assert sections is not None
    assert "medication_guidance" in sections
    assert "rest_guidance" in sections
    assert "monitoring_guidance" in sections
    assert "visit_guidance" in sections
    assert any("对乙酰氨基酚" in item or "布洛芬" in item for item in sections["medication_guidance"]["items"])


def test_build_advice_sections_for_gastro_conclusion():
    answer = {
        "stage": "conclusion",
        "summary": "目前更像胃肠道刺激或感染相关不适。",
        "risk_level": "medium",
        "next_steps": ["补液观察"],
    }
    sections = build_advice_sections(
        locale="zh-CN",
        message="我腹泻、腹痛，还有点恶心",
        answer=answer,
        health_profile={},
    )
    assert sections is not None
    assert "diet_guidance" in sections
    assert "monitoring_guidance" in sections


def test_build_advice_sections_avoids_exercise_for_high_risk():
    answer = {
        "stage": "conclusion",
        "summary": "存在较高风险，建议尽快线下评估。",
        "risk_level": "high",
        "next_steps": ["尽快就医"],
    }
    sections = build_advice_sections(
        locale="en-US",
        message="I have high fever and breathing trouble",
        answer=answer,
        health_profile={},
    )
    assert sections is not None
    assert "visit_guidance" in sections
    assert "exercise_guidance" not in sections


def test_build_advice_sections_uses_pediatric_guardrails():
    answer = {
        "stage": "conclusion",
        "summary": "更像呼吸道感染样不适。",
        "risk_level": "medium",
        "next_steps": ["观察变化"],
    }
    sections = build_advice_sections(
        locale="zh-CN",
        message="孩子今天发烧咳嗽",
        answer=answer,
        health_profile={"age_range": "出生年份: 2016", "sex": "male"},
        region_code="HK",
    )
    assert sections is not None
    assert "exercise_guidance" not in sections
    assert "儿科" in " ".join(sections["visit_guidance"]["items"])
    assert any("监护人" in item for item in sections["monitoring_guidance"]["items"])


def test_build_advice_sections_uses_older_adult_guardrails():
    answer = {
        "stage": "conclusion",
        "summary": "目前需要更谨慎地观察变化。",
        "risk_level": "medium",
        "next_steps": ["记录变化"],
    }
    sections = build_advice_sections(
        locale="en-US",
        message="I have fever and weakness",
        answer=answer,
        health_profile={"age_range": "Birth year: 1948", "sex": "female"},
        region_code="US",
    )
    assert sections is not None
    assert any("lower threshold" in item.lower() for item in sections["visit_guidance"]["items"])
    assert any("older adults" in item.lower() or "mental status" in item.lower() for item in sections["monitoring_guidance"]["items"])


def test_build_advice_sections_emergency_uses_region_context():
    answer = {
        "stage": "conclusion",
        "summary": "存在急症风险。",
        "risk_level": "emergency",
        "next_steps": ["立即急诊"],
    }
    sections = build_advice_sections(
        locale="en-US",
        message="I have chest pain and shortness of breath",
        answer=answer,
        health_profile={"age_range": "Birth year: 1988", "sex": "male"},
        region_code="JP",
    )
    assert sections is not None
    assert any("119" in item for item in sections["visit_guidance"]["items"])
    assert any("不建议自行加用药物" in item or "Do not add self-directed medication" in item for item in sections["medication_guidance"]["items"])


def test_build_advice_sections_low_risk_explicitly_says_no_hospital_needed():
    answer = {
        "stage": "conclusion",
        "summary": "目前更像轻度上呼吸道不适。",
        "risk_level": "low",
        "next_steps": ["休息观察"],
    }
    sections = build_advice_sections(
        locale="zh-CN",
        message="我有点喉咙干，没有发烧，也没有明显加重",
        answer=answer,
        health_profile={"sex": "female"},
        region_code="HK",
    )
    assert sections is not None
    assert any("没有明确必须马上去医院" in item for item in sections["visit_guidance"]["items"])


def test_build_advice_sections_low_risk_can_explicitly_say_no_medication_needed():
    answer = {
        "stage": "conclusion",
        "summary": "目前更像轻度不适。",
        "risk_level": "low",
        "next_steps": ["观察变化"],
    }
    sections = build_advice_sections(
        locale="zh-CN",
        message="我只是有点累，想看看要不要处理",
        answer=answer,
        health_profile={"sex": "male"},
        region_code="HK",
    )
    assert sections is not None
    assert any("目前不一定需要吃药" in item for item in sections["medication_guidance"]["items"])


def test_advice_sections_to_next_steps_prefers_primary_sections():
    sections = {
        "visit_guidance": {"title": "Visit", "priority": "primary", "items": ["Book primary care", "Bring symptom log"]},
        "rest_guidance": {"title": "Rest", "priority": "secondary", "items": ["Sleep more"]},
    }
    steps = advice_sections_to_next_steps(sections, ["fallback"])
    assert steps[:2] == ["Book primary care", "Bring symptom log"]
