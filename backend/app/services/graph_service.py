from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import re
from typing import Any, Callable

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from ..models import MessageRecord, SessionRecord, UserGraphEdgeRecord, UserGraphNodeRecord, UserRecord
from .association_builder import prune_invalid_association_edges, rebuild_association_edges

PERSISTENT_NODE_TYPES = {
    "condition": "HAS_CONDITION",
    "medication": "USES_MEDICATION",
    "allergy": "HAS_ALLERGY",
}

SYMPTOM_PATTERNS = [
    ("发烧", r"发烧|发热|fever"),
    ("咳嗽", r"咳嗽|cough"),
    ("喉咙痛", r"喉咙痛|咽痛|sore throat|throat pain"),
    ("胸痛", r"胸痛|chest pain"),
    ("呼吸困难", r"呼吸困难|气短|shortness of breath|breathing trouble"),
    ("头痛", r"头痛|headache"),
    ("腹痛", r"腹痛|肚子痛|肚子.*疼|abdominal pain|stomach pain"),
    ("流鼻涕", r"流鼻涕|鼻塞|runny nose|nasal congestion"),
    ("恶心", r"恶心|nausea"),
    ("呕吐", r"呕吐|vomit|vomiting"),
    ("腹泻", r"腹泻|拉肚子|diarrhea"),
    ("乏力", r"乏力|疲劳|fatigue|tired"),
    ("头晕", r"头晕|眩晕|dizzy|dizziness"),
    ("皮疹", r"皮疹|rash"),
]

TIMELINE_PATTERNS = [
    ("今天", r"今天|today"),
    ("昨天", r"昨天|yesterday"),
    ("今晚", r"今晚|夜里|tonight"),
    ("今早", r"今早|今天早上|this morning"),
    ("持续", r"持续|仍然|一直|for \d+"),
    ("加重", r"加重|更严重|worse|worsening"),
    ("突然", r"突然|sudden|suddenly"),
    ("反复", r"反复|recurrent|comes and goes"),
    ("缓解", r"缓解|好转|improving|better"),
    ("近几天", r"这两天|这几天|recent days|past few days"),
]


@dataclass
class GraphContextBundle:
    persistent_features: dict[str, list[str]]
    profile_highlights: list[str]
    recent_timeline: list[dict[str, Any]]
    recent_journey: list[dict[str, Any]]
    risk_signals: list[dict[str, Any]]
    summary_labels: list[str]


def create_or_update_user(
    db: Session,
    *,
    username: str,
    locale: str,
    region_code: str,
    birth_year: str,
    sex: str,
    conditions: list[str],
    medications: list[str],
    allergies: list[str],
    user: UserRecord | None = None,
    mark_active: bool = True,
) -> UserRecord:
    now = datetime.utcnow()
    if user is None:
        user = UserRecord(
            username=username,
            locale=locale,
            region_code=region_code,
            birth_year=birth_year,
            sex=sex,
            last_active_at=now,
        )
        db.add(user)
        db.flush()
    else:
        user.username = username
        user.locale = locale
        user.region_code = region_code
        user.birth_year = birth_year
        user.sex = sex
        if mark_active:
            user.last_active_at = now
        db.add(user)
        db.flush()

    root_node = _ensure_user_root_node(db, user)
    _replace_persistent_feature_nodes(db, user.id, root_node.id, "condition", conditions, source="profile")
    _replace_persistent_feature_nodes(db, user.id, root_node.id, "medication", medications, source="profile")
    _replace_persistent_feature_nodes(db, user.id, root_node.id, "allergy", allergies, source="profile")
    return user


def mark_user_active(db: Session, user: UserRecord) -> UserRecord:
    user.last_active_at = datetime.utcnow()
    db.add(user)
    db.flush()
    return user


