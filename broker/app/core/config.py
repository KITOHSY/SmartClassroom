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

    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )
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

    # 예약 도메인 정책 (T05) — DB 정책 테이블 대신 env로 운영. 변경은 재배포 또는 env 갱신.
    reservation_slot_minutes: int = 30
    max_concurrent_reservations: int = 5
    max_reservation_hours_per_day: int = 8
    max_reservation_duration_minutes: int = 240
    reservation_lookahead_days: int = 14

    # 동적 접속 토큰 정책 (T07) — 발급 게이트의 starts_at 이전 grace.
    # `starts_at - grace ~ ends_at` 윈도우에서 발급 가능. 변경은 재배포 또는 env 갱신.
    connect_token_grace_seconds: int = 60

    # 에이전트 토큰 정책 (T11) — admin 발급, host가 살아있는 동안 유효.
    # 회전은 admin이 명시적 revoke + 재발급. 기본 3650일(10년).
    agent_token_ttl_days: int = 3650

    # 호스트 상태 머신 정책 (T06).
    # heartbeat 마지막 수신 후 N초 경과 시 OFFLINE 전이 (3 cycle 누락 = 90s 기본).
    host_offline_after_seconds: int = 90
    # heartbeat 메트릭이 임계 이상이면 DEGRADED 전이.
    host_degraded_cpu_pct: float = 90.0
    host_degraded_mem_pct: float = 95.0
    # OFFLINE detector tick 주기 (background task).
    host_status_monitor_interval_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
