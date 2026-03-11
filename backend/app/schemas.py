from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


RiskLevel = Literal["low", "medium", "high", "emergency"]
TriageStage = Literal["intake", "conclusion"]


class HealthProfile(BaseModel):
    age_range: str | None = None
    sex: str | None = None
    conditions: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    pregnancy_status: str | None = None
    symptom_duration: str | None = None


class ChatRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=128)
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


class ChatResponse(BaseModel):
    answer: ChatAnswer
    meta: ChatMeta


class SessionItem(BaseModel):
    id: str
    device_id: str
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


class ModelConfigRequest(BaseModel):
    base_url: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    model_name: str = Field(min_length=1)


class ModelConfigResponse(BaseModel):
    configured: bool
    base_url: str
    model_name: str
