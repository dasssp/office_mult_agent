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
    agent_max_delegations: int = 8
    agent_max_plan_updates: int = 3
    task_worker_poll_seconds: float = 1.0
    task_worker_timeout_seconds: float = 300
    task_worker_lease_seconds: int = 360
    task_worker_retry_delay_seconds: int = 10
    log_level: str = "INFO"
    database_url: str | None = None
    redis_url: str | None = None
    redis_key_prefix: str = "office-multi-agent"
    redis_default_ttl_seconds: int = 120
    redis_knowledge_ttl_seconds: int = 120
    redis_memory_ttl_seconds: int = 300
    gitlab_base_url: str | None = None
    gitlab_access_token: str | None = None
    gitlab_request_timeout_seconds: float = 10
    knowledge_mcp_url: str | None = None
    knowledge_mcp_service_token: str | None = None
    max_request_body_bytes: int = 2 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
