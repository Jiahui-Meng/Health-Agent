import json
import re
from types import SimpleNamespace

from app.services.model_adapter import ModelAPIError, ModelResult


HTTP_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
HTTP_MODEL_NAME = "glm-4.7-flash"
OAUTH_DEFAULT_BASE_URL = "https://api.openai.com/v1"
OAUTH_DEFAULT_MODEL_NAME = "gpt-5.4"


def _configure_model(client):
    update = client.post(
        "/api/v1/model-config",
        json={
            "base_url": HTTP_BASE_URL,
            "provider_mode": "http_api",
            "api_key": "test-key",
            "model_name": HTTP_MODEL_NAME,
        },
    )
    assert update.status_code == 200


def _mock_model_success(client):
    def fake_generate(messages, locale):
        del messages, locale
        return ModelResult(
            content=json.dumps(
                {
                    "summary": "建议继续观察并安排线下评估。",
                    "risk_level": "medium",
                    "next_steps": [
                        "记录症状变化和持续时长。",
                        "若症状加重，尽快线下就诊。",
                    ],
                    "emergency_guidance": None,
                    "disclaimer": "本回答仅用于健康信息参考，不能替代医生诊疗。",
                    "stage": "conclusion",
                },
                ensure_ascii=False,
            ),
            model=HTTP_MODEL_NAME,
        )

    client.app.state.model_adapter.generate = fake_generate

    def fake_generate_text(messages, locale):
        del messages, locale
        return ModelResult(
            content=(
                "# 用户健康报告\n\n"
                "## 用户概况\n"
                "- 当前已有多次问诊记录。\n\n"
                "## 近期症状演化\n"
                "- 近期以发烧和咳嗽为主。\n\n"
                "## 当前总体建议\n"
                "- 建议继续观察并按需线下就医。"
            ),
            model=HTTP_MODEL_NAME,
        )

    client.app.state.model_adapter.generate_text = fake_generate_text


def _create_user(client, username="alice"):
    response = client.post(
        "/api/v1/users",
        json={
            "username": username,
            "locale": "zh-CN",
            "region_code": "HK",
            "birth_year": "1990",
            "sex": "女",
            "conditions": ["哮喘"],
            "medications": ["吸入剂"],
            "allergies": ["青霉素"],
        },
    )
    assert response.status_code == 200
    return response.json()


def test_create_user_rejects_missing_or_invalid_sex(client):
    response = client.post(
        "/api/v1/users",
        json={
            "username": "invalid-sex-user",
            "locale": "zh-CN",
            "region_code": "HK",
            "birth_year": "1990",
            "sex": "",
            "conditions": [],
            "medications": [],
            "allergies": [],
        },
    )
    assert response.status_code == 422
    assert "male/female" in response.text


def test_chat_flow_and_session_history(client):
    _configure_model(client)
    _mock_model_success(client)

    payload = {
        "device_id": "device-001",
        "locale": "zh-CN",
        "region_code": "HK",
        "message": "我这两天咳嗽，有点头晕",
        "health_profile": {
            "age_range": "30-39",
            "conditions": ["哮喘"],
            "allergies": ["青霉素"],
            "symptom_duration": "2天",
        },
    }

    first = client.post("/api/v1/chat", json=payload)
    assert first.status_code == 200
    data1 = first.json()
    assert data1["answer"]["risk_level"] in {"low", "medium", "high", "emergency"}
    assert data1["answer"]["stage"] in {"intake", "conclusion"}
    if data1["answer"]["stage"] == "conclusion":
        assert isinstance(data1["answer"].get("advice_sections"), dict)
    assert data1["meta"]["session_id"]

    session_id = data1["meta"]["session_id"]

    payload2 = {
        "device_id": "device-001",
        "locale": "zh-CN",
        "region_code": "HK",
        "message": "今天比昨天更严重，夜里咳醒",
        "session_id": session_id,
    }
    second = client.post("/api/v1/chat", json=payload2)
    assert second.status_code == 200

    sessions = client.get("/api/v1/sessions/device-001")
    assert sessions.status_code == 200
    assert len(sessions.json()["sessions"]) == 1

    messages = client.get(f"/api/v1/sessions/{session_id}/messages")
    assert messages.status_code == 200
    assert len(messages.json()["messages"]) == 4


