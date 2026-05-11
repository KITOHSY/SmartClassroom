from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "staging", "production", "test"] = "development"
    app_version: str = "0.1.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    database_url: str = Field(
        default="postgresql+asyncpg://broker:broker@localhost:5432/broker",
        description="Async SQLAlchemy URL (postgresql+asyncpg://)",
    )
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_pool_pre_ping: bool = True

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    expose_docs: bool = True

    auth_provider: Literal["mock", "cnu_sso", "cnu_mail_oauth"] = "mock"
    session_secret: str = "change-me"

    session_cookie_name: str = "broker_session"
    session_ttl_seconds: int = 60 * 60 * 8
    session_cookie_secure: bool = True
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_domain: str | None = None
    auth_login_path: str = "/api/v1/auth/mock/login"

    enable_metrics: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
