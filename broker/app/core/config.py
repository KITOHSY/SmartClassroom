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

    # 내부 컴포넌트 인증 (T08, §11 A6) — X-Internal-Token 헤더 공유 비밀.
    # /tokens/verify 등 머신-투-머신 엔드포인트 보호. production에서 미설정/placeholder면 부팅 거부.
    internal_api_token: str | None = None

    # 자동 페어링 — Sunshine confighttp 호출 (T08).
    # confighttp 포트는 스트리밍 포트(hosts.sunshine_port, 기본 47984)와 별개로 47990 고정.
    sunshine_config_port: int = 47990
    # Sunshine은 자가서명 인증서 — 캠퍼스 LAN 전제로 검증 생략. cert pinning은 후속 강화.
    sunshine_tls_verify: bool = False
    sunshine_request_timeout_seconds: float = 5.0
    # /api/pin 푸시 재시도 — 클라이언트가 페어링 세션을 막 띄운 직후의 짧은 레이스를 흡수.
    sunshine_pair_max_attempts: int = 5
    sunshine_pair_backoff_base_seconds: float = 0.5


@lru_cache
def get_settings() -> Settings:
    return Settings()