def get_graph_bundle(db: Session, user_id: str, current_session_id: str | None = None) -> GraphContextBundle:
    reconcile_user_graph_from_sessions(db, user_id)
    user = db.get(UserRecord, user_id)
    sessions_by_recency = (
        db.execute(
            select(SessionRecord)
            .where(SessionRecord.user_id == user_id)
            .order_by(SessionRecord.updated_at.desc(), SessionRecord.created_at.desc())
        )
        .scalars()
        .all()
    )
    session_ids_by_recency = [session.id for session in sessions_by_recency]
    nodes = (
        db.execute(
            select(UserGraphNodeRecord)
            .where(UserGraphNodeRecord.user_id == user_id)
            .order_by(UserGraphNodeRecord.updated_at.desc(), UserGraphNodeRecord.created_at.desc())
        )
        .scalars()
        .all()
    )
    nodes = _filter_nodes_for_existing_sessions(nodes, set(session_ids_by_recency))
    persistent_features = {
        "conditions": [node.label for node in nodes if node.node_type == "condition"],
        "medications": [node.label for node in nodes if node.node_type == "medication"],
        "allergies": [node.label for node in nodes if node.node_type == "allergy"],
    }
    timeline_nodes = [node for node in nodes if node.node_type in {"symptom_event", "timeline_marker"}]
    recent_timeline = [
        {"node_type": node.node_type, "label": node.label, "payload": node.payload or {}}
        for node in timeline_nodes[:10]
    ]
    effective_session_id = current_session_id or (session_ids_by_recency[0] if session_ids_by_recency else None)
    fallback_journey = _build_session_fallback_cards(db, sessions_by_recency)
    recent_journey = _build_recent_journey(nodes, effective_session_id, session_ids_by_recency, fallback_journey)
    risk_signals = _build_risk_signal_summary(nodes, effective_session_id, session_ids_by_recency)
    summary_labels = [node.label for node in nodes if node.node_type == "summary"][:5]

    if current_session_id:
        recent_timeline = [
            item for item in recent_timeline if str((item.get("payload") or {}).get("session_id") or "") in {"", current_session_id}
        ] or recent_timeline[:10]

    return GraphContextBundle(
        persistent_features=persistent_features,
        profile_highlights=_build_profile_highlights(user),
        recent_timeline=recent_timeline,
        recent_journey=recent_journey,
        risk_signals=risk_signals,
        summary_labels=summary_labels,
    )


def get_graph_payload(db: Session, user_id: str) -> dict[str, Any]:
    reconcile_user_graph_from_sessions(db, user_id)
    session_ids = {
        session.id
        for session in (
            db.execute(select(SessionRecord).where(SessionRecord.user_id == user_id))
            .scalars()
            .all()
        )
    }
    nodes = (
        db.execute(
            select(UserGraphNodeRecord)
            .where(UserGraphNodeRecord.user_id == user_id)
            .order_by(UserGraphNodeRecord.created_at.asc())
        )
        .scalars()
        .all()
    )
    nodes = _filter_nodes_for_existing_sessions(nodes, session_ids)
    valid_node_ids = {node.id for node in nodes}
    edges = (
        db.execute(
            select(UserGraphEdgeRecord)
            .where(UserGraphEdgeRecord.user_id == user_id)
            .order_by(UserGraphEdgeRecord.created_at.asc())
        )
        .scalars()
        .all()
    )
    prune_invalid_association_edges(db, user_id, valid_node_ids, session_ids)
    edges = (
        db.execute(
            select(UserGraphEdgeRecord)
            .where(UserGraphEdgeRecord.user_id == user_id)
            .order_by(UserGraphEdgeRecord.created_at.asc())
        )
        .scalars()
        .all()
    )
    edges = [edge for edge in edges if edge.from_node_id in valid_node_ids and edge.to_node_id in valid_node_ids]
    bundle = get_graph_bundle(db, user_id)
    return {
        "nodes": [
            {
                "id": node.id,
                "node_type": node.node_type,
                "label": node.label,
                "payload": node.payload or {},
                "source": node.source,
                "created_at": node.created_at,
                "updated_at": node.updated_at,
            }
            for node in nodes
        ],
        "edges": [
            {
                "id": edge.id,
                "from_node_id": edge.from_node_id,
                "to_node_id": edge.to_node_id,
                "edge_type": edge.edge_type,
                "payload": edge.payload or {},
                "created_at": edge.created_at,
            }
            for edge in edges
        ],
        "summary_bundle": {
            "persistent_features": bundle.persistent_features,
            "profile_highlights": bundle.profile_highlights,
            "recent_timeline": bundle.recent_timeline,
            "recent_journey": bundle.recent_journey,
            "risk_signals": bundle.risk_signals,
            "summary_labels": bundle.summary_labels,
        },
    }


