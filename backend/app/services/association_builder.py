from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import re
from typing import Any, Callable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import MessageRecord, SessionRecord, UserGraphEdgeRecord, UserGraphNodeRecord, UserRecord

RULE_ASSOCIATION_EDGE_TYPES = {
    "POSSIBLY_RELATED_TO",
    "POSSIBLY_EXPLAINED_BY",
    "POSSIBLY_RECURRENT_WITH",
    "POSSIBLY_CYCLE_RELATED",
}

MODEL_ANALYSIS_EDGE_TYPES = {
    "MODEL_POSSIBLY_RELATED_TO",
    "MODEL_POSSIBLY_EXPLAINED_BY",
    "MODEL_POSSIBLY_RECURRENT_WITH",
    "MODEL_POSSIBLY_PATTERN_LINKED",
}

ASSOCIATION_EDGE_TYPES = RULE_ASSOCIATION_EDGE_TYPES | MODEL_ANALYSIS_EDGE_TYPES

CONDITION_SYMPTOM_RULES: list[tuple[str, tuple[str, ...], tuple[str, ...], str]] = [
    (
        "cardiac",
        ("先天性心脏病", "心脏病", "冠心病", "心律失常", "congenital heart", "heart disease", "cardiac"),
        ("胸痛", "呼吸困难", "头晕", "乏力"),
        "POSSIBLY_EXPLAINED_BY",
    ),
    (
        "respiratory",
        ("哮喘", "慢阻肺", "支气管炎", "asthma", "copd", "bronchitis"),
        ("呼吸困难", "咳嗽", "胸痛", "乏力"),
        "POSSIBLY_RELATED_TO",
    ),
    (
        "gastrointestinal",
        ("胃炎", "肠易激", "胃溃疡", "gastritis", "ibs", "ulcer"),
        ("腹痛", "腹泻", "恶心", "呕吐"),
        "POSSIBLY_RELATED_TO",
    ),
    (
        "allergy",
        ("过敏", "allergy", "eczema", "湿疹"),
        ("皮疹", "呼吸困难", "腹泻"),
        "POSSIBLY_RELATED_TO",
    ),
]

MEDICATION_SYMPTOM_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (("抗生素", "antibiotic"), ("腹泻", "恶心", "皮疹")),
    (("止痛药", "painkiller", "nsaid"), ("腹痛", "恶心")),
]

ALLERGY_SYMPTOM_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (("青霉素", "penicillin"), ("皮疹", "呼吸困难", "腹泻")),
    (("花粉", "pollen"), ("皮疹", "呼吸困难")),
]

CYCLE_PATTERNS = [
    r"月经",
    r"经期",
    r"生理期",
    r"例假",
    r"周期",
    r"上个月",
    r"这个月",
    r"上月",
    r"本月",
]


@dataclass
class AssociationCandidate:
    from_node_id: str
    to_node_id: str
    edge_type: str
    confidence: str
    evidence_type: str
    evidence_summary: str
    rule_keys: list[str]
    source_session_ids: list[str]
    active: bool
    sort_key: str


def rebuild_association_edges(
    db: Session,
    user_id: str,
    *,
    locale: str,
    current_session_id: str | None = None,
    enhancer: Callable[[str], str] | None = None,
) -> None:
    user = db.get(UserRecord, user_id)
    if not user:
        return

    _delete_existing_association_edges(db, user_id)
    candidates = build_association_edges_for_user(
        db,
        user,
        locale=locale,
        current_session_id=current_session_id,
    )
    if enhancer and candidates:
        candidates = enhance_association_candidates(
            user=user,
            candidates=candidates,
            locale=locale,
            enhancer=enhancer,
        )
    _persist_candidates(db, user_id, candidates)


def prune_invalid_association_edges(db: Session, user_id: str, valid_node_ids: set[str], valid_session_ids: set[str]) -> None:
    edges = (
        db.execute(
            select(UserGraphEdgeRecord).where(
                UserGraphEdgeRecord.user_id == user_id,
                UserGraphEdgeRecord.edge_type.in_(ASSOCIATION_EDGE_TYPES),
            )
        )
        .scalars()
        .all()
    )
    removable_ids: list[str] = []
    for edge in edges:
        if edge.from_node_id not in valid_node_ids or edge.to_node_id not in valid_node_ids:
            removable_ids.append(edge.id)
            continue
        source_session_ids = [str(item) for item in (edge.payload or {}).get("source_session_ids") or [] if str(item)]
        if source_session_ids and any(session_id not in valid_session_ids for session_id in source_session_ids):
            removable_ids.append(edge.id)
    if removable_ids:
        db.execute(delete(UserGraphEdgeRecord).where(UserGraphEdgeRecord.id.in_(removable_ids)))
        db.flush()


