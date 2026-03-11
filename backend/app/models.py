import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .database import Base


class SessionRecord(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id: Mapped[str] = mapped_column(String(128), index=True)
    locale: Mapped[str] = mapped_column(String(16), default="zh-CN")
    region_code: Mapped[str] = mapped_column(String(16), default="HK")
    summary: Mapped[str] = mapped_column(Text, default="")
    latest_risk: Mapped[str] = mapped_column(String(16), default="low")
    triage_stage: Mapped[str] = mapped_column(String(16), default="intake")
    triage_round_count: Mapped[int] = mapped_column(default=0)
    health_profile = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["MessageRecord"]] = relationship(
        "MessageRecord",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class MessageRecord(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    risk_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    priority: Mapped[int] = mapped_column(default=10)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[SessionRecord] = relationship("SessionRecord", back_populates="messages")


Index("idx_messages_session_created", MessageRecord.session_id, MessageRecord.created_at.desc())


class RuntimeConfig(Base):
    __tablename__ = "runtime_configs"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    model_base_url: Mapped[str] = mapped_column(String(255), default="https://open.bigmodel.cn/api/paas/v4")
    model_name: Mapped[str] = mapped_column(String(128), default="glm-4.7-flash")
    model_api_key: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
