from dataclasses import dataclass

from ..models import MessageRecord


@dataclass
class ContextBuildResult:
    summary: str
    recent_messages: list[dict[str, str]]
    used_turns: int


def _priority_score(message: MessageRecord) -> int:
    content = message.content.lower()
    score = message.priority
    if any(token in content for token in ["allerg", "过敏", "medication", "用药"]):
        score += 30
    if any(token in content for token in ["chest pain", "呼吸困难", "胸痛", "unconscious"]):
        score += 50
    if any(token in content for token in ["today", "今天", "worse", "加重", "new"]):
        score += 15
    return score


def build_context(
    session_summary: str,
    message_history: list[MessageRecord],
    turn_limit: int = 6,
    max_chars: int = 5000,
) -> ContextBuildResult:
    sorted_messages = sorted(message_history, key=_priority_score, reverse=True)
    picked: list[MessageRecord] = []
    char_count = len(session_summary)

    for message in sorted_messages:
        if len(picked) >= turn_limit:
            break
        if char_count + len(message.content) > max_chars:
            continue
        picked.append(message)
        char_count += len(message.content)

    picked = sorted(picked, key=lambda x: x.created_at)
    recent = [{"role": m.role, "content": m.content} for m in picked]

    return ContextBuildResult(summary=session_summary or "", recent_messages=recent, used_turns=len(recent))
