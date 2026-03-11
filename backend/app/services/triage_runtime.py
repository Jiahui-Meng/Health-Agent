from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import MessageRecord, SessionRecord
from .context_builder import build_context
from .graph_service import get_graph_bundle
from .safety import classify_risk

MIN_TRIAGE_ROUNDS = 3
MAX_TRIAGE_ROUNDS = 5


@dataclass
class SessionContextResult:
    session_id: str
    device_id: str
    locale: str
    region_code: str
    summary: str
    health_profile: dict
    triage_stage: str
    triage_round_count: int
    recent_messages: list[dict[str, str]]
    used_turns: int
    graph_context: dict


def choose_forced_stage(current_stage: str, next_round: int) -> str | None:
    if current_stage == "conclusion":
        return "conclusion"
    if next_round < MIN_TRIAGE_ROUNDS:
        return "intake"
    if next_round >= MAX_TRIAGE_ROUNDS:
        return "conclusion"
    return None


def apply_stage_rules(answer: dict, locale: str, round_count: int) -> dict:
    stage = answer.get("stage") or "conclusion"

    if round_count < MIN_TRIAGE_ROUNDS:
        stage = "intake"
    elif round_count >= MAX_TRIAGE_ROUNDS and stage == "intake":
        stage = "conclusion"
        if locale.startswith("zh"):
            answer["summary"] = "已完成多轮线上问诊，信息仍不足以安全判断，建议尽快线下就医评估。"
            answer["next_steps"] = [
                "请尽快到线下门诊或急诊就医，由医生完成查体和必要检查。",
                "携带症状变化记录（起病时间、体温、疼痛程度、诱因和缓解因素）。",
            ]
        else:
            answer["summary"] = "After multiple online triage rounds, available information is still insufficient for a safe conclusion."
            answer["next_steps"] = [
                "Arrange in-person medical evaluation promptly for physical examination and testing.",
                "Bring a short symptom log (onset, severity trend, triggers, and relieving factors).",
            ]

    answer["stage"] = stage
    if stage == "intake":
        follow_ups = answer.get("follow_up_questions") or []
        answer["follow_up_questions"] = [str(q).strip() for q in follow_ups if str(q).strip()][:3]
        answer["next_steps"] = []
    else:
        answer["follow_up_questions"] = None
    return answer


def build_required_slots(
    locale: str,
    current_message: str,
    health_profile: dict,
    recent_messages: list[dict[str, str]],
) -> list[str]:
    text_pool = [current_message]
    for msg in recent_messages:
        if msg.get("role") == "user":
            text_pool.append(msg.get("content", ""))
    text_blob = " ".join(text_pool).lower()
    has_history = bool(health_profile.get("conditions") or health_profile.get("medications") or health_profile.get("allergies"))

    slots: list[tuple[str, bool]] = [
        ("symptom_site", bool(re.search(r"(喉|咽|胸|腹|头|胃|背|arm|chest|throat|abdomen|head|stomach|back)", text_blob))),
        ("severity", bool(re.search(r"(严重|剧烈|轻微|中等|分|pain scale|severe|mild|moderate|\\d+/10)", text_blob))),
        (
            "onset_time",
            bool(
                re.search(
                    r"(今天|昨天|今早|昨晚|天前|周前|月前|小时|分钟|day|days|week|weeks|month|months|hour|hours|since)",
                    text_blob,
                )
            ),
        ),
        ("associated_symptoms", bool(re.search(r"(伴|同时|还有|并且|with|also|together)", text_blob))),
        ("red_flags", bool(re.search(r"(胸痛|呼吸困难|晕厥|抽搐|便血|chest pain|breathing|faint|seizure|blood)", text_blob))),
        ("relevant_history", has_history),
    ]

    mapping_zh = {
        "symptom_site": "症状部位",
        "severity": "严重程度",
        "onset_time": "起病时间",
        "associated_symptoms": "伴随症状",
        "red_flags": "危险信号",
        "relevant_history": "既往史相关信息",
    }
    mapping_en = {
        "symptom_site": "symptom location",
        "severity": "severity",
        "onset_time": "onset timing",
        "associated_symptoms": "associated symptoms",
        "red_flags": "danger signs",
        "relevant_history": "relevant medical history",
    }
    mapping = mapping_zh if locale.startswith("zh") else mapping_en

    missing = [mapping[key] for key, filled in slots if not filled]
    return missing[:4]