def test_user_crud_and_graph_flow(client):
    user = _create_user(client, "graph-user")
    assert user["conditions"] == ["哮喘"]

    listed = client.get("/api/v1/users")
    assert listed.status_code == 200
    assert listed.json()["users"][0]["id"] == user["id"]

    updated = client.patch(
        f"/api/v1/users/{user['id']}",
        json={"allergies": ["青霉素", "花粉"], "mark_active": True},
    )
    assert updated.status_code == 200
    assert "花粉" in updated.json()["allergies"]

    graph = client.get(f"/api/v1/users/{user['id']}/graph")
    assert graph.status_code == 200
    graph_data = graph.json()
    assert graph_data["summary_bundle"]["persistent_features"]["conditions"] == ["哮喘"]
    assert "HK" in graph_data["summary_bundle"]["profile_highlights"]
    assert len(graph_data["nodes"]) >= 1


def test_chat_with_user_id_writes_sessions_and_graph(client):
    _configure_model(client)
    _mock_model_success(client)
    user = _create_user(client, "session-user")

    response = client.post(
        "/api/v1/chat",
        json={
            "user_id": user["id"],
            "device_id": "device-session-user",
            "locale": "zh-CN",
            "region_code": "HK",
            "message": "我今天发烧、咳嗽，晚上更明显",
            "health_profile": {
                "age_range": "出生年份: 1990",
                "conditions": ["哮喘"],
                "allergies": ["青霉素"],
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["user_id"] == user["id"]
    if data["answer"]["stage"] == "conclusion":
        assert isinstance(data["answer"].get("advice_sections"), dict)
        assert data["answer"]["advice_sections"]["monitoring_guidance"] is not None

    sessions = client.get(f"/api/v1/users/{user['id']}/sessions")
    assert sessions.status_code == 200
    assert len(sessions.json()["sessions"]) == 1
    assert sessions.json()["sessions"][0]["user_id"] == user["id"]

    graph = client.get(f"/api/v1/users/{user['id']}/graph")
    assert graph.status_code == 200
    graph_data = graph.json()
    node_types = {node["node_type"] for node in graph_data["nodes"]}
    assert "session" in node_types
    assert "summary" in node_types
    assert len(graph_data["summary_bundle"]["recent_journey"]) >= 1
    assert graph_data["summary_bundle"]["recent_journey"][0]["is_current_session"] is True
    assert isinstance(graph_data["summary_bundle"]["risk_signals"], list)
    if data["answer"]["stage"] == "conclusion":
        assert len(graph_data["summary_bundle"]["risk_signals"]) >= 1


def test_chat_rejects_user_without_sex(client):
    imported = client.post(
        "/api/v1/users/import-legacy",
        json={
            "profiles": [
                {
                    "username": "legacy-no-sex",
                    "locale": "zh-CN",
                    "region_code": "HK",
                    "birth_year": "1988",
                    "sex": "",
                    "conditions": [],
                    "medications": [],
                    "allergies": [],
                }
            ]
        },
    )
    assert imported.status_code == 200
    user = imported.json()["users"][0]

    response = client.post(
        "/api/v1/chat",
        json={
            "user_id": user["id"],
            "device_id": "device-no-sex",
            "locale": "zh-CN",
            "region_code": "HK",
            "message": "我这两天咳嗽",
        },
    )
    assert response.status_code == 422
    assert "sex is required" in response.text.lower()


def test_male_user_response_removes_menstruation_questions(client):
    _configure_model(client)
    user = _create_user(client, "male-safe-user")
    client.patch(f"/api/v1/users/{user['id']}", json={"sex": "男"})

    def mismatched_generate(messages, locale):
        del messages, locale
        return ModelResult(
            content=json.dumps(
                {
                    "summary": "我先确认一下最近一次月经和是否怀孕。",
                    "risk_level": "medium",
                    "next_steps": [],
                    "emergency_guidance": None,
                    "disclaimer": "本回答仅用于健康信息参考，不能替代医生诊疗。",
                    "stage": "intake",
                    "follow_up_questions": ["最近一次月经是什么时候？", "有没有怀孕可能？"],
                },
                ensure_ascii=False,
            ),
            model=HTTP_MODEL_NAME,
        )

    client.app.state.model_adapter.generate = mismatched_generate

    response = client.post(
        "/api/v1/chat",
        json={
            "user_id": user["id"],
            "device_id": "device-male-safe-user",
            "locale": "zh-CN",
            "region_code": "HK",
            "message": "我最近咳嗽和发烧",
        },
    )
    assert response.status_code == 200
    data = response.json()["answer"]
    assert data["stage"] == "intake"
    assert "月经" not in data["summary"]
    assert all("月经" not in item and "怀孕" not in item for item in data["follow_up_questions"])


def test_intake_chat_does_not_write_risk_signal_to_graph(client):
    _configure_model(client)
    user = _create_user(client, "intake-user")

    def intake_generate(messages, locale):
        del messages, locale
        return ModelResult(
            content=json.dumps(
                {
                    "summary": "我想先确认几个细节。",
                    "risk_level": "medium",
                    "next_steps": [],
                    "emergency_guidance": None,
                    "disclaimer": "本回答仅用于健康信息参考，不能替代医生诊疗。",
                    "stage": "intake",
                    "follow_up_questions": ["症状是突然出现还是逐渐加重的？"],
                },
                ensure_ascii=False,
            ),
            model=HTTP_MODEL_NAME,
        )

    client.app.state.model_adapter.generate = intake_generate

    response = client.post(
        "/api/v1/chat",
        json={
            "user_id": user["id"],
            "device_id": "device-intake-user",
            "locale": "zh-CN",
            "region_code": "HK",
            "message": "我今天头痛，晚上更明显",
        },
    )
    assert response.status_code == 200
    assert response.json()["answer"]["stage"] == "intake"
    assert response.json()["answer"]["advice_sections"] is None

    graph = client.get(f"/api/v1/users/{user['id']}/graph")
    assert graph.status_code == 200
    assert graph.json()["summary_bundle"]["risk_signals"] == []


def test_import_legacy_users_when_backend_empty(client):
    imported = client.post(
        "/api/v1/users/import-legacy",
        json={
            "profiles": [
                {
                    "username": "legacy-user",
                    "locale": "zh-CN",
                    "region_code": "HK",
                    "birth_year": "1988",
                    "sex": "男",
                    "conditions": ["高血压"],
                    "medications": ["氨氯地平"],
                    "allergies": [],
                }
            ],
            "active_username": "legacy-user",
        },
    )
    assert imported.status_code == 200
    assert imported.json()["users"][0]["username"] == "legacy-user"


def test_export_user_markdown_report(client):
    _configure_model(client)
    _mock_model_success(client)
    user = _create_user(client, "export-user")

    chat = client.post(
        "/api/v1/chat",
        json={
            "user_id": user["id"],
            "device_id": "device-export-user",
            "locale": "zh-CN",
            "region_code": "HK",
            "message": "我今天发烧、咳嗽",
        },
    )
    assert chat.status_code == 200

    exported = client.get(f"/api/v1/users/{user['id']}/export?format=markdown")
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/markdown")
    body = exported.text
    assert "# 用户健康报告" in body
    assert "## 当前总体建议" in body
    assert "## Raw Transcript Appendix" in body


def test_export_user_markdown_report_returns_error_when_provider_unavailable(client):
    user = _create_user(client, "export-no-model-user")
    client.post(
        "/api/v1/model-config",
        json={
            "base_url": HTTP_BASE_URL,
            "provider_mode": "http_api",
            "api_key": "",
            "model_name": HTTP_MODEL_NAME,
        },
    )
    exported = client.get(f"/api/v1/users/{user['id']}/export?format=markdown")
    assert exported.status_code == 400


def test_model_config_setup_flow(client):
    status_before = client.get("/api/v1/model-config/status")
    assert status_before.status_code == 200
    assert isinstance(status_before.json()["configured"], bool)
    assert status_before.json()["base_url"] == OAUTH_DEFAULT_BASE_URL
    assert status_before.json()["model_name"] == OAUTH_DEFAULT_MODEL_NAME
    assert status_before.json()["provider_mode"] == "codex_cli"
    assert "mcp_available" in status_before.json()

    update = client.post(
        "/api/v1/model-config",
        json={
            "base_url": HTTP_BASE_URL,
            "provider_mode": "http_api",
            "api_key": "test-key",
            "model_name": HTTP_MODEL_NAME,
        },
    )
    assert update.status_code == 200
    assert update.json()["configured"] is True

    status_after = client.get("/api/v1/model-config/status")
    assert status_after.status_code == 200
    assert status_after.json()["configured"] is True
    assert status_after.json()["model_name"] == HTTP_MODEL_NAME


def test_model_config_normalizes_chat_completions_suffix(client):
    update = client.post(
        "/api/v1/model-config",
        json={
            "base_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
            "provider_mode": "http_api",
            "api_key": "test-key",
            "model_name": HTTP_MODEL_NAME,
        },
    )
    assert update.status_code == 200
    assert update.json()["base_url"] == HTTP_BASE_URL

    status = client.get("/api/v1/model-config/status")
    assert status.status_code == 200
    assert status.json()["base_url"] == HTTP_BASE_URL


def test_model_config_maps_legacy_oauth_cli_to_codex_cli(client):
    update = client.post(
        "/api/v1/model-config",
        json={
            "provider_mode": "oauth_cli",
            "base_url": OAUTH_DEFAULT_BASE_URL,
            "model_name": OAUTH_DEFAULT_MODEL_NAME,
        },
    )
    assert update.status_code == 200
    assert update.json()["provider_mode"] == "codex_cli"


def test_model_config_migrates_old_codex_default_model(client):
    update = client.post(
        "/api/v1/model-config",
        json={
            "provider_mode": "codex_cli",
            "base_url": OAUTH_DEFAULT_BASE_URL,
            "model_name": "gpt-4.1-mini",
        },
    )
    assert update.status_code == 200

    status = client.get("/api/v1/model-config/status")
    assert status.status_code == 200
    assert status.json()["model_name"] == "gpt-5.4"


def test_model_call_failure_returns_clear_error(client):
    _configure_model(client)

    def fail_generate(messages, locale):
        del messages, locale
        raise ModelAPIError(
            "Model API authentication failed. Please verify API Key (Token). Upstream detail: invalid token",
            status_code=502,
        )

    client.app.state.model_adapter.generate = fail_generate

    response = client.post(
        "/api/v1/chat",
        json={
            "device_id": "device-004",
            "locale": "en-US",
            "region_code": "US",
            "message": "mild headache for two days",
        },
    )
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "authentication failed" in detail["message"].lower()
    assert "hint" in detail


def test_codex_cli_chat_failure_surfaces_mcp_hint(client):
    def fake_status():
        return SimpleNamespace(cli_available=True, logged_in=True, message="Logged in", account_id=None)

    def fake_mcp_status():
        return True, "MCP server is ready."

    def fail_exec(prompt, model_name, timeout_seconds=90):
        del prompt, model_name, timeout_seconds
        from app.services.codex_cli import CodexCliError

        raise CodexCliError("MCP server/tool error: tool call failed", status_code=502)

    client.app.state.codex_cli_service.status = fake_status
    client.app.state.codex_cli_service.mcp_status = fake_mcp_status
    client.app.state.codex_cli_service.exec_with_mcp = fail_exec

    response = client.post(
        "/api/v1/chat",
        json={
            "device_id": "device-codex-001",
            "locale": "en-US",
            "region_code": "US",
            "message": "mild headache for two days",
        },
    )
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "mcp" in detail["message"].lower()
    assert "mcp availability" in detail["hint"].lower()


def test_emergency_triage(client):
    payload = {
        "device_id": "device-002",
        "locale": "en-US",
        "region_code": "US",
        "message": "I have chest pain and shortness of breath",
    }
    response = client.post("/api/v1/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["answer"]["risk_level"] == "emergency"
    assert data["answer"]["stage"] == "conclusion"
    assert "911" in data["answer"]["emergency_guidance"]
    assert "visit_guidance" in data["answer"]["advice_sections"]
    assert data["answer"]["advice_sections"]["exercise_guidance"] is None


def test_delete_session(client):
    _configure_model(client)
    _mock_model_success(client)

    payload = {
        "device_id": "device-003",
        "locale": "en-US",
        "region_code": "US",
        "message": "mild headache",
    }
    response = client.post("/api/v1/chat", json=payload)
    session_id = response.json()["meta"]["session_id"]

    deleted = client.delete(f"/api/v1/sessions/{session_id}")
    assert deleted.status_code == 200

    check = client.get(f"/api/v1/sessions/{session_id}/messages")
    assert check.status_code == 404


def test_delete_session_removes_graph_subtree(client):
    _configure_model(client)
    _mock_model_success(client)
    user = _create_user(client, "delete-graph-user")

    response = client.post(
        "/api/v1/chat",
        json={
            "user_id": user["id"],
            "device_id": "device-delete-graph-user",
            "locale": "zh-CN",
            "region_code": "HK",
            "message": "我今天发烧、咳嗽",
        },
    )
    assert response.status_code == 200
    session_id = response.json()["meta"]["session_id"]

    graph_before = client.get(f"/api/v1/users/{user['id']}/graph")
    assert graph_before.status_code == 200
    assert any(node["node_type"] == "session" and node["label"] == session_id for node in graph_before.json()["nodes"])

    deleted = client.delete(f"/api/v1/sessions/{session_id}")
    assert deleted.status_code == 200

    graph_after = client.get(f"/api/v1/users/{user['id']}/graph")
    assert graph_after.status_code == 200
    assert not any(node["node_type"] == "session" and node["label"] == session_id for node in graph_after.json()["nodes"])
    assert all(item["session_id"] != session_id for item in graph_after.json()["summary_bundle"]["recent_journey"])
    assert all(item["session_id"] != session_id for item in graph_after.json()["summary_bundle"]["risk_signals"])


def test_export_report_excludes_deleted_sessions(client):
    _configure_model(client)
    _mock_model_success(client)
    user = _create_user(client, "delete-export-user")

    first = client.post(
        "/api/v1/chat",
        json={
            "user_id": user["id"],
            "device_id": "device-delete-export-user",
            "locale": "zh-CN",
            "region_code": "HK",
            "message": "第一段历史：我昨天发烧咳嗽",
        },
    )
    assert first.status_code == 200
    first_session_id = first.json()["meta"]["session_id"]

    second = client.post(
        "/api/v1/chat",
        json={
            "user_id": user["id"],
            "device_id": "device-delete-export-user-2",
            "locale": "zh-CN",
            "region_code": "HK",
            "message": "第二段历史：我今天腹泻腹痛",
        },
    )
    assert second.status_code == 200
    second_session_id = second.json()["meta"]["session_id"]

    deleted = client.delete(f"/api/v1/sessions/{first_session_id}")
    assert deleted.status_code == 200

    exported = client.get(f"/api/v1/users/{user['id']}/export?format=markdown")
    assert exported.status_code == 200
    body = exported.text
    assert first_session_id not in body
    assert "第一段历史" not in body
    assert second_session_id in body
    assert "第二段历史" in body


def test_graph_reconcile_backfills_history_for_existing_sessions(client):
    _configure_model(client)
    _mock_model_success(client)
    user = _create_user(client, "reconcile-user")

    payload = {
        "user_id": user["id"],
        "device_id": "device-reconcile-user",
        "locale": "zh-CN",
        "region_code": "HK",
        "message": "我最近发烧、咳嗽，晚上更明显",
    }
    session_id = None
    final_data = None
    for idx in range(3):
        if session_id:
            payload["session_id"] = session_id
            payload["message"] = "补充一点：现在还是咳嗽，晚上更明显。"
        response = client.post("/api/v1/chat", json=payload)
        assert response.status_code == 200
        final_data = response.json()
        session_id = final_data["meta"]["session_id"]

    assert final_data is not None
    assert final_data["answer"]["stage"] == "conclusion"

    with client.app.state.session_factory() as db:
        from sqlalchemy import delete, select

        from app.models import UserGraphEdgeRecord, UserGraphNodeRecord

        node_ids = {
            node.id
            for node in db.execute(
                select(UserGraphNodeRecord).where(UserGraphNodeRecord.user_id == user["id"])
            ).scalars()
            if (node.node_type == "session" and node.label == session_id)
            or str((node.payload or {}).get("session_id") or "") == session_id
        }
        if node_ids:
            db.execute(
                delete(UserGraphEdgeRecord).where(
                    UserGraphEdgeRecord.user_id == user["id"],
                    (UserGraphEdgeRecord.from_node_id.in_(node_ids)) | (UserGraphEdgeRecord.to_node_id.in_(node_ids)),
                )
            )
            db.execute(delete(UserGraphNodeRecord).where(UserGraphNodeRecord.id.in_(node_ids)))
            db.commit()

    graph = client.get(f"/api/v1/users/{user['id']}/graph")
    assert graph.status_code == 200
    payload = graph.json()
    assert any(node["node_type"] == "session" and node["label"] == session_id for node in payload["nodes"])
    assert len(payload["summary_bundle"]["recent_journey"]) >= 1
    assert len(payload["summary_bundle"]["risk_signals"]) >= 1


def test_graph_builds_condition_to_session_association_edges(client):
    _configure_model(client)
    _mock_model_success(client)
    response = client.post(
        "/api/v1/users",
        json={
            "username": "association-heart-user",
            "locale": "zh-CN",
            "region_code": "HK",
            "birth_year": "1992",
            "sex": "男",
            "conditions": ["先天性心脏病"],
            "medications": [],
            "allergies": [],
        },
    )
    assert response.status_code == 200
    user = response.json()

    chat = client.post(
        "/api/v1/chat",
        json={
            "user_id": user["id"],
            "device_id": "device-association-heart-user",
            "locale": "zh-CN",
            "region_code": "HK",
            "message": "我这两天胸痛，而且会气短。",
        },
    )
    assert chat.status_code == 200

    graph = client.get(f"/api/v1/users/{user['id']}/graph")
    assert graph.status_code == 200
    association_edges = [
        edge
        for edge in graph.json()["edges"]
        if edge["edge_type"] in {"POSSIBLY_RELATED_TO", "POSSIBLY_EXPLAINED_BY"}
    ]
    assert association_edges
    assert any("condition:cardiac" in edge["payload"].get("rule_keys", []) for edge in association_edges)
    assert any(edge["payload"].get("confidence") in {"medium", "high"} for edge in association_edges)


def test_graph_builds_cycle_association_for_female_only(client):
    _configure_model(client)
    _mock_model_success(client)

    female = _create_user(client, "female-cycle-user")
    first = client.post(
        "/api/v1/chat",
        json={
            "user_id": female["id"],
            "device_id": "device-female-cycle-user-1",
            "locale": "zh-CN",
            "region_code": "HK",
            "message": "上个月肚子疼，这个月来月经前还是肚子疼。",
        },
    )
    assert first.status_code == 200
    second = client.post(
        "/api/v1/chat",
        json={
            "user_id": female["id"],
            "device_id": "device-female-cycle-user-2",
            "locale": "zh-CN",
            "region_code": "HK",
            "message": "这个月肚子还是疼，和生理期差不多同时出现。",
        },
    )
    assert second.status_code == 200

    female_graph = client.get(f"/api/v1/users/{female['id']}/graph")
    assert female_graph.status_code == 200
    female_cycle_edges = [
        edge for edge in female_graph.json()["edges"] if edge["edge_type"] == "POSSIBLY_CYCLE_RELATED"
    ]
    assert female_cycle_edges

    male_response = client.post(
        "/api/v1/users",
        json={
            "username": "male-cycle-user",
            "locale": "zh-CN",
            "region_code": "HK",
            "birth_year": "1991",
            "sex": "男",
            "conditions": [],
            "medications": [],
            "allergies": [],
        },
    )
    assert male_response.status_code == 200
    male = male_response.json()
    client.post(
        "/api/v1/chat",
        json={
            "user_id": male["id"],
            "device_id": "device-male-cycle-user-1",
            "locale": "zh-CN",
            "region_code": "HK",
            "message": "上个月肚子疼，这个月还是肚子疼。",
        },
    )
    client.post(
        "/api/v1/chat",
        json={
            "user_id": male["id"],
            "device_id": "device-male-cycle-user-2",
            "locale": "zh-CN",
            "region_code": "HK",
            "message": "这个月肚子还是疼，和上个月差不多。",
        },
    )
    male_graph = client.get(f"/api/v1/users/{male['id']}/graph")
    assert male_graph.status_code == 200
    assert not any(edge["edge_type"] == "POSSIBLY_CYCLE_RELATED" for edge in male_graph.json()["edges"])


def test_delete_session_removes_association_edges(client):
    _configure_model(client)
    _mock_model_success(client)
    user = _create_user(client, "delete-association-user")

    first = client.post(
        "/api/v1/chat",
        json={
            "user_id": user["id"],
            "device_id": "device-delete-association-1",
            "locale": "zh-CN",
            "region_code": "HK",
            "message": "上个月肚子疼，这个月来月经前还是肚子疼。",
        },
    )
    second = client.post(
        "/api/v1/chat",
        json={
            "user_id": user["id"],
            "device_id": "device-delete-association-2",
            "locale": "zh-CN",
            "region_code": "HK",
            "message": "这个月肚子还是疼，和生理期差不多同时出现。",
        },
    )
    assert first.status_code == 200
    assert second.status_code == 200
    first_session_id = first.json()["meta"]["session_id"]

    graph_before = client.get(f"/api/v1/users/{user['id']}/graph")
    assert graph_before.status_code == 200
    assert any(edge["edge_type"] == "POSSIBLY_CYCLE_RELATED" for edge in graph_before.json()["edges"])

    deleted = client.delete(f"/api/v1/sessions/{first_session_id}")
    assert deleted.status_code == 200

    graph_after = client.get(f"/api/v1/users/{user['id']}/graph")
    assert graph_after.status_code == 200
    assert all(
        first_session_id not in edge["payload"].get("source_session_ids", [])
        for edge in graph_after.json()["edges"]
        if edge["edge_type"].startswith("POSSIBLY_")
    )


def test_run_association_analysis_writes_model_edges(client):
    _configure_model(client)
    _mock_model_success(client)
    user = _create_user(client, "analysis-user")

    chat = client.post(
        "/api/v1/chat",
        json={
            "user_id": user["id"],
            "device_id": "device-analysis-user",
            "locale": "zh-CN",
            "region_code": "HK",
            "message": "我最近胸痛，而且容易气短。",
        },
    )
    assert chat.status_code == 200
    session_id = chat.json()["meta"]["session_id"]
    def analysis_generate_text(messages, locale):
        del locale
        prompt = "\n".join(message["content"] for message in messages)
        assert session_id in prompt
        context = json.loads(re.search(r"\{.*\}", messages[-1]["content"], flags=re.DOTALL).group(0))
        condition_node_id = next(node["id"] for node in context["graph"]["nodes"] if node["node_type"] == "condition")
        session_node_id = next(
            node["id"] for node in context["graph"]["nodes"] if node["node_type"] == "session" and node["label"] == session_id
        )
        return ModelResult(
            content=json.dumps(
                {
                    "rows": [
                        {
                            "from_ref": condition_node_id,
                            "to_ref": session_node_id,
                            "association_type": "possibly_explained_by",
                            "confidence": "high",
                            "evidence_summary": "先天性心脏病与当前胸痛、气短在同一会话中再次出现，值得重点关联。",
                            "source_session_ids": [session_id],
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            model=HTTP_MODEL_NAME,
        )

    client.app.state.model_adapter.generate_text = analysis_generate_text

    response = client.post(f"/api/v1/users/{user['id']}/association-analysis")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["written_edges_count"] == 1
    assert data["rows"][0]["association_type"] == "possibly_explained_by"

    graph = client.get(f"/api/v1/users/{user['id']}/graph")
    assert graph.status_code == 200
    assert any(edge["edge_type"] == "MODEL_POSSIBLY_EXPLAINED_BY" for edge in graph.json()["edges"])


def test_delete_session_removes_model_analysis_edges(client):
    _configure_model(client)
    _mock_model_success(client)
    user = _create_user(client, "analysis-delete-user")

    chat = client.post(
        "/api/v1/chat",
        json={
            "user_id": user["id"],
            "device_id": "device-analysis-delete-user",
            "locale": "zh-CN",
            "region_code": "HK",
            "message": "我最近胸痛，而且容易气短。",
        },
    )
    assert chat.status_code == 200
    session_id = chat.json()["meta"]["session_id"]
    def analysis_generate_text(messages, locale):
        del locale
        context = json.loads(re.search(r"\{.*\}", messages[-1]["content"], flags=re.DOTALL).group(0))
        condition_node_id = next(node["id"] for node in context["graph"]["nodes"] if node["node_type"] == "condition")
        session_node_id = next(
            node["id"] for node in context["graph"]["nodes"] if node["node_type"] == "session" and node["label"] == session_id
        )
        return ModelResult(
            content=json.dumps(
                {
                    "rows": [
                        {
                            "from_ref": condition_node_id,
                            "to_ref": session_node_id,
                            "association_type": "possibly_related_to",
                            "confidence": "medium",
                            "evidence_summary": "既往心脏病和这次胸痛会话可能相关。",
                            "source_session_ids": [session_id],
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            model=HTTP_MODEL_NAME,
        )

    client.app.state.model_adapter.generate_text = analysis_generate_text
    analyzed = client.post(f"/api/v1/users/{user['id']}/association-analysis")
    assert analyzed.status_code == 200

    deleted = client.delete(f"/api/v1/sessions/{session_id}")
    assert deleted.status_code == 200

    graph_after = client.get(f"/api/v1/users/{user['id']}/graph")
    assert graph_after.status_code == 200
    assert all(
        session_id not in edge["payload"].get("source_session_ids", [])
        for edge in graph_after.json()["edges"]
        if edge["edge_type"].startswith("MODEL_")
    )


def test_triage_progresses_from_intake_to_conclusion_by_round(client):
    _configure_model(client)

    state = {"calls": 0}

    def staged_generate(messages, locale):
        del messages, locale
        state["calls"] += 1
        if state["calls"] <= 4:
            payload = {
                "summary": "为安全分诊，需要补充信息。",
                "risk_level": "medium",
                "next_steps": [],
                "emergency_guidance": None,
                "disclaimer": "本回答仅用于健康信息参考，不能替代医生诊疗。",
                "stage": "intake",
                "follow_up_questions": ["请描述起病时间。", "当前最严重症状是什么？"],
            }
        else:
            payload = {
                "summary": "综合目前信息，建议尽快线下评估。",
                "risk_level": "medium",
                "next_steps": ["补充水分和休息。", "若症状加重尽快就医。"],
                "emergency_guidance": None,
                "disclaimer": "本回答仅用于健康信息参考，不能替代医生诊疗。",
                "stage": "intake",
                "follow_up_questions": ["仍需补充更多信息。"],
            }
        return ModelResult(content=json.dumps(payload, ensure_ascii=False), model=HTTP_MODEL_NAME)

    client.app.state.model_adapter.generate = staged_generate

    payload = {
        "device_id": "device-005",
        "locale": "zh-CN",
        "region_code": "HK",
        "message": "我这两天咳嗽、喉咙痛",
    }

    session_id = None
    for _ in range(5):
        if session_id:
            payload["session_id"] = session_id
            payload["message"] = "补充一点：夜里更明显。"
        resp = client.post("/api/v1/chat", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        session_id = data["meta"]["session_id"]

    # 第5轮强制进入结论阶段，不再停留在 intake
    assert data["answer"]["stage"] == "conclusion"
    assert len(data["answer"]["next_steps"]) >= 1
    assert isinstance(data["answer"]["advice_sections"], dict)
