"""테스트 fixture.

DB가 필요 없는 테스트는 `client` 만 사용하면 된다.
DB가 필요한 테스트(readyz, alembic, models)는 `pg_url`/`db_session` fixture 사용.

T05 추가 헬퍼:
- `host` / `other_host` — INSERT로 직접 시드한 Host 행 (운영 시드 없음 가정).
- `auth_client(role)` — 로그인 완료된 AsyncClient 발급 (role='user' 또는 'admin').
"""

import os
from collections.abc import AsyncIterator, Iterator
from typing import Protocol

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient


class AuthClientFactory(Protocol):
    """auth_client fixture가 yield하는 호출 객체의 시그니처."""

    async def __call__(
        self,
        *,
        role: str = "user",
        external_id: str | None = None,
        display_name: str | None = None,
    ) -> AsyncClient: ...


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


# ---------------------------------------------------------------------------
# T05 헬퍼 — Host 시드 + 인증된 client 발급.
# ---------------------------------------------------------------------------


async def _insert_host(hostname: str, display_name: str) -> int:
    """Host INSERT 후 PK 반환. hostname 고유성은 호출 측이 관리."""
    from broker.app.infra.db import get_session_factory
    from sqlalchemy import text

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            text(
                "INSERT INTO hosts (hostname, display_name, status) "
                "VALUES (:h, :d, 'OFFLINE') RETURNING id"
            ).bindparams(h=hostname, d=display_name)
        )
        host_id_value: int = result.scalar_one()
        await session.commit()
    return host_id_value


@pytest_asyncio.fixture
async def host(client: AsyncClient) -> int:
    """기본 Host 시드. hostname은 fixture 호출마다 고유. client에 의존해 DB URL 보장."""
    _ = client
    import uuid

    return await _insert_host(f"pc-{uuid.uuid4().hex[:8]}", "강의실 PC")


@pytest_asyncio.fixture
async def other_host(client: AsyncClient) -> int:
    _ = client
    import uuid

    return await _insert_host(f"pc-{uuid.uuid4().hex[:8]}", "다른 강의실 PC")


@pytest_asyncio.fixture
async def auth_client(
    client: AsyncClient,
) -> AsyncIterator[AuthClientFactory]:
    """role='user'/'admin'으로 로그인된 client 발급 헬퍼.

    client fixture에서 lifespan/DATABASE_URL 보장. 각 호출이 새 AsyncClient를 만들어
    독립 cookie jar를 갖는다. fixture teardown이 모두 close.
    """
    from broker.app.main import create_app

    counter = {"n": 0}
    created: list[AsyncClient] = []

    async def _make(
        *,
        role: str = "user",
        external_id: str | None = None,
        display_name: str | None = None,
    ) -> AsyncClient:
        counter["n"] += 1
        ext_id = external_id or f"u-{counter['n']}-{os.urandom(4).hex()}"
        name = display_name or f"User {counter['n']}"

        app = create_app()
        transport = ASGITransport(app=app)
        ac = AsyncClient(transport=transport, base_url="http://test")
        created.append(ac)
        r = await ac.post(
            "/api/v1/auth/mock/callback",
            json={"external_id": ext_id, "display_name": name, "role": role},
        )
        if r.status_code != 200:
            raise RuntimeError(f"mock 로그인 실패: {r.status_code} {r.text}")
        return ac

    try:
        yield _make
    finally:
        for ac in created:
            await ac.aclose()
