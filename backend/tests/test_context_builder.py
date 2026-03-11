from datetime import datetime, timedelta, timezone

from app.models import MessageRecord
from app.services.context_builder import build_context


def _msg(role: str, content: str, minutes: int, priority: int = 10) -> MessageRecord:
    return MessageRecord(
        session_id="s1",
        role=role,
        content=content,
        risk_level="medium",
        priority=priority,
        created_at=datetime.now(timezone.utc) + timedelta(minutes=minutes),
    )


def test_context_builder_prioritizes_critical_information():
    messages = [
        _msg("user", "small talk only", 1, 1),
        _msg("user", "I am allergic to penicillin", 2, 1),
        _msg("user", "today symptoms got worse", 3, 1),
        _msg("assistant", "ack", 4, 1),
        _msg("user", "chest pain appeared", 5, 1),
    ]

    result = build_context("long summary", messages, turn_limit=3, max_chars=500)
    joined = " ".join(x["content"] for x in result.recent_messages)

    assert result.used_turns == 3
    assert "allergic" in joined
    assert "chest pain" in joined
