import json

from app.services.model_adapter import ModelAPIError, ModelResult


BIGMODEL_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
BIGMODEL_MODEL_NAME = "glm-4.7-flash"


def _configure_model(client):
    update = client.post(
        "/api/v1/model-config",
        json={
            "base_url": BIGMODEL_BASE_URL,
            "api_key": "test-key",
            "model_name": BIGMODEL_MODEL_NAME,
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
            model=BIGMODEL_MODEL_NAME,
        )

    client.app.state.model_adapter.generate = fake_generate


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


def test_model_config_setup_flow(client):
    status_before = client.get("/api/v1/model-config/status")
    assert status_before.status_code == 200
    assert status_before.json()["configured"] is False
    assert status_before.json()["base_url"] == BIGMODEL_BASE_URL
    assert status_before.json()["model_name"] == BIGMODEL_MODEL_NAME

    update = client.post(
        "/api/v1/model-config",
        json={
            "base_url": BIGMODEL_BASE_URL,
            "api_key": "test-key",
            "model_name": BIGMODEL_MODEL_NAME,
        },
    )
    assert update.status_code == 200
    assert update.json()["configured"] is True

    status_after = client.get("/api/v1/model-config/status")
    assert status_after.status_code == 200
    assert status_after.json()["configured"] is True
    assert status_after.json()["model_name"] == BIGMODEL_MODEL_NAME


def test_model_config_normalizes_chat_completions_suffix(client):
    update = client.post(
        "/api/v1/model-config",
        json={
            "base_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
            "api_key": "test-key",
            "model_name": BIGMODEL_MODEL_NAME,
        },
    )
    assert update.status_code == 200
    assert update.json()["base_url"] == BIGMODEL_BASE_URL

    status = client.get("/api/v1/model-config/status")
    assert status.status_code == 200
    assert status.json()["base_url"] == BIGMODEL_BASE_URL


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
        return ModelResult(content=json.dumps(payload, ensure_ascii=False), model=BIGMODEL_MODEL_NAME)

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