def replace_model_analysis_edges(
    db: Session,
    user_id: str,
    *,
    rows: list[dict[str, Any]],
    analyzed_at: str,
) -> None:
    db.execute(
        delete(UserGraphEdgeRecord).where(
            UserGraphEdgeRecord.user_id == user_id,
            UserGraphEdgeRecord.edge_type.in_(MODEL_ANALYSIS_EDGE_TYPES),
        )
    )
    db.flush()
    for row in rows:
        db.add(
            UserGraphEdgeRecord(
                user_id=user_id,
                from_node_id=row["from_ref"],
                to_node_id=row["to_ref"],
                edge_type=row["edge_type"],
                payload={
                    "confidence": row["confidence"],
                    "evidence_type": "model_analysis",
                    "evidence_summary": row["evidence_summary"],
                    "source_session_ids": row["source_session_ids"],
                    "analysis_run_at": analyzed_at,
                    "active": bool(row["source_session_ids"]),
                },
            )
        )
    db.flush()


def build_association_edges_for_user(
    db: Session,
    user: UserRecord,
    *,
    locale: str,
    current_session_id: str | None = None,
) -> list[AssociationCandidate]:
    sessions = (
        db.execute(
            select(SessionRecord).where(SessionRecord.user_id == user.id).order_by(SessionRecord.updated_at.desc(), SessionRecord.created_at.desc())
        )
        .scalars()
        .all()
    )
    if not sessions:
        return []

    session_ids = [session.id for session in sessions]
    session_nodes = {
        node.label: node
        for node in db.execute(
            select(UserGraphNodeRecord).where(
                UserGraphNodeRecord.user_id == user.id,
                UserGraphNodeRecord.node_type == "session",
            )
        ).scalars()
        if node.label in session_ids
    }
    nodes = (
        db.execute(select(UserGraphNodeRecord).where(UserGraphNodeRecord.user_id == user.id))
        .scalars()
        .all()
    )
    messages = (
        db.execute(
            select(MessageRecord)
            .where(MessageRecord.session_id.in_(session_ids))
            .order_by(MessageRecord.created_at.asc(), MessageRecord.id.asc())
        )
        .scalars()
        .all()
    )

    conditions = [node for node in nodes if node.node_type == "condition"]
    medications = [node for node in nodes if node.node_type == "medication"]
    allergies = [node for node in nodes if node.node_type == "allergy"]
    symptom_nodes = [node for node in nodes if node.node_type == "symptom"]
    symptom_events = [node for node in nodes if node.node_type == "symptom_event"]
    summaries = [node for node in nodes if node.node_type == "summary"]

    session_messages: dict[str, list[MessageRecord]] = {session.id: [] for session in sessions}
    for message in messages:
        if message.session_id in session_messages:
            session_messages[message.session_id].append(message)

    symptom_sessions: dict[str, set[str]] = {}
    session_symptoms: dict[str, set[str]] = {session.id: set() for session in sessions}
    symptom_event_by_session: dict[tuple[str, str], UserGraphNodeRecord] = {}
    for event in symptom_events:
        session_id = str((event.payload or {}).get("session_id") or "")
        symptom_label, _ = _split_symptom_event_label(event.label, str((event.payload or {}).get("message") or ""))
        if not session_id or session_id not in session_messages or not symptom_label:
            continue
        session_symptoms.setdefault(session_id, set()).add(symptom_label)
        symptom_sessions.setdefault(symptom_label, set()).add(session_id)
        symptom_event_by_session.setdefault((session_id, symptom_label), event)

    summary_by_session = {
        str((node.payload or {}).get("session_id") or ""): node
        for node in summaries
        if str((node.payload or {}).get("session_id") or "") in session_messages
    }

    candidates: dict[str, AssociationCandidate] = {}
    most_recent_session_id = current_session_id or (sessions[0].id if sessions else None)
    female_user = user.sex == "female"

    for condition in conditions:
        lowered = condition.label.lower()
        for rule_key, condition_terms, symptom_labels, edge_type in CONDITION_SYMPTOM_RULES:
            if not any(term in lowered for term in condition_terms):
                continue
            matched_sessions = sorted(
                {
                    session_id
                    for session_id, labels in session_symptoms.items()
                    if any(symptom_label in labels for symptom_label in symptom_labels)
                }
            )
            if not matched_sessions:
                continue
            for session_id in matched_sessions[:3]:
                session_node = session_nodes.get(session_id)
                if not session_node:
                    continue
                matched = [label for label in symptom_labels if label in session_symptoms.get(session_id, set())]
                evidence = _localize(
                    locale,
                    zh=f"{condition.label} 与本次出现的 {'、'.join(matched)} 可能有关联。",
                    en=f"{condition.label} may be related to the reported {', '.join(matched)}.",
                )
                key = f"{condition.id}:{session_node.id}:{edge_type}"
                candidates[key] = AssociationCandidate(
                    from_node_id=condition.id,
                    to_node_id=session_node.id,
                    edge_type=edge_type,
                    confidence="medium",
                    evidence_type="rule",
                    evidence_summary=evidence,
                    rule_keys=[f"condition:{rule_key}"],
                    source_session_ids=[session_id],
                    active=session_id == most_recent_session_id,
                    sort_key=key,
                )

    for medication in medications:
        lowered = medication.label.lower()
        for med_terms, symptom_labels in MEDICATION_SYMPTOM_RULES:
            if not any(term in lowered for term in med_terms):
                continue
            for session_id, labels in session_symptoms.items():
                matched = [label for label in symptom_labels if label in labels]
                if not matched:
                    continue
                session_node = session_nodes.get(session_id)
                if not session_node:
                    continue
                evidence = _localize(
                    locale,
                    zh=f"{medication.label} 与 {'、'.join(matched)} 可能存在相关性，值得回顾用药时间和不适出现顺序。",
                    en=f"{medication.label} may be associated with {', '.join(matched)}; review the medication timing against symptom onset.",
                )
                key = f"{medication.id}:{session_node.id}:medication"
                candidates[key] = AssociationCandidate(
                    from_node_id=medication.id,
                    to_node_id=session_node.id,
                    edge_type="POSSIBLY_RELATED_TO",
                    confidence="low",
                    evidence_type="rule",
                    evidence_summary=evidence,
                    rule_keys=["medication:symptom_overlap"],
                    source_session_ids=[session_id],
                    active=session_id == most_recent_session_id,
                    sort_key=key,
                )

    for allergy in allergies:
        lowered = allergy.label.lower()
        for allergy_terms, symptom_labels in ALLERGY_SYMPTOM_RULES:
            if not any(term in lowered for term in allergy_terms):
                continue
            for session_id, labels in session_symptoms.items():
                matched = [label for label in symptom_labels if label in labels]
                if not matched:
                    continue
                session_node = session_nodes.get(session_id)
                if not session_node:
                    continue
                evidence = _localize(
                    locale,
                    zh=f"{allergy.label} 过敏史与 {'、'.join(matched)} 可能相关，建议回顾暴露史。",
                    en=f"The {allergy.label} allergy history may relate to {', '.join(matched)} and should be reviewed against recent exposures.",
                )
                key = f"{allergy.id}:{session_node.id}:allergy"
                candidates[key] = AssociationCandidate(
                    from_node_id=allergy.id,
                    to_node_id=session_node.id,
                    edge_type="POSSIBLY_RELATED_TO",
                    confidence="medium",
                    evidence_type="rule",
                    evidence_summary=evidence,
                    rule_keys=["allergy:symptom_overlap"],
                    source_session_ids=[session_id],
                    active=session_id == most_recent_session_id,
                    sort_key=key,
                )

    for symptom_label, seen_session_ids in symptom_sessions.items():
        ordered = [session.id for session in sessions if session.id in seen_session_ids]
        if len(ordered) < 2:
            continue
        current_id = ordered[0]
        previous_id = ordered[1]
        current_node = session_nodes.get(current_id)
        previous_node = session_nodes.get(previous_id)
        if current_node and previous_node:
            evidence = _localize(
                locale,
                zh=f"{symptom_label} 在不同问诊中重复出现，可能提示复发或持续问题。",
                en=f"{symptom_label} appeared across multiple consultations and may reflect recurrence or persistence.",
            )
            key = f"{previous_node.id}:{current_node.id}:recurrent:{symptom_label}"
            candidates[key] = AssociationCandidate(
                from_node_id=previous_node.id,
                to_node_id=current_node.id,
                edge_type="POSSIBLY_RECURRENT_WITH",
                confidence="medium",
                evidence_type="rule",
                evidence_summary=evidence,
                rule_keys=["symptom:recurrent"],
                source_session_ids=[previous_id, current_id],
                active=current_id == most_recent_session_id,
                sort_key=key,
            )

        if not female_user or symptom_label != "腹痛" or len(ordered) < 2:
            continue
        current_messages = _session_text_blob(session_messages.get(current_id, []), summary_by_session.get(current_id))
        previous_messages = _session_text_blob(session_messages.get(previous_id, []), summary_by_session.get(previous_id))
        if _looks_cycle_related(current_messages) or _looks_cycle_related(previous_messages):
            current_node = session_nodes.get(current_id)
            previous_node = session_nodes.get(previous_id)
            if current_node and previous_node:
                evidence = _localize(
                    locale,
                    zh="腹痛在相邻月份重复出现，且文本中出现周期/月经相关线索，可能与经期有关。",
                    en="Abdominal pain recurred across adjacent months with cycle-related language, suggesting a possible menstrual association.",
                )
                key = f"{previous_node.id}:{current_node.id}:cycle"
                candidates[key] = AssociationCandidate(
                    from_node_id=previous_node.id,
                    to_node_id=current_node.id,
                    edge_type="POSSIBLY_CYCLE_RELATED",
                    confidence="medium",
                    evidence_type="rule",
                    evidence_summary=evidence,
                    rule_keys=["cycle:monthly_abdominal_pain"],
                    source_session_ids=[previous_id, current_id],
                    active=current_id == most_recent_session_id,
                    sort_key=key,
                )

    return list(candidates.values())