def upsert_session_graph(
    db: Session,
    *,
    user: UserRecord,
    session_record: SessionRecord,
    user_message: str,
    answer: dict,
    locale: str,
    risk_triggers: list[str],
) -> None:
    root_node = _ensure_user_root_node(db, user)
    session_node = _ensure_session_node(db, user.id, session_record.id)
    _ensure_edge(db, user.id, root_node.id, session_node.id, "HAS_SESSION")

    symptom_labels = _extract_labels(user_message, SYMPTOM_PATTERNS)
    for label in symptom_labels:
        symptom_node = _get_or_create_node(db, user.id, "symptom", label, {"locale": locale}, source="extracted")
        _ensure_edge(db, user.id, session_node.id, symptom_node.id, "REPORTED_SYMPTOM")

        event_node = _get_or_create_node(
            db,
            user.id,
            "symptom_event",
            f"{label}:{user_message[:80]}",
            {"session_id": session_record.id, "message": user_message, "locale": locale},
            source="chat",
        )
        _ensure_edge(db, user.id, symptom_node.id, event_node.id, "EVOLVED_TO")
        _ensure_edge(db, user.id, session_node.id, event_node.id, "REPORTED_SYMPTOM")

    for label in _extract_labels(user_message, TIMELINE_PATTERNS):
        marker_node = _get_or_create_node(
            db,
            user.id,
            "timeline_marker",
            label,
            {"session_id": session_record.id, "message": user_message},
            source="chat",
        )
        _ensure_edge(db, user.id, session_node.id, marker_node.id, "OCCURRED_AT")

    if answer.get("stage") == "conclusion":
        risk_labels = list(dict.fromkeys(risk_triggers))
        summary_label = str(answer.get("summary") or "").strip()
        if summary_label:
            risk_labels.append(summary_label[:120])
        if str(answer.get("risk_level") or "") not in risk_labels:
            risk_labels.append(str(answer.get("risk_level") or "medium"))
        for label in risk_labels:
            risk_node = _get_or_create_node(
                db,
                user.id,
                "risk_signal",
                label,
                {"session_id": session_record.id, "risk_level": answer.get("risk_level")},
                source="chat",
            )
            _ensure_edge(db, user.id, session_node.id, risk_node.id, "HAS_RISK_SIGNAL")

    summary = str(answer.get("summary") or "").strip()
    if summary:
        summary_node = _get_or_create_node(
            db,
            user.id,
            "summary",
            summary[:255],
            {"session_id": session_record.id, "stage": answer.get("stage"), "risk_level": answer.get("risk_level")},
            source="summary",
        )
        _ensure_edge(db, user.id, session_node.id, summary_node.id, "SUMMARIZED_AS")


def reconcile_user_graph_from_sessions(
    db: Session,
    user_id: str,
    *,
    association_enhancer: Callable[[str], str] | None = None,
) -> None:
    user = db.get(UserRecord, user_id)
    if not user:
        return

    root_node = _ensure_user_root_node(db, user)
    sessions = (
        db.execute(select(SessionRecord).where(SessionRecord.user_id == user_id).order_by(SessionRecord.created_at.asc()))
        .scalars()
        .all()
    )
    for session in sessions:
        rebuild_session_graph_from_history(db, user_id, session.id, root_node_id=root_node.id)
    _prune_orphan_symptom_nodes(db, user_id)
    rebuild_association_edges(
        db,
        user_id,
        locale=user.locale,
        current_session_id=sessions[-1].id if sessions else None,
        enhancer=association_enhancer,
    )
    db.flush()


