from datetime import datetime
import json
import re

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, func, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings, get_settings
from .database import Base, build_session_factory, create_engine_for_url, get_db_session
from .models import MessageRecord, RuntimeConfig, SessionRecord
from .schemas import (
    ChatAnswer,
    ChatMeta,
    ChatRequest,
    ChatResponse,
    MessageItem,
    MessageListResponse,
    ModelConfigRequest,
    ModelConfigResponse,
    ModelConfigStatusResponse,
    SessionItem,
    SessionListResponse,
)
from .services.context_builder import build_context
from .services.model_adapter import ModelAdapter, ModelAPIError, normalize_model_base_url
from .services.output_parser import parse_model_json
from .services.prompt_builder import build_system_prompt, build_user_prompt
from .services.safety import (
    build_emergency_guidance,
    classify_risk,
    enforce_no_diagnosis_or_prescription,
    max_risk,
)
from .services.summarizer import build_summary

MIN_TRIAGE_ROUNDS = 3
MAX_TRIAGE_ROUNDS = 5


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()

    app = FastAPI(title=app_settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    engine = create_engine_for_url(app_settings.database_url)
    session_factory = build_session_factory(engine)

    app.state.settings = app_settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.model_adapter = ModelAdapter(
        base_url=app_settings.model_base_url,
        api_key=app_settings.model_api_key,
        model_name=app_settings.model_name,
        timeout_seconds=app_settings.model_timeout_seconds,
    )

    @app.on_event("startup")
    def startup() -> None:
        Base.metadata.create_all(bind=engine)
        _ensure_sessions_triage_columns(engine)

        with session_factory() as db:
            runtime_config = _ensure_runtime_config_row(db, app_settings)
            _sync_adapter_from_runtime(app.state.model_adapter, runtime_config)

    def get_session_factory() -> sessionmaker[Session]:
        return app.state.session_factory

    def db_dependency(factory: sessionmaker[Session] = Depends(get_session_factory)):
        yield from get_db_session(factory)

    @app.get("/health")
    def healthcheck() -> dict:
        return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

    @app.get(f"{app_settings.api_prefix}/model-config/status", response_model=ModelConfigStatusResponse)
    def get_model_config_status(db: Session = Depends(db_dependency)) -> ModelConfigStatusResponse:
        runtime_config = _ensure_runtime_config_row(db, app_settings)
        _sync_adapter_from_runtime(app.state.model_adapter, runtime_config)
        return ModelConfigStatusResponse(
            configured=app.state.model_adapter.is_configured(),
            base_url=runtime_config.model_base_url,
            model_name=runtime_config.model_name,
        )

    @app.post(f"{app_settings.api_prefix}/model-config", response_model=ModelConfigResponse)
    def save_model_config(payload: ModelConfigRequest, db: Session = Depends(db_dependency)) -> ModelConfigResponse:
        runtime_config = _ensure_runtime_config_row(db, app_settings)

        runtime_config.model_base_url = normalize_model_base_url(payload.base_url)
        runtime_config.model_api_key = payload.api_key.strip()
        runtime_config.model_name = payload.model_name.strip()

        db.add(runtime_config)
        db.commit()
        db.refresh(runtime_config)

        _sync_adapter_from_runtime(app.state.model_adapter, runtime_config)
        return ModelConfigResponse(
            configured=app.state.model_adapter.is_configured(),
            base_url=runtime_config.model_base_url,
            model_name=runtime_config.model_name,
        )

    @app.post(f"{app_settings.api_prefix}/chat", response_model=ChatResponse)
    def chat(payload: ChatRequest, db: Session = Depends(db_dependency)) -> ChatResponse:
        session_record = _get_or_create_session(db, payload)
        profile_changed = _merge_profile(session_record, payload.health_profile.model_dump() if payload.health_profile else None)

        initial_risk = classify_risk(payload.message)
        user_message = MessageRecord(
            session_id=session_record.id,
            role="user",
            content=payload.message,
            risk_level=initial_risk.risk_level,
            priority=_risk_priority(initial_risk.risk_level),
        )
        db.add(user_message)
        db.flush()

        if initial_risk.risk_level == "emergency":
            answer = {
                "summary": (
                    "检测到潜在急症风险，建议立即线下急救/急诊。"
                    if payload.locale.startswith("zh")
                    else "Potential emergency risk detected. Seek emergency care immediately."
                ),
                "risk_level": "emergency",
                "next_steps": (
                    [
                        "立即拨打急救电话并前往最近急诊。",
                        "不要单独等待症状自行缓解。",
                        "准备当前症状发生时间与既往病史，便于急诊评估。",
                    ]
                    if payload.locale.startswith("zh")
                    else [
                        "Call emergency services and go to the nearest ER now.",
                        "Do not wait alone for symptoms to resolve.",
                        "Prepare symptom timeline and medical history for triage.",
                    ]
                ),
                "emergency_guidance": build_emergency_guidance(
                    payload.locale, payload.region_code, initial_risk.triggers
                ),
                "disclaimer": (
                    "本回答仅用于健康信息参考，不能替代医生诊疗。"
                    if payload.locale.startswith("zh")
                    else "Informational only and not a replacement for medical diagnosis or treatment."
                ),
                "stage": "conclusion",
                "follow_up_questions": None,
            }
            session_record.triage_stage = "conclusion"
            model_name = "safety-router"
            used_context_turns = 0
        else:
            history = (
                db.execute(
                    select(MessageRecord)
                    .where(MessageRecord.session_id == session_record.id, MessageRecord.id != user_message.id)
                    .order_by(desc(MessageRecord.created_at))
                    .limit(40)
                )
                .scalars()
                .all()
            )
            context = build_context(
                session_summary=session_record.summary,
                message_history=history,
                turn_limit=app_settings.context_turn_limit,
                max_chars=app_settings.max_context_chars,
            )
            next_round = (session_record.triage_round_count or 0) + 1
            current_stage = session_record.triage_stage or "intake"
            forced_stage = _choose_forced_stage(current_stage, next_round)
            required_slots = _build_required_slots(
                locale=payload.locale,
                current_message=payload.message,
                health_profile=session_record.health_profile or {},
                recent_messages=context.recent_messages,
            )
            target_stage = forced_stage or current_stage
            system_prompt = build_system_prompt(payload.locale, target_stage)
            user_prompt = build_user_prompt(
                locale=payload.locale,
                message=payload.message,
                profile=payload.health_profile,
                long_summary=context.summary,
                recent_messages=context.recent_messages,
                triage_stage=target_stage,
                triage_round_count=next_round,
                max_rounds=MAX_TRIAGE_ROUNDS,
                required_slots=required_slots,
            )
            try:
                model_result = app.state.model_adapter.generate(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    locale=payload.locale,
                )
            except ModelAPIError as exc:
                raise HTTPException(
                    status_code=exc.status_code,
                    detail={
                        "message": str(exc),
                        "hint": "Please verify model Base URL / API Key (Token) / model name.",
                    },
                ) from exc
            answer = parse_model_json(model_result.content, payload.locale)
            answer = _apply_stage_rules(answer, payload.locale, next_round)
            session_record.triage_round_count = next_round
            session_record.triage_stage = answer["stage"]
            answer["risk_level"] = max_risk(answer["risk_level"], initial_risk.risk_level)
            if answer["risk_level"] in {"high", "emergency"}:
                answer["emergency_guidance"] = build_emergency_guidance(
                    payload.locale, payload.region_code, initial_risk.triggers
                )
            if answer["stage"] == "conclusion":
                answer = enforce_no_diagnosis_or_prescription(answer, payload.locale)
            model_name = model_result.model
            used_context_turns = context.used_turns

        assistant_message = MessageRecord(
            session_id=session_record.id,
            role="assistant",
            content=json.dumps(answer, ensure_ascii=False),
            risk_level=answer["risk_level"],
            priority=_risk_priority(answer["risk_level"]),
        )
        db.add(assistant_message)

        session_record.locale = payload.locale
        session_record.region_code = payload.region_code
        session_record.latest_risk = answer["risk_level"]

        if _should_refresh_summary(db, session_record.id, profile_changed):
            recent_for_summary = (
                db.execute(
                    select(MessageRecord)
                    .where(MessageRecord.session_id == session_record.id)
                    .order_by(desc(MessageRecord.created_at))
                    .limit(12)
                )
                .scalars()
                .all()
            )
            recent_for_summary = list(reversed(recent_for_summary))
            session_record.summary = build_summary(
                existing_summary=session_record.summary,
                health_profile=session_record.health_profile,
                recent_messages=recent_for_summary,
                locale=payload.locale,
            )

        db.commit()

        response = ChatResponse(
            answer=ChatAnswer(**answer),
            meta=ChatMeta(
                session_id=session_record.id,
                used_context_turns=used_context_turns,
                model=model_name,
            ),
        )
        return response

    @app.get(f"{app_settings.api_prefix}/sessions/{{session_id}}/messages", response_model=MessageListResponse)
    def get_messages(session_id: str, db: Session = Depends(db_dependency)) -> MessageListResponse:
        session_record = db.get(SessionRecord, session_id)
        if not session_record:
            raise HTTPException(status_code=404, detail="Session not found")

        messages = (
            db.execute(
                select(MessageRecord)
                .where(MessageRecord.session_id == session_id)
                .order_by(MessageRecord.created_at.asc(), MessageRecord.id.asc())
            )
            .scalars()
            .all()
        )
        return MessageListResponse(
            session_id=session_id,
            messages=[
                MessageItem(
                    id=m.id,
                    role=m.role,
                    content=m.content,
                    risk_level=m.risk_level,
                    created_at=m.created_at,
                )
                for m in messages
            ],
        )

    @app.get(f"{app_settings.api_prefix}/sessions/{{device_id}}", response_model=SessionListResponse)
    def get_sessions(device_id: str, db: Session = Depends(db_dependency)) -> SessionListResponse:
        sessions = (
            db.execute(
                select(SessionRecord)
                .where(SessionRecord.device_id == device_id)
                .order_by(SessionRecord.updated_at.desc(), SessionRecord.created_at.desc())
            )
            .scalars()
            .all()
        )
        return SessionListResponse(
            sessions=[
                SessionItem(
                    id=s.id,
                    device_id=s.device_id,
                    locale=s.locale,
                    region_code=s.region_code,
                    latest_risk=s.latest_risk,
                    created_at=s.created_at,
                    updated_at=s.updated_at,
                )
                for s in sessions
            ]
        )

    @app.delete(f"{app_settings.api_prefix}/sessions/{{session_id}}")
    def delete_session(session_id: str, db: Session = Depends(db_dependency)) -> dict:
        session_record = db.get(SessionRecord, session_id)
        if not session_record:
            raise HTTPException(status_code=404, detail="Session not found")

        db.delete(session_record)
        db.commit()
        return {"deleted": True, "session_id": session_id}

    return app


def _risk_priority(risk: str) -> int:
    return {"emergency": 100, "high": 80, "medium": 50, "low": 20}.get(risk, 20)


def _get_or_create_session(db: Session, payload: ChatRequest) -> SessionRecord:
    if payload.session_id:
        session_record = db.get(SessionRecord, payload.session_id)
        if not session_record or session_record.device_id != payload.device_id:
            raise HTTPException(status_code=404, detail="Session not found for device")
        return session_record

    session_record = SessionRecord(
        device_id=payload.device_id,
        locale=payload.locale,
        region_code=payload.region_code,
        summary="",
        latest_risk="low",
        triage_stage="intake",
        triage_round_count=0,
        health_profile={},
    )
    db.add(session_record)
    db.flush()
    return session_record


def _merge_profile(session_record: SessionRecord, incoming: dict | None) -> bool:
    if not incoming:
        return False
    existing = session_record.health_profile or {}
    changed = False

    for key, value in incoming.items():
        if value is None:
            continue
        if isinstance(value, list) and not value:
            continue
        if existing.get(key) != value:
            existing[key] = value
            changed = True

    session_record.health_profile = existing
    return changed


def _should_refresh_summary(db: Session, session_id: str, profile_changed: bool) -> bool:
    if profile_changed:
        return True

    assistant_turns = (
        db.execute(
            select(func.count(MessageRecord.id)).where(
                MessageRecord.session_id == session_id,
                MessageRecord.role == "assistant",
            )
        )
        .scalar_one()
    )
    return assistant_turns % 10 == 0


def _ensure_runtime_config_row(db: Session, settings: Settings) -> RuntimeConfig:
    runtime_config = db.get(RuntimeConfig, 1)
    if runtime_config:
        normalized_base_url = normalize_model_base_url(runtime_config.model_base_url)
        if normalized_base_url != runtime_config.model_base_url:
            runtime_config.model_base_url = normalized_base_url
            db.add(runtime_config)
            db.commit()
            db.refresh(runtime_config)
        return runtime_config

    runtime_config = RuntimeConfig(
        id=1,
        model_base_url=normalize_model_base_url(settings.model_base_url),
        model_name=settings.model_name,
        model_api_key=settings.model_api_key,
    )
    db.add(runtime_config)
    db.commit()
    db.refresh(runtime_config)
    return runtime_config


def _sync_adapter_from_runtime(adapter: ModelAdapter, runtime_config: RuntimeConfig) -> None:
    adapter.update_config(
        base_url=runtime_config.model_base_url,
        api_key=runtime_config.model_api_key,
        model_name=runtime_config.model_name,
    )


def _ensure_sessions_triage_columns(engine) -> None:
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("sessions")}
    with engine.begin() as conn:
        if "triage_stage" not in columns:
            conn.execute(text("ALTER TABLE sessions ADD COLUMN triage_stage VARCHAR(16) DEFAULT 'intake'"))
            conn.execute(text("UPDATE sessions SET triage_stage = 'intake' WHERE triage_stage IS NULL"))
        if "triage_round_count" not in columns:
            conn.execute(text("ALTER TABLE sessions ADD COLUMN triage_round_count INTEGER DEFAULT 0"))
            conn.execute(text("UPDATE sessions SET triage_round_count = 0 WHERE triage_round_count IS NULL"))


def _choose_forced_stage(current_stage: str, next_round: int) -> str | None:
    if current_stage == "conclusion":
        return "conclusion"
    if next_round < MIN_TRIAGE_ROUNDS:
        return "intake"
    if next_round >= MAX_TRIAGE_ROUNDS:
        return "conclusion"
    return None


def _apply_stage_rules(answer: dict, locale: str, round_count: int) -> dict:
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


def _build_required_slots(
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


app = create_app()
