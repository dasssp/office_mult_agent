from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    java_rag_base_url: str | None = None
    mcp_service_token: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