def rebuild_session_graph_from_history(db: Session, user_id: str, session_id: str, *, root_node_id: str | None = None) -> None:
    session = db.get(SessionRecord, session_id)
    if not session or session.user_id != user_id:
        return

    _delete_session_derived_nodes(db, user_id, session_id)
    root_node = (
        db.execute(
            select(UserGraphNodeRecord).where(
                UserGraphNodeRecord.user_id == user_id,
                UserGraphNodeRecord.node_type == "user",
            )
        )
        .scalars()
        .first()
        if root_node_id is None
        else None
    )
    if root_node_id is None:
        if not root_node:
            user = db.get(UserRecord, user_id)
            if not user:
                return
            root_node = _ensure_user_root_node(db, user)
        root_node_id = root_node.id

    session_node = _ensure_session_node(db, user_id, session_id)
    _ensure_edge(db, user_id, root_node_id, session_node.id, "HAS_SESSION")

    messages = (
        db.execute(
            select(MessageRecord)
            .where(MessageRecord.session_id == session_id)
            .order_by(MessageRecord.created_at.asc(), MessageRecord.id.asc())
        )
        .scalars()
        .all()
    )

    latest_user_message = ""
    latest_conclusion: dict[str, Any] | None = None
    risk_triggers: list[str] = []

    for message in messages:
        if message.role == "user":
            latest_user_message = message.content
            _materialize_user_message_nodes(
                db,
                user_id=user_id,
                session_id=session_id,
                session_node_id=session_node.id,
                locale=session.locale,
                text=message.content,
            )
        elif message.role == "assistant":
            parsed = _parse_assistant_json(message.content)
            if not parsed:
                continue
            if str(parsed.get("stage") or "") == "conclusion":
                latest_conclusion = parsed
                risk_triggers = _extract_readable_risk_labels(parsed)
                _materialize_assistant_summary_nodes(
                    db,
                    user_id=user_id,
                    session_id=session_id,
                    session_node_id=session_node.id,
                    text=" ".join(
                        [
                            str(parsed.get("summary") or ""),
                            " ".join(str(item) for item in (parsed.get("next_steps") or [])),
                        ]
                    ).strip(),
                )

    if latest_conclusion:
        risk_level = str(latest_conclusion.get("risk_level") or session.latest_risk or "medium")
        labels = risk_triggers or [str(latest_conclusion.get("summary") or "").strip()[:120] or risk_level]
        for label in labels[:2]:
            risk_node = _get_or_create_node(
                db,
                user_id,
                "risk_signal",
                label,
                {"session_id": session_id, "risk_level": risk_level},
                source="summary",
            )
            _ensure_edge(db, user_id, session_node.id, risk_node.id, "HAS_RISK_SIGNAL")

        summary = str(latest_conclusion.get("summary") or "").strip() or session.summary.strip() or latest_user_message[:120]
        if summary:
            summary_node = _get_or_create_node(
                db,
                user_id,
                "summary",
                summary[:255],
                {"session_id": session_id, "stage": "conclusion", "risk_level": risk_level},
                source="summary",
            )
            _ensure_edge(db, user_id, session_node.id, summary_node.id, "SUMMARIZED_AS")
    elif session.summary.strip():
        summary_node = _get_or_create_node(
            db,
            user_id,
            "summary",
            session.summary.strip()[:255],
            {"session_id": session_id, "stage": session.triage_stage or "intake", "risk_level": session.latest_risk or "low"},
            source="summary",
        )
        _ensure_edge(db, user_id, session_node.id, summary_node.id, "SUMMARIZED_AS")


def _delete_session_derived_nodes(db: Session, user_id: str, session_id: str) -> None:
    nodes = (
        db.execute(select(UserGraphNodeRecord).where(UserGraphNodeRecord.user_id == user_id))
        .scalars()
        .all()
    )
    removable_ids = {
        node.id
        for node in nodes
        if node.node_type != "session" and str((node.payload or {}).get("session_id") or "") == session_id
    }
    if not removable_ids:
        return
    db.execute(
        delete(UserGraphEdgeRecord).where(
            UserGraphEdgeRecord.user_id == user_id,
            (UserGraphEdgeRecord.from_node_id.in_(removable_ids)) | (UserGraphEdgeRecord.to_node_id.in_(removable_ids)),
        )
    )
    db.execute(delete(UserGraphNodeRecord).where(UserGraphNodeRecord.id.in_(removable_ids)))
    db.flush()


