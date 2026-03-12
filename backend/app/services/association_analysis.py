from __future__ import annotations

import json
import re
from typing import Any

from ..models import MessageRecord, SessionRecord, UserRecord

ANALYSIS_EDGE_TYPE_MAP = {
    "possibly_related_to": "MODEL_POSSIBLY_RELATED_TO",
    "possibly_explained_by": "MODEL_POSSIBLY_EXPLAINED_BY",
    "possibly_recurrent_with": "MODEL_POSSIBLY_RECURRENT_WITH",
    "possibly_pattern_linked": "MODEL_POSSIBLY_PATTERN_LINKED",
}


def build_association_analysis_context(
    *,
    user: UserRecord,
    sessions: list[SessionRecord],
    messages: list[MessageRecord],
    graph_payload: dict[str, Any],
) -> dict[str, Any]:
    valid_session_ids = {session.id for session in sessions}
    valid_node_ids = {node["id"] for node in graph_payload["nodes"]}
    messages_by_session: dict[str, list[dict[str, str]]] = {session.id: [] for session in sessions}
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

    rule_associations = []
    for edge in graph_payload["edges"]:
        if edge["edge_type"].startswith("MODEL_"):
            continue
        if not edge["edge_type"].startswith("POSSIBLY_"):
            continue
        payload = edge.get("payload") or {}
        source_session_ids = [str(item) for item in payload.get("source_session_ids") or [] if str(item) in valid_session_ids]
        rule_associations.append(
            {
                "from_node_id": edge["from_node_id"],
                "to_node_id": edge["to_node_id"],
                "edge_type": edge["edge_type"],
                "confidence": payload.get("confidence") or "low",
                "evidence_type": payload.get("evidence_type") or "",
                "evidence_summary": payload.get("evidence_summary") or "",
                "source_session_ids": source_session_ids,
            }
        )

    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "locale": user.locale,
            "region_code": user.region_code,
            "birth_year": user.birth_year or "",
            "sex": user.sex or "",
            "conditions": (graph_payload.get("summary_bundle", {}).get("persistent_features", {}) or {}).get("conditions", []),
            "medications": (graph_payload.get("summary_bundle", {}).get("persistent_features", {}) or {}).get("medications", []),
            "allergies": (graph_payload.get("summary_bundle", {}).get("persistent_features", {}) or {}).get("allergies", []),
        },
        "graph": {
            "nodes": [
                {
                    "id": node["id"],
                    "node_type": node["node_type"],
                    "label": node["label"],
                    "payload": node.get("payload") or {},
                }
                for node in graph_payload["nodes"]
            ],
            "rule_associations": rule_associations,
            "summary_bundle": graph_payload.get("summary_bundle") or {},
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
        "allowed_refs": sorted(valid_node_ids),
        "allowed_session_ids": sorted(valid_session_ids),
    }


def build_association_analysis_messages(locale: str, context: dict[str, Any]) -> list[dict[str, str]]:
    if locale.startswith("zh"):
        system = (
            "你是 Health Agent 的关联性分析助手。"
            "请基于用户资料、graph、既有候选关联和完整问诊历史，输出一份严格 JSON 的关联性对照表。"
            "只能输出候选关联，不能输出诊断、处方或确定性因果。"
            "只能引用 allowed_refs 中存在的节点 id，source_session_ids 只能使用 allowed_session_ids 中的值。"
            "禁止捏造不存在的会话、节点或历史。"
            "返回格式必须是 JSON："
            '{"rows":[{"from_ref":"node_id","to_ref":"node_id","association_type":"possibly_related_to|possibly_explained_by|possibly_recurrent_with|possibly_pattern_linked","confidence":"low|medium|high","evidence_summary":"string","source_session_ids":["session_id"]}]}.'
        )
        user_prompt = "请分析以下上下文，并仅返回 JSON：\n" + json.dumps(context, ensure_ascii=False)
    else:
        system = (
            "You are Health Agent's association-analysis assistant. "
            "Use the user profile, graph, existing candidate associations, and full consultation history to produce a strict JSON association table. "
            "Only output candidate associations, never diagnoses, prescriptions, or certain causality. "
            "Only reference node ids in allowed_refs and session ids in allowed_session_ids. "
            "Do not invent nodes, sessions, or facts. "
            "Return JSON only with shape: "
            '{"rows":[{"from_ref":"node_id","to_ref":"node_id","association_type":"possibly_related_to|possibly_explained_by|possibly_recurrent_with|possibly_pattern_linked","confidence":"low|medium|high","evidence_summary":"string","source_session_ids":["session_id"]}]}.'
        )
        user_prompt = "Analyze this context and return JSON only:\n" + json.dumps(context, ensure_ascii=False)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_prompt},
    ]


def parse_association_analysis_rows(
    content: str,
    *,
    valid_node_ids: set[str],
    valid_session_ids: set[str],
) -> list[dict[str, Any]]:
    parsed = json.loads(_extract_json_object(content))
    rows = parsed.get("rows")
    if not isinstance(rows, list):
        raise ValueError("Association analysis response is missing rows.")

    clean_rows: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        from_ref = str(item.get("from_ref") or "").strip()
        to_ref = str(item.get("to_ref") or "").strip()
        association_type = str(item.get("association_type") or "").strip().lower()
        confidence = str(item.get("confidence") or "low").strip().lower()
        evidence_summary = str(item.get("evidence_summary") or "").strip()
        if from_ref not in valid_node_ids or to_ref not in valid_node_ids:
            continue
        if association_type not in ANALYSIS_EDGE_TYPE_MAP:
            continue
        if confidence not in {"low", "medium", "high"}:
            confidence = "low"
        source_session_ids = [
            str(session_id)
            for session_id in (item.get("source_session_ids") or [])
            if str(session_id) in valid_session_ids
        ]
        if not evidence_summary:
            continue
        clean_rows.append(
            {
                "from_ref": from_ref,
                "to_ref": to_ref,
                "association_type": association_type,
                "confidence": confidence,
                "evidence_summary": evidence_summary[:320],
                "source_session_ids": source_session_ids,
            }
        )
    return clean_rows


def _extract_json_object(text: str) -> str:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        return match.group(0)
    raise ValueError("No JSON object found in model response.")
