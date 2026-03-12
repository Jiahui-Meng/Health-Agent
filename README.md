# Health Agent v1

Health Agent 是一个面向健康咨询与分诊的本地 AI Agent，默认使用 `Codex CLI + MCP tools`，并保留 `HTTP API` 作为回退模式。  
当前项目已经支持本地多用户、长期会话持久化、health graph、医生式多轮问诊，以及用户级导出报告。

## How to Run / 如何运行

推荐直接使用本地开发路径。当前项目默认面向本机运行，尤其是 `Codex CLI` 更适合直接使用宿主机登录态。

### Quick Start

1. 安装后端依赖

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. 启动后端（本地推荐 SQLite）

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

启动完成后你应该能访问：

- Frontend: `http://localhost:5173`
- Backend health: `http://localhost:8000/health`

如果前端右上角的设置按钮里能看到 Codex / MCP 状态，说明模型配置链路也正常。

## Local Development

### 1. Backend Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

推荐本地先用 SQLite，启动最稳：

```env
HEALTH_AGENT_DATABASE_URL=sqlite:///./health_agent_dev.db
```

可以把这行写进 `backend/.env`，或者直接临时带环境变量启动：

```bash
HEALTH_AGENT_DATABASE_URL="sqlite:///./health_agent_dev.db" uvicorn app.main:app --reload --port 8000
```

### 2. Frontend Setup

```bash
cd frontend
npm install
```

在 `frontend/.env` 中设置：

```env
VITE_API_BASE_URL=http://localhost:8000
```

然后启动前端：

```bash
npm run dev
```

### 3. Model Setup

默认推荐 `Codex CLI`。

先登录：

```bash
codex login
codex login status
```

然后打开前端：

- 首次进入会弹出模型配置
- 默认 Provider 是 `Codex CLI`
- 也可以切换到 `HTTP API`

如果你只是本地开发，推荐这条路径：

- `SQLite + 本地后端 + 本地前端 + Codex CLI`

## Model Providers

当前项目支持两种模型接入方式。

1. `Codex CLI (default)`
- 使用 OpenAI 账号登录后的 `codex` CLI
- 后端通过内建 `MCP server` 调用模型
- 推荐用于本地开发和默认体验

2. `HTTP API`
- 适配 OpenAI 风格接口
- 可手动填写 `Base URL / API Key / Model Name`
- 适合作为回退路径

默认相关配置可见于：

- [backend/.env.example](/Users/kevin/Desktop/Health_Agent/backend/.env.example)
- [backend/app/config.py](/Users/kevin/Desktop/Health_Agent/backend/app/config.py)

默认值包括：

- `HEALTH_AGENT_PROVIDER_MODE=codex_cli`
- `HEALTH_AGENT_MODEL_BASE_URL=https://api.openai.com/v1`
- `HEALTH_AGENT_MODEL_NAME=gpt-5.4`

## Tests

### Backend

```bash
cd backend
source .venv/bin/activate
pytest -q
```

### Frontend

```bash
cd frontend
npm run build
```

## API Overview

核心接口：

- `POST /api/v1/chat`
- `GET /api/v1/users`
- `POST /api/v1/users`
- `PATCH /api/v1/users/{user_id}`
- `GET /api/v1/users/{user_id}/sessions`
- `GET /api/v1/users/{user_id}/graph`
- `GET /api/v1/users/{user_id}/export?format=markdown`
- `GET /api/v1/model-config/status`
- `POST /api/v1/model-config`
- `GET /api/v1/auth/oauth/status`
- `POST /api/v1/auth/oauth/login/start`
- `POST /api/v1/auth/oauth/logout`

聊天接口示例：

```json
{
  "user_id": "your-user-id",
  "device_id": "device_local_user",
  "locale": "zh-CN",
  "region_code": "HK",
  "message": "我今天发烧到38度，喉咙痛，还有点咳嗽",
  "health_profile": {
    "age_range": "出生年份: 1990",
    "sex": "女",
    "conditions": ["哮喘"],
    "medications": ["吸入剂"],
    "allergies": ["青霉素"]
  }
}
```

## Stack

- Frontend: React + Vite + TypeScript
- Backend: FastAPI + SQLAlchemy
- Database: SQLite / PostgreSQL
- Runtime: Codex CLI + MCP tools / HTTP API fallback
- Deployment: Local development

## Product Shape

当前项目的主要形态：

- 本地多用户
- 后端数据库持久化用户档案、会话和消息
- 用户级 health graph
- 3-5 轮医生式问诊
- 最终阶段才输出结论与风险等级
- 用户级 Markdown 导出报告
- `sex` 为强制安全字段，用于避免明显错误的性别特异追问

## Safety Strategy

- 急症关键词前置识别
- 用户资料 guardrails：
  - `sex` 为强制字段
  - 出生年份会推导年龄段约束
  - `region_code` 会约束急症文案与急救号码上下文
- `intake` 阶段只做医生式追问，不提前给结论和风险等级
- `conclusion` 阶段才输出建议模块、结论和风险等级
- 性别不匹配内容会在后处理阶段被自动重写为中性、安全的问法

## Profile Guardrails

当前问诊链路会把以下用户资料作为硬约束注入 prompt：

- `sex`
- `birth_year`（推导年龄段）
- `region_code`

这些约束目前用于：

- 避免明显错误的性别特异追问
- 对未成年人和老年人采用更谨慎的问诊与建议阈值
- 让急症文案与地区急救号码保持一致

相关实现入口：

- [backend/app/services/profile_guardrails.py](/Users/kevin/Desktop/Health_Agent/backend/app/services/profile_guardrails.py)
- 禁止诊断结论与处方指令
- 急症场景直接分流
- 多轮问诊后再给最终结论
- 高风险输出保留区域化急救提示

## 常见启动问题

### 1. 本地直跑后端时报 `postgres` 主机名错误

如果你看到类似：

```text
nodename nor servname provided, or not known
```

通常说明你还在用旧的 Postgres 连接串。  
本地开发请改成 SQLite，例如：

```bash
HEALTH_AGENT_DATABASE_URL="sqlite:///./health_agent_dev.db" uvicorn app.main:app --reload --port 8000
```

### 2. Codex CLI 显示未登录

先检查：

```bash
codex login status
```

如果未登录，执行：

```bash
codex login
```

### 3. 前端能打开，但不能聊天

优先检查这三项：

- Backend 是否在 `http://localhost:8000`
- `frontend/.env` 是否配置了 `VITE_API_BASE_URL=http://localhost:8000`
- 右上角模型配置按钮中，Codex / MCP 状态是否正常

## Related Docs

- [graph-architecture.md](/Users/kevin/Desktop/Health_Agent/docs/graph-architecture.md)