def delete_session_graph_subtree(db: Session, user_id: str, session_id: str) -> None:
    nodes = (
        db.execute(
            select(UserGraphNodeRecord).where(UserGraphNodeRecord.user_id == user_id)
        )
        .scalars()
        .all()
    )
    removable_ids = {
        node.id
        for node in nodes
        if (
            node.node_type == "session"
            and node.label == session_id
        )
        or str((node.payload or {}).get("session_id") or "") == session_id
    }
    if removable_ids:
        db.execute(
            delete(UserGraphEdgeRecord).where(
                UserGraphEdgeRecord.user_id == user_id,
                (UserGraphEdgeRecord.from_node_id.in_(removable_ids)) | (UserGraphEdgeRecord.to_node_id.in_(removable_ids)),
            )
        )
        db.execute(delete(UserGraphNodeRecord).where(UserGraphNodeRecord.id.in_(removable_ids)))
        db.flush()
    _prune_orphan_symptom_nodes(db, user_id)
    user = db.get(UserRecord, user_id)
    if user:
        rebuild_association_edges(db, user_id, locale=user.locale)


def _ensure_user_root_node(db: Session, user: UserRecord) -> UserGraphNodeRecord:
    existing = (
        db.execute(
            select(UserGraphNodeRecord).where(
                UserGraphNodeRecord.user_id == user.id,
                UserGraphNodeRecord.node_type == "user",
            )
        )
        .scalars()
        .first()
    )
    if existing:
        existing.label = user.username
        existing.payload = {
            "locale": user.locale,
            "region_code": user.region_code,
            "birth_year": user.birth_year,
            "sex": user.sex,
        }
        db.add(existing)
        db.flush()
        return existing

    node = UserGraphNodeRecord(
        user_id=user.id,
        node_type="user",
        label=user.username,
        payload={
            "locale": user.locale,
            "region_code": user.region_code,
            "birth_year": user.birth_year,
            "sex": user.sex,
        },
        source="profile",
    )
    db.add(node)
    db.flush()
    return node


def _replace_persistent_feature_nodes(
    db: Session,
    user_id: str,
    root_node_id: str,
    node_type: str,
    values: list[str],
    *,
    source: str,
) -> None:
    old_nodes = (
        db.execute(
            select(UserGraphNodeRecord).where(
                UserGraphNodeRecord.user_id == user_id,
                UserGraphNodeRecord.node_type == node_type,
                UserGraphNodeRecord.source == source,
            )
        )
        .scalars()
        .all()
    )
    old_ids = [node.id for node in old_nodes]
    if old_ids:
        db.execute(
            delete(UserGraphEdgeRecord).where(
                UserGraphEdgeRecord.user_id == user_id,
                (UserGraphEdgeRecord.from_node_id.in_(old_ids)) | (UserGraphEdgeRecord.to_node_id.in_(old_ids)),
            )
        )
        db.execute(delete(UserGraphNodeRecord).where(UserGraphNodeRecord.id.in_(old_ids)))
        db.flush()

    for value in values:
        clean_value = value.strip()
        if not clean_value:
            continue
        node = _get_or_create_node(db, user_id, node_type, clean_value, {"value": clean_value}, source=source)
        _ensure_edge(db, user_id, root_node_id, node.id, PERSISTENT_NODE_TYPES[node_type])


def _ensure_session_node(db: Session, user_id: str, session_id: str) -> UserGraphNodeRecord:
    existing = (
        db.execute(
            select(UserGraphNodeRecord).where(
                UserGraphNodeRecord.user_id == user_id,
                UserGraphNodeRecord.node_type == "session",
                UserGraphNodeRecord.label == session_id,
            )
        )
        .scalars()
        .first()
    )
    if existing:
        return existing
    node = UserGraphNodeRecord(
        user_id=user_id,
        node_type="session",
        label=session_id,
        payload={"session_id": session_id},
        source="chat",
    )
    db.add(node)
    db.flush()
    return node


def _get_or_create_node(
    db: Session,
    user_id: str,
    node_type: str,
    label: str,
    payload: dict[str, Any],
    *,
    source: str,
) -> UserGraphNodeRecord:
    existing = (
        db.execute(
            select(UserGraphNodeRecord).where(
                UserGraphNodeRecord.user_id == user_id,
                UserGraphNodeRecord.node_type == node_type,
                UserGraphNodeRecord.label == label,
                UserGraphNodeRecord.source == source,
            )
        )
        .scalars()
        .first()
    )
    if existing:
        merged_payload = dict(existing.payload or {})
        merged_payload.update(payload or {})
        existing.payload = merged_payload
        db.add(existing)
        db.flush()
        return existing
    node = UserGraphNodeRecord(
        user_id=user_id,
        node_type=node_type,
        label=label,
        payload=payload,
        source=source,
    )
    db.add(node)
    db.flush()
    return node


