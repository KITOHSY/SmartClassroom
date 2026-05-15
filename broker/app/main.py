import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from broker.app.api.v1.health import router as health_router
from broker.app.api.v1.router import api_router
from broker.app.core.config import Settings, get_settings
from broker.app.core.errors import register_error_handlers
from broker.app.core.logging import configure_logging, get_logger
from broker.app.core.metrics import setup_metrics
from broker.app.core.middleware import (
    AccessLogMiddleware,
    AuthSessionMiddleware,
    RequestIdMiddleware,
)
from broker.app.infra.db import dispose_engine
from broker.app.services.host_events import HostEventBroker
from broker.app.services.host_status_monitor import run_monitor_loop
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse


def _enforce_production_guards(settings: Settings) -> None:
    """EXP §11 Mock-first 운영 가드 — production에서 mock provider 활성 시 즉시 거부."""
    if settings.app_env == "production":
        if settings.auth_provider == "mock":
            raise RuntimeError(
                "MockAuthProvider는 production에서 사용할 수 없습니다. "
                "AUTH_PROVIDER=cnu_sso 또는 다른 실제 provider를 설정하세요."
            )
        if settings.session_secret in ("change-me", "dev-secret", ""):
            raise RuntimeError(
                "production에서는 SESSION_SECRET을 안전한 값으로 반드시 주입해야 합니다."
            )
        if not settings.session_cookie_secure:
            raise RuntimeError("production에서는 SESSION_COOKIE_SECURE=true가 강제됩니다.")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)
    _enforce_production_guards(settings)
    log = get_logger(__name__)
    log.info(
        "broker.startup",
        env=settings.app_env,
        version=settings.app_version,
        auth_provider=settings.auth_provider,
    )

    # T06 — SSE 이벤트 broker + stale heartbeat → OFFLINE detector task.
    app.state.host_event_broker = HostEventBroker()
    monitor_stop = asyncio.Event()
    app.state.host_monitor_stop = monitor_stop
    monitor_task = asyncio.create_task(
        run_monitor_loop(app.state.host_event_broker, monitor_stop, settings)
    )
    app.state.host_monitor_task = monitor_task

    try:
        yield
    finally:
        log.info("broker.shutdown")
        monitor_stop.set()
        try:
            await asyncio.wait_for(monitor_task, timeout=5.0)
        except (TimeoutError, asyncio.CancelledError):
            monitor_task.cancel()
        await app.state.host_event_broker.close()
        await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="SmartClassroom Broker",
        version=settings.app_version,
        default_response_class=ORJSONResponse,
        docs_url="/docs" if settings.expose_docs else None,
        redoc_url="/redoc" if settings.expose_docs else None,
        openapi_url="/openapi.json" if settings.expose_docs else None,
        lifespan=lifespan,
    )

    # 미들웨어는 LIFO: 마지막 add가 가장 바깥(요청 가장 먼저).
    # 실행 순서 (요청 → 응답): RequestId → AuthSession → AccessLog → CORS → 라우터.
    # AccessLog가 user_id/auth_provider contextvar를 픽업하려면 AuthSession이
    # AccessLog의 바깥(요청 시 먼저)이어야 함.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(AuthSessionMiddleware)
    app.add_middleware(RequestIdMiddleware)

    register_error_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(health_router)

    # Prometheus instrumentation은 모든 라우터 등록 후 호출 (라우트 패턴 라벨링).
    setup_metrics(app)

    return app


app = create_app()