def build_session_context(
    db: Session,
    settings: Settings,
    session_id: str,
    device_id: str,
    locale: str,
) -> SessionContextResult:
    session_record = db.get(SessionRecord, session_id)
    if not session_record or session_record.device_id != device_id:
        raise ValueError("Session not found for device")

    history = (
        db.execute(
            select(MessageRecord)
            .where(MessageRecord.session_id == session_record.id)
            .order_by(desc(MessageRecord.created_at))
            .limit(40)
        )
        .scalars()
        .all()
    )
    context = build_context(
        session_summary=session_record.summary,
        message_history=history,
        turn_limit=settings.context_turn_limit,
        max_chars=settings.max_context_chars,
    )
    return SessionContextResult(
        session_id=session_record.id,
        device_id=session_record.device_id,
        locale=locale or session_record.locale,
        region_code=session_record.region_code,
        summary=context.summary,
        health_profile=session_record.health_profile or {},
        triage_stage=session_record.triage_stage or "intake",
        triage_round_count=session_record.triage_round_count or 0,
        recent_messages=context.recent_messages,
        used_turns=context.used_turns,
        graph_context=get_graph_bundle(db, session_record.user_id, session_record.id).__dict__ if session_record.user_id else {},
    )


def analyze_health_input(
    *,
    locale: str,
    message: str,
    health_profile: dict,
    recent_messages: list[dict[str, str]],
) -> dict:
    normalized_recent_messages: list[dict[str, str]] = []
    for item in recent_messages:
        if isinstance(item, dict):
            role = str(item.get("role") or "user")
            content = str(item.get("content") or "")
            normalized_recent_messages.append({"role": role, "content": content})
        elif isinstance(item, str):
            normalized_recent_messages.append({"role": "user", "content": item})

    risk = classify_risk(message)
    required_slots = build_required_slots(
        locale=locale,
        current_message=message,
        health_profile=health_profile,
        recent_messages=normalized_recent_messages,
    )
    return {
        "risk_level": risk.risk_level,
        "triggers": risk.triggers,
        "required_slots": required_slots,
        "should_emergency_redirect": risk.risk_level == "emergency",
    }


def build_health_response_plan(
    *,
    locale: str,
    current_stage: str,
    current_round_count: int,
    required_slots: list[str],
    risk_level: str,
) -> dict:
    next_round = current_round_count + 1
    target_stage = choose_forced_stage(current_stage, next_round) or current_stage
    if target_stage == "intake":
        if locale.startswith("zh"):
            instruction = "继续医生式问诊，只提 1-3 个最关键的追问，不下结论。"
        else:
            instruction = "Continue doctor-style intake. Ask only 1-3 highest-value follow-up questions and do not conclude yet."
    else:
        if locale.startswith("zh"):
            instruction = "给出安全、简洁的总结和下一步建议；若信息仍不足，明确建议线下就医评估。"
        else:
            instruction = "Provide a safe concise conclusion and next steps; if information is still insufficient, explicitly recommend in-person evaluation."
    return {
        "stage": target_stage,
        "next_round_count": next_round,
        "risk_level": risk_level,
        "required_slots": required_slots,
        "instruction": instruction,
    }


def preview_persist_chat_turn(*, session_id: str, stage: str, risk_level: str) -> dict:
    return {
        "session_id": session_id,
        "stage": stage,
        "risk_level": risk_level,
        "persisted": False,
        "message": "Host application persists the authoritative chat turn after schema validation.",
    }