def _ensure_edge(
    db: Session,
    user_id: str,
    from_node_id: str,
    to_node_id: str,
    edge_type: str,
    payload: dict[str, Any] | None = None,
) -> UserGraphEdgeRecord:
    existing = (
        db.execute(
            select(UserGraphEdgeRecord).where(
                UserGraphEdgeRecord.user_id == user_id,
                UserGraphEdgeRecord.from_node_id == from_node_id,
                UserGraphEdgeRecord.to_node_id == to_node_id,
                UserGraphEdgeRecord.edge_type == edge_type,
            )
        )
        .scalars()
        .first()
    )
    if existing:
        if payload:
            existing.payload = payload
            db.add(existing)
            db.flush()
        return existing
    edge = UserGraphEdgeRecord(
        user_id=user_id,
        from_node_id=from_node_id,
        to_node_id=to_node_id,
        edge_type=edge_type,
        payload=payload or {},
    )
    db.add(edge)
    db.flush()
    return edge


def _build_profile_highlights(user: UserRecord | None) -> list[str]:
    if not user:
        return []
    parts = [item for item in [user.birth_year, user.sex, user.region_code] if item]
    return parts[:3]


def _filter_nodes_for_existing_sessions(
    nodes: list[UserGraphNodeRecord],
    valid_session_ids: set[str],
) -> list[UserGraphNodeRecord]:
    filtered = []
    for node in nodes:
        payload_session_id = str((node.payload or {}).get("session_id") or "")
        if node.node_type == "session" and node.label not in valid_session_ids:
            continue
        if payload_session_id and payload_session_id not in valid_session_ids:
            continue
        filtered.append(node)
    return filtered


def _prune_orphan_symptom_nodes(db: Session, user_id: str) -> None:
    symptom_nodes = (
        db.execute(
            select(UserGraphNodeRecord).where(
                UserGraphNodeRecord.user_id == user_id,
                UserGraphNodeRecord.node_type == "symptom",
            )
        )
        .scalars()
        .all()
    )
    for node in symptom_nodes:
        has_edges = (
            db.execute(
                select(UserGraphEdgeRecord).where(
                    UserGraphEdgeRecord.user_id == user_id,
                    (UserGraphEdgeRecord.from_node_id == node.id) | (UserGraphEdgeRecord.to_node_id == node.id),
                )
            )
            .scalars()
            .first()
        )
        if not has_edges:
            db.delete(node)
    db.flush()


