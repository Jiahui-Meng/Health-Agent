# Health Agent v1

Health Agent is a health-focused AI agent inspired by openclaw's gateway/runtime pattern.

It supports:
- Free-text symptom input + structured health profile fields
- Risk triage (`low|medium|high|emergency`) with strict safety rules
- OpenAI-compatible HTTP model API (BigModel default)
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
export HEALTH_AGENT_MODEL_BASE_URL="https://open.bigmodel.cn/api/paas/v4"
export HEALTH_AGENT_MODEL_API_KEY="<your_token>"
export HEALTH_AGENT_MODEL_NAME="glm-4.7-flash"
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
  "configured": true,
  "base_url": "https://open.bigmodel.cn/api/paas/v4",
  "model_name": "glm-4.7-flash"
}
```

### POST `/api/v1/model-config`
Set model config:

```json
{
  "base_url": "https://open.bigmodel.cn/api/paas/v4",
  "api_key": "<your_token>",
  "model_name": "glm-4.7-flash"
}
```

Tip: if you provide an endpoint ending with `/chat/completions`, backend auto-normalizes to base URL.

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