def enhance_association_candidates(
    *,
    user: UserRecord,
    candidates: list[AssociationCandidate],
    locale: str,
    enhancer: Callable[[str], str],
) -> list[AssociationCandidate]:
    if not candidates:
        return candidates

    payload = {
        "locale": locale,
        "sex": user.sex,
        "birth_year": user.birth_year,
        "region_code": user.region_code,
        "candidates": [
            {
                "id": candidate.sort_key,
                "edge_type": candidate.edge_type,
                "confidence": candidate.confidence,
                "evidence_summary": candidate.evidence_summary,
                "rule_keys": candidate.rule_keys,
                "source_session_ids": candidate.source_session_ids,
            }
            for candidate in candidates
        ],
    }
    prompt = (
        "You are refining health-graph candidate associations.\n"
        "Return strict JSON with shape: "
        '{"candidates":[{"id":"string","confidence":"low|medium|high","evidence_summary":"string"}]}.\n'
        "Only revise confidence and evidence_summary for existing candidates.\n"
        "Do not add new candidates. Do not state diagnoses. Keep evidence concise and factual.\n"
        f"INPUT_JSON:\n{json.dumps(payload, ensure_ascii=False)}"
    )

    try:
        raw = enhancer(prompt)
        parsed = json.loads(_extract_json_object(raw))
    except Exception:
        return candidates

    by_id = {
        str(item.get("id")): item
        for item in parsed.get("candidates", [])
        if isinstance(item, dict) and str(item.get("id") or "")
    }
    for candidate in candidates:
        updated = by_id.get(candidate.sort_key)
        if not updated:
            continue
        confidence = str(updated.get("confidence") or candidate.confidence).lower()
        if confidence in {"low", "medium", "high"}:
            candidate.confidence = confidence
        summary = str(updated.get("evidence_summary") or "").strip()
        if summary:
            candidate.evidence_summary = summary[:280]
            candidate.evidence_type = "hybrid"
    return candidates