def _build_recent_journey(
    nodes: list[UserGraphNodeRecord],
    current_session_id: str | None,
    session_ids_by_recency: list[str],
    fallback_cards: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    session_rank = {session_id: index for index, session_id in enumerate(session_ids_by_recency)}
    grouped: dict[str, dict[str, Any]] = {}

    for node in nodes:
        if node.node_type not in {"symptom_event", "timeline_marker"}:
            continue
        payload = node.payload or {}
        session_id = str(payload.get("session_id") or "")
        if not session_id:
            continue
        group = grouped.setdefault(
            session_id,
            {
                "markers": [],
                "symptoms": [],
                "messages": [],
                "sort_time": _node_sort_time(node),
            },
        )
        group["sort_time"] = max(group["sort_time"], _node_sort_time(node))
        if node.node_type == "timeline_marker" and node.label not in group["markers"]:
            group["markers"].append(node.label)
        if node.node_type == "symptom_event":
            symptom_label, message = _split_symptom_event_label(node.label, str(payload.get("message") or ""))
            if symptom_label and symptom_label not in group["symptoms"]:
                group["symptoms"].append(symptom_label)
            clean_message = message.strip()
            if clean_message and clean_message not in group["messages"]:
                group["messages"].append(clean_message)

    journey = []
    for session_id, group in grouped.items():
        markers = group["markers"][:2]
        symptoms = group["symptoms"][:3]
        messages = group["messages"][:2]
        title_parts = []
        if markers:
            title_parts.append(" / ".join(markers))
        if symptoms:
            title_parts.append("、".join(symptoms))
        title = " ".join(title_parts).strip() or (messages[0][:60] if messages else session_id)
        detail = "；".join(message[:90] for message in messages if message) or title
        journey.append(
            {
                "title": title,
                "detail": detail,
                "session_id": session_id,
                "is_current_session": bool(current_session_id and session_id == current_session_id),
                "sort_time": group["sort_time"].isoformat(),
                "severity_hint": "medium" if any(marker in {"加重", "持续"} for marker in markers) else "low",
                "_session_rank": session_rank.get(session_id, 999),
                "_sort_epoch": group["sort_time"].timestamp(),
            }
        )

    existing_sessions = {item["session_id"] for item in journey}
    for session_id in session_ids_by_recency:
        if session_id in existing_sessions:
            continue
        fallback = fallback_cards.get(session_id)
        if not fallback:
            continue
        journey.append(
            {
                "title": fallback["title"],
                "detail": fallback["detail"],
                "session_id": session_id,
                "is_current_session": bool(current_session_id and session_id == current_session_id),
                "sort_time": fallback["sort_time"],
                "severity_hint": fallback["severity_hint"],
                "_session_rank": session_rank.get(session_id, 999),
                "_sort_epoch": fallback["_sort_epoch"],
            }
        )

    journey.sort(
        key=lambda item: (
            0 if item["is_current_session"] else 1,
            item["_session_rank"],
            -item["_sort_epoch"],
        )
    )
    return [{key: value for key, value in item.items() if key != "_session_rank"} for item in journey[:5]]


def _build_risk_signal_summary(
    nodes: list[UserGraphNodeRecord],
    current_session_id: str | None,
    session_ids_by_recency: list[str],
) -> list[dict[str, Any]]:
    session_rank = {session_id: index for index, session_id in enumerate(session_ids_by_recency)}
    items = []
    for node in nodes:
        if node.node_type != "risk_signal":
            continue
        payload = node.payload or {}
        session_id = str(payload.get("session_id") or "")
        risk_level = str(payload.get("risk_level") or "medium")
        is_current_session = bool(current_session_id and session_id == current_session_id)
        items.append(
            {
                "label": node.label,
                "risk_level": risk_level,
                "session_id": session_id,
                "is_current_session": is_current_session,
                "is_active": is_current_session,
                "sort_time": _node_sort_time(node).isoformat(),
                "_priority": _risk_priority(risk_level),
                "_session_rank": session_rank.get(session_id, 999),
                "_sort_epoch": _node_sort_time(node).timestamp(),
            }
        )

    items.sort(
        key=lambda item: (
            0 if item["is_current_session"] else 1,
            -item["_priority"],
            item["_session_rank"],
            -item["_sort_epoch"],
        )
    )

    if not any(item["is_active"] and item["risk_level"] in {"high", "emergency"} for item in items):
        for item in items:
            if item["is_current_session"]:
                item["is_active"] = True
                break

    return [{key: value for key, value in item.items() if not key.startswith("_")} for item in items[:6]]


def _build_session_fallback_cards(db: Session, sessions_by_recency: list[SessionRecord]) -> dict[str, dict[str, Any]]:
    if not sessions_by_recency:
        return {}
    session_ids = [session.id for session in sessions_by_recency]
    messages = (
        db.execute(
            select(MessageRecord)
            .where(MessageRecord.session_id.in_(session_ids))
            .order_by(MessageRecord.created_at.asc(), MessageRecord.id.asc())
        )
        .scalars()
        .all()
    )
    grouped: dict[str, dict[str, str]] = {
        session.id: {"latest_user": "", "latest_conclusion": ""}
        for session in sessions_by_recency
    }
    for message in messages:
        if message.role == "user":
            grouped.setdefault(message.session_id, {})["latest_user"] = message.content.strip()
        elif message.role == "assistant":
            parsed = _parse_assistant_json(message.content)
            if parsed and str(parsed.get("stage") or "") == "conclusion":
                grouped.setdefault(message.session_id, {})["latest_conclusion"] = str(parsed.get("summary") or "").strip()

    cards: dict[str, dict[str, Any]] = {}
    for session in sessions_by_recency:
        session_group = grouped.get(session.id, {})
        title_source = session_group.get("latest_conclusion") or session_group.get("latest_user") or session.summary or session.id
        detail_source = session_group.get("latest_user") or session_group.get("latest_conclusion") or session.summary or title_source
        cards[session.id] = {
            "title": title_source[:80].strip(),
            "detail": detail_source[:120].strip(),
            "sort_time": (session.updated_at or session.created_at or datetime.utcnow()).isoformat(),
            "severity_hint": session.latest_risk or "low",
            "_sort_epoch": (session.updated_at or session.created_at or datetime.utcnow()).timestamp(),
        }
    return cards


def _split_symptom_event_label(label: str, fallback_message: str) -> tuple[str, str]:
    if ":" not in label:
        return label.strip(), fallback_message.strip()
    symptom, message = label.split(":", 1)
    return symptom.strip(), (message or fallback_message).strip()


def _node_sort_time(node: UserGraphNodeRecord) -> datetime:
    return node.updated_at or node.created_at or datetime.utcnow()


def _risk_priority(risk_level: str) -> int:
    return {"emergency": 100, "high": 80, "medium": 50, "low": 20}.get(risk_level, 20)


def _extract_labels(text: str, patterns: list[tuple[str, str]]) -> list[str]:
    lowered = text.lower()
    hits: list[str] = []
    for label, pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE) or re.search(pattern, lowered, flags=re.IGNORECASE):
            hits.append(label)
    return list(dict.fromkeys(hits))


