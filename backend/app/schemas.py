from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


RiskLevel = Literal["low", "medium", "high", "emergency"]
TriageStage = Literal["intake", "conclusion"]
ProviderMode = Literal["codex_cli", "oauth_cli", "http_api"]


class HealthProfile(BaseModel):
    age_range: str | None = None
    sex: str | None = None
    conditions: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    pregnancy_status: str | None = None
    symptom_duration: str | None = None


class ChatRequest(BaseModel):
    device_id: str = ""
    user_id: str | None = None
    locale: str = "zh-CN"
    region_code: str = "HK"
    message: str = Field(min_length=1)
    health_profile: HealthProfile | None = None
    session_id: str | None = None


class ChatAnswer(BaseModel):
    summary: str
    risk_level: RiskLevel
    next_steps: list[str]
    emergency_guidance: str | None = None
    disclaimer: str
    stage: TriageStage = "conclusion"
    follow_up_questions: list[str] | None = None


class ChatMeta(BaseModel):
    session_id: str
    used_context_turns: int
    model: str
    user_id: str | None = None


class ChatResponse(BaseModel):
    answer: ChatAnswer
    meta: ChatMeta


class SessionItem(BaseModel):
    id: str
    device_id: str
    user_id: str | None = None
    locale: str
    region_code: str
    latest_risk: RiskLevel
    created_at: datetime
    updated_at: datetime


class SessionListResponse(BaseModel):
    sessions: list[SessionItem]


class MessageItem(BaseModel):
    id: int
    role: str
    content: str
    risk_level: str | None = None
    created_at: datetime


class MessageListResponse(BaseModel):
    session_id: str
    messages: list[MessageItem]


class ModelConfigStatusResponse(BaseModel):
    configured: bool
    base_url: str
    model_name: str
    provider_mode: ProviderMode = "codex_cli"
    oauth_cli_available: bool = False
    oauth_logged_in: bool = False
    oauth_status_message: str = ""
    oauth_account_id: str | None = None
    mcp_available: bool = False
    mcp_status_message: str = ""


class ModelConfigRequest(BaseModel):
    provider_mode: ProviderMode = "codex_cli"
    base_url: str = ""
    api_key: str = ""
    model_name: str = ""


class ModelConfigResponse(BaseModel):
    configured: bool
    base_url: str
    model_name: str
    provider_mode: ProviderMode = "codex_cli"


class OAuthStatusResponse(BaseModel):
    provider: str = "codex"
    cli_available: bool
    logged_in: bool
    status_message: str
    account_id: str | None = None
    mcp_available: bool = False
    mcp_status_message: str = ""


class OAuthActionResponse(BaseModel):
    ok: bool
    message: str


class UserProfile(BaseModel):
    id: str
    username: str
    locale: str
    region_code: str
    birth_year: str = ""
    sex: str = ""
    conditions: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    last_active_at: datetime


class UserListResponse(BaseModel):
    users: list[UserProfile]


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    locale: str = "zh-CN"
    region_code: str = "HK"
    birth_year: str = ""
    sex: str = ""
    conditions: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)


class UserUpdateRequest(BaseModel):
    locale: str | None = None
    region_code: str | None = None
    birth_year: str | None = None
    sex: str | None = None
    conditions: list[str] | None = None
    medications: list[str] | None = None
    allergies: list[str] | None = None
    mark_active: bool = False


class UserGraphNode(BaseModel):
    id: str
    node_type: str
    label: str
    payload: dict = Field(default_factory=dict)
    source: str
    created_at: datetime
    updated_at: datetime


class UserGraphEdge(BaseModel):
    id: str
    from_node_id: str
    to_node_id: str
    edge_type: str
    payload: dict = Field(default_factory=dict)
    created_at: datetime


class GraphJourneyItem(BaseModel):
    title: str
    detail: str = ""
    session_id: str = ""
    is_current_session: bool = False
    sort_time: datetime
    severity_hint: RiskLevel | str = "low"


class GraphRiskSignalItem(BaseModel):
    label: str
    risk_level: RiskLevel | str = "low"
    session_id: str = ""
    is_current_session: bool = False
    is_active: bool = False
    sort_time: datetime


class GraphContextBundle(BaseModel):
    persistent_features: dict[str, list[str]] = Field(default_factory=dict)
    profile_highlights: list[str] = Field(default_factory=list)
    recent_timeline: list[dict] = Field(default_factory=list)
    recent_journey: list[GraphJourneyItem] = Field(default_factory=list)
    risk_signals: list[GraphRiskSignalItem] = Field(default_factory=list)
    summary_labels: list[str] = Field(default_factory=list)


class UserGraphResponse(BaseModel):
    user_id: str
    nodes: list[UserGraphNode]
    edges: list[UserGraphEdge]
    summary_bundle: GraphContextBundle


class UserDeleteResponse(BaseModel):
    deleted: bool
    user_id: str


class LegacyUserProfileImport(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    locale: str = "zh-CN"
    region_code: str = "HK"
    birth_year: str = ""
    sex: str = ""
    conditions: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)


class LegacyImportRequest(BaseModel):
    profiles: list[LegacyUserProfileImport] = Field(default_factory=list)
    active_username: str | None = None