def _persist_candidates(db: Session, user_id: str, candidates: list[AssociationCandidate]) -> None:
    for candidate in candidates:
        db.add(
            UserGraphEdgeRecord(
                user_id=user_id,
                from_node_id=candidate.from_node_id,
                to_node_id=candidate.to_node_id,
                edge_type=candidate.edge_type,
                payload={
                    "confidence": candidate.confidence,
                    "evidence_type": candidate.evidence_type,
                    "evidence_summary": candidate.evidence_summary,
                    "rule_keys": candidate.rule_keys,
                    "source_session_ids": candidate.source_session_ids,
                    "active": candidate.active,
                    "updated_at": datetime.utcnow().isoformat(),
                },
            )
        )
    db.flush()


def _delete_existing_association_edges(db: Session, user_id: str) -> None:
    db.execute(
        delete(UserGraphEdgeRecord).where(
            UserGraphEdgeRecord.user_id == user_id,
            UserGraphEdgeRecord.edge_type.in_(RULE_ASSOCIATION_EDGE_TYPES),
        )
    )
    db.flush()


def _looks_cycle_related(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in CYCLE_PATTERNS)


def _session_text_blob(messages: list[MessageRecord], summary_node: UserGraphNodeRecord | None) -> str:
    parts = [message.content.strip() for message in messages if message.content.strip()]
    if summary_node and summary_node.label.strip():
        parts.append(summary_node.label.strip())
    return " ".join(parts)


def _extract_json_object(text: str) -> str:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        return match.group(0)
    raise ValueError("No JSON object found")


def _split_symptom_event_label(label: str, fallback_message: str) -> tuple[str, str]:
    if ":" not in label:
        return label.strip(), fallback_message.strip()
    symptom, message = label.split(":", 1)
    return symptom.strip(), (message or fallback_message).strip()


def _localize(locale: str, *, zh: str, en: str) -> str:
    return zh if locale.startswith("zh") else en
