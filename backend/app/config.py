from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="HEALTH_AGENT_", extra="ignore")

    app_name: str = "Health Agent API"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://postgres:postgres@postgres:5432/health_agent"

    model_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    model_api_key: str = ""
    model_name: str = "glm-4.7-flash"
    model_timeout_seconds: int = 45

    context_turn_limit: int = 6
    max_context_chars: int = 5000
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
