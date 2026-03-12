from __future__ import annotations

from collections import defaultdict
import json

from ..models import MessageRecord, SessionRecord, UserRecord


def build_export_context(
    *,
    user: UserRecord,
    sessions: list[SessionRecord],
    messages: list[MessageRecord],
    graph_summary: dict,
) -> dict:
    valid_session_ids = {session.id for session in sessions}
    messages_by_session: dict[str, list[dict[str, str]]] = defaultdict(list)
    for message in messages:
        if message.session_id not in valid_session_ids:
            continue
        messages_by_session[message.session_id].append(
            {
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at.isoformat() if message.created_at else "",
                "risk_level": message.risk_level or "",
            }
        )

    persistent = graph_summary.get("persistent_features") or {}
    recent_journey = [
        item
        for item in (graph_summary.get("recent_journey") or [])
        if not item.get("session_id") or item.get("session_id") in valid_session_ids
    ]
    risk_signals = [
        item
        for item in (graph_summary.get("risk_signals") or [])
        if not isinstance(item, dict) or not item.get("session_id") or item.get("session_id") in valid_session_ids
    ]
    summary_labels = [session.summary.strip() for session in sessions if (session.summary or "").strip()][:5]
    return {
        "user": {
            "username": user.username,
            "locale": user.locale,
            "region_code": user.region_code,
            "birth_year": user.birth_year or "",
            "sex": user.sex or "",
            "conditions": persistent.get("conditions") or [],
            "medications": persistent.get("medications") or [],
            "allergies": persistent.get("allergies") or [],
        },
        "graph_summary": {
            "recent_journey": recent_journey,
            "risk_signals": risk_signals,
            "summary_labels": summary_labels,
        },
        "sessions": [
            {
                "id": session.id,
                "updated_at": session.updated_at.isoformat() if session.updated_at else "",
                "latest_risk": session.latest_risk,
                "triage_stage": session.triage_stage,
                "summary": session.summary or "",
                "messages": messages_by_session.get(session.id, []),
            }
            for session in sessions
        ],
    }


def build_export_report_messages(locale: str, context: dict) -> list[dict[str, str]]:
    if locale.startswith("zh"):
        system = (
            "你是 Health Agent 的病例整理助手。"
            "请基于提供的用户资料、graph 摘要和问诊历史，生成一份面向人类阅读的 Markdown 报告正文。"
            "正文必须包含：用户概况、近期症状演化、关键风险变化、问诊历史总结、当前总体建议。"
            "不要捏造未提供的信息，不要输出 JSON，不要包含原始逐轮聊天附录。"
            "语言必须自然、清晰、通俗，适合作为个人健康记录摘要。"
        )
        user_prompt = (
            "请根据以下结构化上下文生成 Markdown 报告正文：\n"
            f"{json.dumps(context, ensure_ascii=False)}"
        )
    else:
        system = (
            "You are Health Agent's case-report assistant. "
            "Generate a human-readable Markdown report body from the provided user profile, graph summary, and chat history. "
            "The body must include: user overview, recent symptom progression, key risk changes, visit history summary, and current overall guidance. "
            "Do not invent facts, do not output JSON, and do not include the raw turn-by-turn appendix."
        )
        user_prompt = (
            "Generate a Markdown report body from this structured context:\n"
            f"{json.dumps(context, ensure_ascii=False)}"
        )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_prompt},
    ]


def compose_full_markdown_report(context: dict, report_body: str) -> str:
    sessions = context.get("sessions") or []
    lines = [report_body.strip(), "", "---", "", "## Raw Transcript Appendix", ""]
    if not sessions:
        lines.append("- No recorded sessions.")
        return "\n".join(lines).strip() + "\n"

    for session in sessions:
        lines.extend(
            [
                f"### Session {session.get('id')}",
                f"- Updated at: {session.get('updated_at') or '-'}",
                f"- Final stage: {session.get('triage_stage') or '-'}",
                f"- Latest risk: {session.get('latest_risk') or '-'}",
            ]
        )
        if session.get("summary"):
            lines.append(f"- Session summary: {session['summary']}")
        lines.append("")
        for message in session.get("messages") or []:
            role = "User" if message.get("role") == "user" else "Assistant"
            lines.append(f"**{role}:** {message.get('content') or ''}")
            lines.append("")
    return "\n".join(lines).strip() + "\n"
