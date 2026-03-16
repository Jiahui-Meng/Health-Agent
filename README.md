# Health Agent v1

Health Agent is a local AI agent for health consultation and triage. It supports multi-user local profiles, persistent sessions, a user health graph, doctor-style multi-turn intake, exportable reports, and graph-based association analysis.

Health Agent 是一个本地运行的健康咨询与分诊 AI Agent，支持本地多用户、长期会话持久化、用户级健康图谱、医生式多轮问诊、可导出报告，以及基于图谱的关联性分析。

## How to Run

### Quick Start

1. Backend setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Start the backend with local SQLite

```bash
cd backend
source .venv/bin/activate
HEALTH_AGENT_DATABASE_URL="sqlite:///./health_agent_dev.db" uvicorn app.main:app --reload --port 8000
```

3. Frontend setup

```bash
cd frontend
npm install
printf "VITE_API_BASE_URL=http://localhost:8000\n" > .env
npm run dev
```

4. Login to Codex CLI

```bash
codex login
codex login status
```

5. Open the app

```text
http://localhost:5173
```

Expected endpoints:

- Frontend: `http://localhost:5173`
- Backend health: `http://localhost:8000/health`

### 快速启动

1. 安装后端依赖

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. 使用本地 SQLite 启动后端

```bash
cd backend
source .venv/bin/activate
HEALTH_AGENT_DATABASE_URL="sqlite:///./health_agent_dev.db" uvicorn app.main:app --reload --port 8000
```

3. 安装并启动前端

```bash
cd frontend
npm install
printf "VITE_API_BASE_URL=http://localhost:8000\n" > .env
npm run dev
```

4. 登录 Codex CLI

```bash
codex login
codex login status
```

5. 打开页面

```text
http://localhost:5173
```

启动后你应该能访问：

- 前端：`http://localhost:5173`
- 后端健康检查：`http://localhost:8000/health`

## Local Development

### English

Recommended local stack:

- Backend: FastAPI + SQLAlchemy
- Frontend: React + Vite + TypeScript
- Database: SQLite for local development
- Model provider: `Codex CLI` by default, `HTTP API` as fallback

If you want the most stable local path, use:

- `SQLite + local backend + local frontend + Codex CLI`

### 中文

推荐的本地开发组合：

- 后端：FastAPI + SQLAlchemy
- 前端：React + Vite + TypeScript
- 数据库：本地开发推荐 SQLite
- 模型接入：默认 `Codex CLI`，回退可用 `HTTP API`

如果你要走最稳的本地路径，建议使用：

- `SQLite + 本地后端 + 本地前端 + Codex CLI`

## Model Providers

### English

Supported provider modes:

1. `Codex CLI` (default)
- Uses local `codex` login state
- Best for local development
- Works with the built-in MCP flow used by this project

2. `HTTP API`
- OpenAI-style compatible endpoint
- Manual `Base URL / API Key / Model Name`
- Useful as fallback

Default config references:

- [backend/.env.example](/Users/kevin/Desktop/Health_Agent/backend/.env.example)
- [backend/app/config.py](/Users/kevin/Desktop/Health_Agent/backend/app/config.py)

Default values:

- `HEALTH_AGENT_PROVIDER_MODE=codex_cli`
- `HEALTH_AGENT_MODEL_BASE_URL=https://api.openai.com/v1`
- `HEALTH_AGENT_MODEL_NAME=gpt-5.4`

Prompt packs:

- Prompt files are loaded from `backend/prompts/{zh|en}`.
- System prompt is assembled in fixed order:
  `role.md -> policy.md -> user.md -> data_availability.md -> output.md`
- `user.md` is template-based and only carries minimal user card fields.
- Configure with:
  - `HEALTH_AGENT_PROMPTS_DIR=prompts`
  - `HEALTH_AGENT_PROMPT_LOCALE_FALLBACK=en`

### 中文

当前支持两种模型接入方式：

1. `Codex CLI`（默认）
- 使用本机 `codex` 登录态
- 更适合本地开发
- 与当前项目内建的 MCP 流程配合使用

2. `HTTP API`
- 兼容 OpenAI 风格接口
- 手动填写 `Base URL / API Key / Model Name`
- 适合作为回退方案

默认配置可参考：

- [backend/.env.example](/Users/kevin/Desktop/Health_Agent/backend/.env.example)
- [backend/app/config.py](/Users/kevin/Desktop/Health_Agent/backend/app/config.py)

默认值包括：

- `HEALTH_AGENT_PROVIDER_MODE=codex_cli`
- `HEALTH_AGENT_MODEL_BASE_URL=https://api.openai.com/v1`
- `HEALTH_AGENT_MODEL_NAME=gpt-5.4`

Prompt 文件说明：

- Prompt 文件目录：`backend/prompts/{zh|en}`
- System prompt 按固定顺序拼接：
  `role.md -> policy.md -> user.md -> data_availability.md -> output.md`
- `user.md` 使用模板变量，仅承载最小用户身份卡，不放全量历史。
- 可通过以下变量配置：
  - `HEALTH_AGENT_PROMPTS_DIR=prompts`
  - `HEALTH_AGENT_PROMPT_LOCALE_FALLBACK=en`

## Tests

### English

Backend:

```bash
cd backend
source .venv/bin/activate
pytest -q
```

Frontend:

```bash
cd frontend
npm run build
```

### 中文

后端测试：

```bash
cd backend
source .venv/bin/activate
pytest -q
```

前端构建检查：

```bash
cd frontend
npm run build
```

## API Overview

### English

Core endpoints:

