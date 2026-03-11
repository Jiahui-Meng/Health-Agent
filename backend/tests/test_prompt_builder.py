import json

from app.schemas import HealthProfile
from app.services.prompt_builder import build_codex_mcp_prompt, build_system_prompt, build_user_prompt


def test_build_system_prompt_bilingual():
    zh_prompt = build_system_prompt("zh-CN", "intake")
    en_prompt = build_system_prompt("en-US", "conclusion")

    assert "JSON" in zh_prompt
    assert "no" in en_prompt.lower() and "prescription" in en_prompt.lower()
    assert "intake" in zh_prompt.lower()
    assert "conclusion" in en_prompt.lower()


def test_build_user_prompt_contains_profile_and_context():
    profile = HealthProfile(
        age_range="30-39",
        conditions=["asthma"],
        medications=["inhaler"],
        allergies=["penicillin"],
    )
    prompt = build_user_prompt(
        locale="en-US",
        message="I have cough for 3 days",
        profile=profile,
        long_summary="Recurring cough pattern",
        recent_messages=[{"role": "user", "content": "cough started on Monday"}],
        triage_stage="intake",
        triage_round_count=2,
        max_rounds=5,
        required_slots=["severity", "danger signs"],
    )

    data = json.loads(prompt)
    assert data["health_profile"]["conditions"] == ["asthma"]
    assert data["long_term_summary"] == "Recurring cough pattern"
    assert data["recent_messages"][0]["content"] == "cough started on Monday"
    assert data["triage_stage"] == "intake"
    assert data["triage_round_count"] == 2


def test_build_codex_mcp_prompt_contains_tool_instructions():
    prompt = build_codex_mcp_prompt(
        locale="en-US",
        session_id="session-1",
        device_id="device-1",
        message="I have a sore throat",
        triage_stage="intake",
        triage_round_count=2,
        max_rounds=5,
    )
    data = json.loads(prompt)
    assert data["session_id"] == "session-1"
    assert any("get_session_context" in rule for rule in data["rules"])
    assert data["triage_stage"] == "intake"
