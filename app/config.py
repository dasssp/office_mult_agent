from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "office-multi-agent"
    app_env: Literal["development", "test", "production"] = "development"
    assistant_runtime: Literal["legacy", "deep_agent"] = "legacy"
    agent_model: str | None = None
    agent_recursion_limit: int = 48
    agent_timeout_seconds: int = 180
    log_level: str = "INFO"
    database_url: str | None = None
    knowledge_mcp_url: str | None = None
    knowledge_mcp_service_token: str | None = None
    max_request_body_bytes: int = 2 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
