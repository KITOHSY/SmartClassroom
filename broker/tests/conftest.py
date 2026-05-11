"""테스트 fixture.

DB가 필요 없는 테스트는 `client` 만 사용하면 된다.
DB가 필요한 테스트(readyz, alembic, models)는 `pg_url`/`db_session` fixture 사용.
"""

import os
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient


@pytest.fixture(scope="session", autouse=True)
def _set_test_env() -> None:
    os.environ.setdefault("APP_ENV", "test")
    os.environ.setdefault("LOG_LEVEL", "WARNING")
    os.environ.setdefault("ENABLE_METRICS", "true")
    # 테스트는 http://test 위에서 동작하므로 secure cookie를 끄지 않으면 cookie jar에 적용 안 됨.
    os.environ.setdefault("SESSION_COOKIE_SECURE", "false")


@pytest_asyncio.fixture
async def client_no_lifespan() -> AsyncIterator[AsyncClient]:
    """lifespan 없이 앱 인스턴스만 — 단순 라우트 테스트용."""
    from broker.app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def client(pg_url: str) -> AsyncIterator[AsyncClient]:
    """lifespan 활성 + DB 연결 — readyz/통합 테스트용."""
    os.environ["DATABASE_URL"] = pg_url
    # get_settings는 lru_cache라 한 번 캐시되면 변경 반영 안 됨 — 캐시 비움.
    from broker.app.core.config import get_settings

    get_settings.cache_clear()

    from broker.app.infra.db import dispose_engine

    await dispose_engine()

    from broker.app.main import create_app

    app = create_app()
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    await dispose_engine()


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    """testcontainers PostgreSQL — DB 필요한 테스트만 사용."""
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        pytest.skip("testcontainers 미설치")

    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        url = pg.get_connection_url()
        # alembic 적용
        os.environ["DATABASE_URL"] = url
        from broker.app.core.config import get_settings

        get_settings.cache_clear()

        from alembic.config import Config

        from alembic import command

        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")
        yield url