- `POST /api/v1/chat`
- `GET /api/v1/users`
- `POST /api/v1/users`
- `PATCH /api/v1/users/{user_id}`
- `GET /api/v1/users/{user_id}/sessions`
- `GET /api/v1/users/{user_id}/graph`
- `POST /api/v1/users/{user_id}/association-analysis`
- `GET /api/v1/users/{user_id}/export?format=markdown`
- `GET /api/v1/model-config/status`
- `POST /api/v1/model-config`
- `GET /api/v1/auth/oauth/status`
- `POST /api/v1/auth/oauth/login/start`
- `POST /api/v1/auth/oauth/logout`

Example chat request:

```json
{
  "user_id": "your-user-id",
  "device_id": "device_local_user",
  "locale": "zh-CN",
  "region_code": "HK",
  "message": "I have a sore throat, cough, and fever.",
  "health_profile": {
    "age_range": "Birth year: 1990",
    "sex": "female",
    "conditions": ["asthma"],
    "medications": ["inhaler"],
    "allergies": ["penicillin"]
  }
}
```

### 中文

核心接口：

- `POST /api/v1/chat`
- `GET /api/v1/users`
- `POST /api/v1/users`
- `PATCH /api/v1/users/{user_id}`
- `GET /api/v1/users/{user_id}/sessions`
- `GET /api/v1/users/{user_id}/graph`
- `POST /api/v1/users/{user_id}/association-analysis`
- `GET /api/v1/users/{user_id}/export?format=markdown`
- `GET /api/v1/model-config/status`
- `POST /api/v1/model-config`
- `GET /api/v1/auth/oauth/status`
- `POST /api/v1/auth/oauth/login/start`
- `POST /api/v1/auth/oauth/logout`

聊天请求示例：

```json
{
  "user_id": "your-user-id",
  "device_id": "device_local_user",
  "locale": "zh-CN",
  "region_code": "HK",
  "message": "我今天发烧到38度，喉咙痛，还有点咳嗽",
  "health_profile": {
    "age_range": "出生年份: 1990",
    "sex": "female",
    "conditions": ["哮喘"],
    "medications": ["吸入剂"],
    "allergies": ["青霉素"]
  }
}
```

## Product Shape

### English

Current product capabilities:

- Local multi-user profiles
- Persistent sessions, messages, and graph data in the backend database
- User health graph with raw event nodes and derived association edges
- Doctor-style 3-5 turn intake flow
- Final-stage conclusion with structured advice modules
- Markdown export report
- Manual full-user association analysis written back into the graph
- `sex` is a required safety field to prevent clearly mismatched sex-specific questioning

### 中文

当前产品能力包括：

- 本地多用户档案
- 后端数据库持久化用户、会话、消息和 graph 数据
- 同时包含原始事件节点与派生关联边的用户健康图谱
- 医生式 3-5 轮问诊
- 最终阶段输出结论与结构化建议模块
- Markdown 导出报告
- 手动触发的整用户关联性分析，并直接写回 graph
- `sex` 是强制安全字段，用于避免明显错误的性别特异追问

## Safety Strategy

### English

Safety behavior:

- Emergency keyword pre-classification
- Profile guardrails for `sex`, `birth_year`, and `region_code`
- Intake stage only asks questions and does not show final conclusion/risk
- Conclusion stage shows advice, summary, and risk level
- Sex-mismatched content is rewritten during post-processing
- No diagnosis or prescription-style instructions
- Full-user association analysis only produces candidate associations, never diagnoses

### 中文

安全策略包括：

- 急症关键词前置识别
- 基于 `sex`、`birth_year`、`region_code` 的 profile guardrails
- `intake` 阶段只追问，不提前输出最终结论与风险等级
- `conclusion` 阶段才输出建议、总结和风险等级
- 性别不匹配内容会在后处理阶段被自动重写
- 禁止诊断性结论与处方式指令
- 整用户关联性分析只输出候选关联，不输出诊断

## Common Startup Issues

### English

1. `postgres` host error during local backend startup

If you see something like:

```text
nodename nor servname provided, or not known
```

You are likely still using a PostgreSQL connection string intended for a container/service network. For local development, switch to SQLite:

```bash
HEALTH_AGENT_DATABASE_URL="sqlite:///./health_agent_dev.db" uvicorn app.main:app --reload --port 8000
```

2. Codex CLI is not logged in

Check:

```bash
codex login status
```

If needed:

```bash
codex login
```

3. Frontend opens but chat does not work

Check:

- Backend is running at `http://localhost:8000`
- `frontend/.env` contains `VITE_API_BASE_URL=http://localhost:8000`
- Codex / MCP status is healthy in the top-right settings dialog

### 中文

1. 本地启动后端时报 `postgres` 主机名错误

如果你看到类似：

```text
nodename nor servname provided, or not known
```

通常说明你还在使用面向容器/服务网络的 PostgreSQL 连接串。本地开发请切换到 SQLite：

```bash
HEALTH_AGENT_DATABASE_URL="sqlite:///./health_agent_dev.db" uvicorn app.main:app --reload --port 8000
```

2. Codex CLI 未登录

先检查：

```bash
codex login status
```

如果未登录，执行：

```bash
codex login
```

3. 前端能打开但无法聊天

优先检查：

- 后端是否在 `http://localhost:8000`
- `frontend/.env` 是否配置了 `VITE_API_BASE_URL=http://localhost:8000`
- 右上角设置弹层中的 Codex / MCP 状态是否正常

## Related Docs

- [graph-architecture.md](/Users/kevin/Desktop/Health_Agent/docs/graph-architecture.md)