def _materialize_user_message_nodes(
    db: Session,
    *,
    user_id: str,
    session_id: str,
    session_node_id: str,
    locale: str,
    text: str,
) -> None:
    symptom_labels = _extract_labels(text, SYMPTOM_PATTERNS)
    for label in symptom_labels:
        symptom_node = _get_or_create_node(db, user_id, "symptom", label, {"locale": locale}, source="extracted")
        _ensure_edge(db, user_id, session_node_id, symptom_node.id, "REPORTED_SYMPTOM")
        event_node = _get_or_create_node(
            db,
            user_id,
            "symptom_event",
            f"{label}:{text[:80]}",
            {"session_id": session_id, "message": text, "locale": locale},
            source="chat",
        )
        _ensure_edge(db, user_id, symptom_node.id, event_node.id, "EVOLVED_TO")
        _ensure_edge(db, user_id, session_node_id, event_node.id, "REPORTED_SYMPTOM")

    for label in _extract_labels(text, TIMELINE_PATTERNS):
        marker_node = _get_or_create_node(
            db,
            user_id,
            "timeline_marker",
            label,
            {"session_id": session_id, "message": text},
            source="chat",
        )
        _ensure_edge(db, user_id, session_node_id, marker_node.id, "OCCURRED_AT")


def _materialize_assistant_summary_nodes(
    db: Session,
    *,
    user_id: str,
    session_id: str,
    session_node_id: str,
    text: str,
) -> None:
    if not text:
        return
    for label in _extract_labels(text, SYMPTOM_PATTERNS):
        symptom_node = _get_or_create_node(db, user_id, "symptom", label, {"locale": ""}, source="extracted")
        _ensure_edge(db, user_id, session_node_id, symptom_node.id, "REPORTED_SYMPTOM")
        event_node = _get_or_create_node(
            db,
            user_id,
            "symptom_event",
            f"{label}:{text[:80]}",
            {"session_id": session_id, "message": text},
            source="summary",
        )
        _ensure_edge(db, user_id, symptom_node.id, event_node.id, "EVOLVED_TO")
        _ensure_edge(db, user_id, session_node_id, event_node.id, "REPORTED_SYMPTOM")

    for label in _extract_labels(text, TIMELINE_PATTERNS):
        marker_node = _get_or_create_node(
            db,
            user_id,
            "timeline_marker",
            label,
            {"session_id": session_id, "message": text},
            source="summary",
        )
        _ensure_edge(db, user_id, session_node_id, marker_node.id, "OCCURRED_AT")


def _parse_assistant_json(content: str) -> dict[str, Any] | None:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _extract_readable_risk_labels(answer: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    emergency = str(answer.get("emergency_guidance") or "").strip()
    if emergency:
        labels.append(emergency[:120])
    summary = str(answer.get("summary") or "").strip()
    if summary:
        labels.append(summary[:120])
    risk_level = str(answer.get("risk_level") or "").strip().lower()
    if risk_level and risk_level not in labels:
        labels.append(risk_level)
    return list(dict.fromkeys([label for label in labels if label]))[:2]
