from __future__ import annotations

from .profile_guardrails import normalize_sex, sex_guardrails


def display_sex(value: str, locale: str) -> str:
    normalized = normalize_sex(value)
    if locale.startswith("zh"):
        return "男" if normalized == "male" else "女" if normalized == "female" else ""
    return normalized
