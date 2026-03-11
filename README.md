# Health Agent v1

Health Agent is a health-focused AI agent inspired by openclaw's gateway/runtime pattern.

It supports:
- Free-text symptom input + structured health profile fields
- Risk triage (`low|medium|high|emergency`) with strict safety rules
- OpenAI Codex CLI login with built-in MCP tools (default) + HTTP API fallback
- First-open model setup UI
- Anonymous long-term local history (device-based, no login)
- Session/message APIs for retrieval and deletion

## Stack

- Frontend: React + Vite + TypeScript
- Backend: FastAPI + SQLAlchemy
- Database: Postgres
- Deployment: Docker Compose

## Quick Start (Docker)

1. Optional envs:

```bash
export HEALTH_AGENT_PROVIDER_MODE="codex_cli"
export HEALTH_AGENT_CODEX_CLI_BIN="codex"
export HEALTH_AGENT_MCP_MODE="stdio"
export HEALTH_AGENT_MODEL_BASE_URL="https://api.openai.com/v1"
export HEALTH_AGENT_MODEL_NAME="gpt-5.4"
```

2. Start all services:

```bash
docker compose up --build
```

3. Open apps:
- Frontend: http://localhost:5173
- Backend health: http://localhost:8000/health

## Local Development

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
codex login
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Set API URL in `frontend/.env`:

```bash
VITE_API_BASE_URL=http://localhost:8000
```

## API

### POST `/api/v1/chat`

Request:

```json
{
  "device_id": "device_xxx",
  "locale": "zh-CN",
  "region_code": "HK",
  "message": "我胸痛并且呼吸困难",
  "health_profile": {
    "age_range": "30-39",
    "sex": "female",
    "conditions": ["asthma"],
    "medications": ["inhaler"],
    "allergies": ["penicillin"],
    "pregnancy_status": "not pregnant"
  },
  "session_id": null
}
```

### GET `/api/v1/sessions/{device_id}`
Get sessions for an anonymous device.

### GET `/api/v1/sessions/{session_id}/messages`
Get all messages for a session.

### DELETE `/api/v1/sessions/{session_id}`
Delete one session and its messages.

### GET `/api/v1/model-config/status`
Returns runtime model config status:

```json
{
  "configured": false,
  "base_url": "https://api.openai.com/v1",
  "model_name": "gpt-5.4",
  "provider_mode": "codex_cli",
  "oauth_cli_available": true,
  "oauth_logged_in": false,
  "oauth_status_message": "Codex CLI is not logged in.",
  "oauth_account_id": null,
  "mcp_available": true,
  "mcp_status_message": "MCP server is ready."
}
```

### POST `/api/v1/model-config`
Set model config:

```json
{
  "provider_mode": "http_api",
  "base_url": "https://open.bigmodel.cn/api/paas/v4",
  "api_key": "<your_token>",
  "model_name": "glm-4.7-flash"
}
```

Tip: if you provide an endpoint ending with `/chat/completions`, backend auto-normalizes to base URL.

### OAuth APIs

- `GET /api/v1/auth/oauth/status`
- `POST /api/v1/auth/oauth/login/start`
- `POST /api/v1/auth/oauth/logout`

In `codex_cli` mode, the backend invokes `codex exec` with an internal stdio MCP server. The MCP tools expose session context, risk analysis, and response planning, while the FastAPI backend remains the source of truth for safety checks and persistence.

## Safety Strategy (Strict)

- Pre-routing emergency detection (CN + EN keywords)
- No diagnosis and no prescription output policy
- Emergency/high-risk guidance includes region-based emergency number
- Post-generation guard rewrites unsafe output

## Tests

```bash
cd backend
pytest -q
```

```bash
cd frontend
npm run build
```
