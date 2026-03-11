from datetime import datetime
import json
import re
from pathlib import Path
import sys

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
    OAuthActionResponse,
    OAuthStatusResponse,
    SessionItem,
    SessionListResponse,
)
from .services.context_builder import build_context
from .services.model_adapter import ModelAdapter, ModelAPIError, ModelResult, normalize_model_base_url
from .services.codex_cli import CodexCliError, CodexCliService
from .services.output_parser import parse_model_json
from .services.prompt_builder import build_codex_mcp_prompt, build_system_prompt, build_user_prompt
from .services.safety import (
    build_emergency_guidance,
    classify_risk,
    enforce_no_diagnosis_or_prescription,
    max_risk,
)
from .services.summarizer import build_summary
from .services.triage_runtime import (
    apply_stage_rules as runtime_apply_stage_rules,
    build_required_slots as runtime_build_required_slots,
    choose_forced_stage as runtime_choose_forced_stage,
)

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
    app.state.codex_cli_service = CodexCliService(
        cli_bin=app_settings.codex_cli_bin or app_settings.oauth_cli_bin or "codex",
        python_bin=sys.executable,
        workspace_root=str(Path(__file__).resolve().parents[2]),
        backend_root=str(Path(__file__).resolve().parents[1]),
        database_url=app_settings.database_url,
    )

    @app.on_event("startup")
    def startup() -> None:
        Base.metadata.create_all(bind=engine)
        _ensure_sessions_triage_columns(engine)
        _ensure_runtime_config_columns(engine)

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
        codex_status = app.state.codex_cli_service.status()
        mcp_available, mcp_message = app.state.codex_cli_service.mcp_status()
        configured = _is_model_configured(runtime_config, codex_status.logged_in, mcp_available)
        return ModelConfigStatusResponse(
            configured=configured,
            base_url=runtime_config.model_base_url,
            model_name=runtime_config.model_name,
            provider_mode=runtime_config.provider_mode,
            oauth_cli_available=codex_status.cli_available,
            oauth_logged_in=codex_status.logged_in,
            oauth_status_message=codex_status.message,
            oauth_account_id=codex_status.account_id,
            mcp_available=mcp_available,
            mcp_status_message=mcp_message,
        )

    @app.post(f"{app_settings.api_prefix}/model-config", response_model=ModelConfigResponse)
    def save_model_config(payload: ModelConfigRequest, db: Session = Depends(db_dependency)) -> ModelConfigResponse:
        runtime_config = _ensure_runtime_config_row(db, app_settings)
        if payload.base_url.strip():
            runtime_config.model_base_url = normalize_model_base_url(payload.base_url)
        if payload.model_name.strip():
            runtime_config.model_name = payload.model_name.strip()
        normalized_provider = _normalize_provider_mode(payload.provider_mode)
        runtime_config.provider_mode = normalized_provider
        if normalized_provider == "http_api":
            runtime_config.model_api_key = payload.api_key.strip()
        elif payload.api_key.strip():
            # allow optional manual override
            runtime_config.model_api_key = payload.api_key.strip()

        db.add(runtime_config)
        db.commit()
        db.refresh(runtime_config)
        codex_status = app.state.codex_cli_service.status()
        mcp_available, _ = app.state.codex_cli_service.mcp_status()
        return ModelConfigResponse(
            configured=_is_model_configured(runtime_config, codex_status.logged_in, mcp_available),
            base_url=runtime_config.model_base_url,
            model_name=runtime_config.model_name,
            provider_mode=runtime_config.provider_mode,
        )

    @app.get(f"{app_settings.api_prefix}/auth/oauth/status", response_model=OAuthStatusResponse)
    def oauth_status() -> OAuthStatusResponse:
        status = app.state.codex_cli_service.status()
        mcp_available, mcp_message = app.state.codex_cli_service.mcp_status()
        return OAuthStatusResponse(
            provider="codex",
            cli_available=status.cli_available,
            logged_in=status.logged_in,
            status_message=status.message,
            account_id=status.account_id,
            mcp_available=mcp_available,
            mcp_status_message=mcp_message,
        )

    @app.post(f"{app_settings.api_prefix}/auth/oauth/login/start", response_model=OAuthActionResponse)
    def oauth_login() -> OAuthActionResponse:
        result = app.state.codex_cli_service.login()
        status_code = 200 if result.ok else 502
        if not result.ok:
            raise HTTPException(status_code=status_code, detail=result.message)
        return OAuthActionResponse(ok=result.ok, message=result.message)

    @app.post(f"{app_settings.api_prefix}/auth/oauth/logout", response_model=OAuthActionResponse)
    def oauth_logout() -> OAuthActionResponse:
        result = app.state.codex_cli_service.logout()
        status_code = 200 if result.ok else 502
        if not result.ok:
            raise HTTPException(status_code=status_code, detail=result.message)
        return OAuthActionResponse(ok=result.ok, message=result.message)

    @app.post(f"{app_settings.api_prefix}/chat", response_model=ChatResponse)
    def chat(payload: ChatRequest, db: Session = Depends(db_dependency)) -> ChatResponse:
        runtime_config = _ensure_runtime_config_row(db, app_settings)
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
            provider = _normalize_provider_mode(runtime_config.provider_mode)
            system_prompt = build_system_prompt(payload.locale, target_stage)
            if provider == "codex_cli":
                user_prompt = build_codex_mcp_prompt(
                    locale=payload.locale,
                    session_id=session_record.id,
                    device_id=payload.device_id,
                    message=payload.message,
                    triage_stage=target_stage,
                    triage_round_count=next_round,
                    max_rounds=MAX_TRIAGE_ROUNDS,
                )
            else:
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
                model_result = _generate_model_result(
                    runtime_config=runtime_config,
                    codex_cli_service=app.state.codex_cli_service,
                    model_adapter=app.state.model_adapter,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    locale=payload.locale,
                )
            except (ModelAPIError, CodexCliError) as exc:
                raise HTTPException(
                    status_code=getattr(exc, "status_code", 502),
                    detail={
                        "message": str(exc),
                        "hint": "Please verify provider mode, Codex login status, model name, MCP availability, Base URL, and credentials.",
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
        if not runtime_config.provider_mode:
            runtime_config.provider_mode = settings.provider_mode
            db.add(runtime_config)
            db.commit()
            db.refresh(runtime_config)
        normalized_provider = _normalize_provider_mode(runtime_config.provider_mode)
        if normalized_provider != runtime_config.provider_mode:
            runtime_config.provider_mode = normalized_provider
            db.add(runtime_config)
            db.commit()
            db.refresh(runtime_config)
        if runtime_config.provider_mode == "codex_cli" and runtime_config.model_name in {"", "gpt-4.1-mini"}:
            runtime_config.model_name = "gpt-5.4"
            db.add(runtime_config)
            db.commit()
            db.refresh(runtime_config)
        return runtime_config

    runtime_config = RuntimeConfig(
        id=1,
        model_base_url=normalize_model_base_url(settings.model_base_url),
        model_name="gpt-5.4" if _normalize_provider_mode(settings.provider_mode) == "codex_cli" else settings.model_name,
        model_api_key=settings.model_api_key,
        provider_mode=_normalize_provider_mode(settings.provider_mode),
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


def _sync_adapter_with_token(adapter: ModelAdapter, runtime_config: RuntimeConfig, token: str) -> None:
    adapter.update_config(
        base_url=runtime_config.model_base_url,
        api_key=token,
        model_name=runtime_config.model_name,
    )


def _is_model_configured(runtime_config: RuntimeConfig, codex_logged_in: bool, mcp_available: bool = True) -> bool:
    provider = _normalize_provider_mode(runtime_config.provider_mode)
    if provider == "codex_cli":
        return codex_logged_in and mcp_available
    return bool(runtime_config.model_api_key.strip())


def _normalize_provider_mode(provider_mode: str | None) -> str:
    normalized = (provider_mode or "").strip().lower()
    if normalized == "oauth_cli":
        return "codex_cli"
    if normalized in {"codex_cli", "http_api"}:
        return normalized
    return "codex_cli"


def _generate_model_result(
    runtime_config: RuntimeConfig,
    codex_cli_service: CodexCliService,
    model_adapter: ModelAdapter,
    messages: list[dict[str, str]],
    locale: str,
):
    provider = _normalize_provider_mode(runtime_config.provider_mode)

    if provider == "http_api":
        if not runtime_config.model_api_key.strip():
            raise ModelAPIError(
                "HTTP API mode requires API Key (Token). Please save model config first.",
                status_code=400,
            )
        _sync_adapter_with_token(model_adapter, runtime_config, runtime_config.model_api_key)
        return model_adapter.generate(messages=messages, locale=locale)

    status = codex_cli_service.status()
    if not status.cli_available:
        raise CodexCliError(status.message, status_code=400)
    if not status.logged_in:
        raise CodexCliError("Codex CLI is not logged in. Please run login first.", status_code=401)

    prompt_blocks: list[str] = []
    for msg in messages:
        role = msg.get("role", "user").upper()
        content = msg.get("content", "")
        prompt_blocks.append(f"{role}:\n{content}")
    prompt_text = "\n\n".join(prompt_blocks).strip()
    content = codex_cli_service.exec_with_mcp(
        prompt=prompt_text,
        model_name=runtime_config.model_name or None,
    )

    return ModelResult(content=content, model=runtime_config.model_name or "codex-cli")


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


def _ensure_runtime_config_columns(engine) -> None:
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("runtime_configs")}
    with engine.begin() as conn:
        if "provider_mode" not in columns:
            conn.execute(text("ALTER TABLE runtime_configs ADD COLUMN provider_mode VARCHAR(16) DEFAULT 'codex_cli'"))
            conn.execute(text("UPDATE runtime_configs SET provider_mode = 'codex_cli' WHERE provider_mode IS NULL"))
        conn.execute(text("UPDATE runtime_configs SET provider_mode = 'codex_cli' WHERE provider_mode = 'oauth_cli'"))
        conn.execute(
            text(
                "UPDATE runtime_configs SET model_name = 'gpt-5.4' "
                "WHERE provider_mode = 'codex_cli' AND (model_name IS NULL OR model_name = '' OR model_name = 'gpt-4.1-mini')"
            )
        )


def _choose_forced_stage(current_stage: str, next_round: int) -> str | None:
    return runtime_choose_forced_stage(current_stage, next_round)


def _apply_stage_rules(answer: dict, locale: str, round_count: int) -> dict:
    return runtime_apply_stage_rules(answer, locale, round_count)


def _build_required_slots(
    locale: str,
    current_message: str,
    health_profile: dict,
    recent_messages: list[dict[str, str]],
) -> list[str]:
    return runtime_build_required_slots(locale, current_message, health_profile, recent_messages)


app = create_app()
