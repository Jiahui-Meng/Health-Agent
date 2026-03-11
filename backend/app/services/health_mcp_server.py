from __future__ import annotations

import json
import sys
from typing import Any

from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import build_session_factory, create_engine_for_url
from .triage_runtime import (
    build_health_response_plan,
    build_session_context,
    preview_persist_chat_turn,
    analyze_health_input,
)

SERVER_NAME = "health-agent"
PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "get_session_context",
        "description": "Get the current session summary, recent messages, health profile, and triage state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "device_id": {"type": "string"},
                "locale": {"type": "string"},
            },
            "required": ["session_id", "device_id", "locale"],
            "additionalProperties": False,
        },
    },
    {
        "name": "analyze_health_input",
        "description": "Classify risk, extract risk triggers, and compute missing intake slots for the current user message.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "locale": {"type": "string"},
                "message": {"type": "string"},
                "health_profile": {"type": "object"},
                "recent_messages": {"type": "array"},
            },
            "required": ["locale", "message"],
            "additionalProperties": True,
        },
    },
    {
        "name": "build_health_response_plan",
        "description": "Compute the current triage stage and response constraints based on round count and missing slots.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "locale": {"type": "string"},
                "current_stage": {"type": "string"},
                "current_round_count": {"type": "integer"},
                "required_slots": {"type": "array", "items": {"type": "string"}},
                "risk_level": {"type": "string"},
            },
            "required": ["locale", "current_stage", "current_round_count", "required_slots", "risk_level"],
            "additionalProperties": False,
        },
    },
    {
        "name": "persist_chat_turn",
        "description": "Preview the authoritative persistence outcome for the final structured answer. The host application performs the actual write.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "stage": {"type": "string"},
                "risk_level": {"type": "string"},
            },
            "required": ["session_id", "stage", "risk_level"],
            "additionalProperties": False,
        },
    },
]


def main() -> int:
    settings = get_settings()
    engine = create_engine_for_url(settings.database_url)
    session_factory = build_session_factory(engine)

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        if not isinstance(request, dict):
            continue

        method = request.get("method")
        request_id = request.get("id")
        params = request.get("params") or {}

        try:
            if method == "initialize":
                _write_result(
                    request_id,
                    {
                        "protocolVersion": PROTOCOL_VERSION,
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": SERVER_NAME, "version": "1.0.0"},
                    },
                )
            elif method == "notifications/initialized":
                continue
            elif method == "ping":
                _write_result(request_id, {})
            elif method == "tools/list":
                _write_result(request_id, {"tools": TOOLS})
            elif method == "tools/call":
                result = _handle_tool_call(session_factory(), params)
                _write_result(request_id, {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]})
            else:
                _write_error(request_id, -32601, f"Method not found: {method}")
        except Exception as exc:
            _write_error(request_id, -32000, str(exc))
    return 0


def _handle_tool_call(db: Session, params: dict[str, Any]) -> dict[str, Any]:
    try:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name == "get_session_context":
            context = build_session_context(
                db=db,
                settings=get_settings(),
                session_id=str(arguments["session_id"]),
                device_id=str(arguments["device_id"]),
                locale=str(arguments["locale"]),
            )
            return {
                "session_id": context.session_id,
                "device_id": context.device_id,
                "locale": context.locale,
                "region_code": context.region_code,
                "summary": context.summary,
                "health_profile": context.health_profile,
                "triage_stage": context.triage_stage,
                "triage_round_count": context.triage_round_count,
                "recent_messages": context.recent_messages,
                "used_turns": context.used_turns,
            }
        if name == "analyze_health_input":
            return analyze_health_input(
                locale=str(arguments["locale"]),
                message=str(arguments["message"]),
                health_profile=arguments.get("health_profile") or {},
                recent_messages=arguments.get("recent_messages") or [],
            )
        if name == "build_health_response_plan":
            return build_health_response_plan(
                locale=str(arguments["locale"]),
                current_stage=str(arguments["current_stage"]),
                current_round_count=int(arguments["current_round_count"]),
                required_slots=[str(item) for item in arguments.get("required_slots") or []],
                risk_level=str(arguments["risk_level"]),
            )
        if name == "persist_chat_turn":
            return preview_persist_chat_turn(
                session_id=str(arguments["session_id"]),
                stage=str(arguments["stage"]),
                risk_level=str(arguments["risk_level"]),
            )
        raise ValueError(f"Unknown tool: {name}")
    finally:
        db.close()


def _write_result(request_id: Any, result: dict[str, Any]) -> None:
    payload = {"jsonrpc": "2.0", "id": request_id, "result": result}
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _write_error(request_id: Any, code: int, message: str) -> None:
    payload = {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    raise SystemExit(main())
