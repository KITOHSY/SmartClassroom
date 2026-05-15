"""T11 admin Host enrollment 라우터 테스트.

- POST /hosts admin → 201 + raw agent_token + DB jti = sha256(raw)
- POST /hosts user → 403 (관리자 권한 필요)
- POST /hosts 미인증 → 401
- POST /hosts 중복 hostname → 409
- POST /hosts/{id}/agent-token admin → 200 + 이전 토큰 일괄 revoke
- POST /hosts/{id}/agent-token 존재하지 않는 host → 404
"""

from __future__ import annotations

import hashlib
import uuid
from typing import TYPE_CHECKING

import pytest
from broker.app.services.agent_token_service import verify_agent_token
from httpx import AsyncClient

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from broker.tests.conftest import AuthClientFactory
    from sqlalchemy.ext.asyncio import AsyncSession


import pytest_asyncio


@pytest_asyncio.fixture
async def db(client: AsyncClient) -> AsyncIterator[AsyncSession]:
    _ = client
    from broker.app.infra.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        yield session


def _payload(hostname: str | None = None) -> dict[str, object]:
    return {
        "hostname": hostname or f"pc-{uuid.uuid4().hex[:8]}",
        "display_name": "테스트 강의실 PC",
        "location": "공대5호관 401호",
        "sunshine_port": 47984,
    }


@pytest.mark.asyncio
async def test_admin_creates_host_and_receives_raw_token(
    auth_client: AuthClientFactory, db: AsyncSession
) -> None:
    """admin → 201, agent_token raw 1회 응답, DB는 sha256(raw)만 저장."""
    admin = await auth_client(role="admin")
    body = _payload()
    r = await admin.post("/api/v1/hosts", json=body)
    assert r.status_code == 201, r.text
    payload = r.json()

    assert payload["hostname"] == body["hostname"]
    assert payload["display_name"] == body["display_name"]
    assert payload["status"] == "OFFLINE"
    assert payload["sunshine_port"] == 47984
    raw_token = payload["agent_token"]
    assert isinstance(raw_token, str) and len(raw_token) >= 32
    assert payload["revoked_previous"] == 0

    # raw로 verify 통과 + DB의 jti가 sha256(raw)인지 검증
    token = await verify_agent_token(db, raw_token)
    assert token is not None
    assert token.jti == hashlib.sha256(raw_token.encode()).hexdigest()
    assert token.host_id == payload["id"]


@pytest.mark.asyncio
async def test_user_role_forbidden(auth_client: AuthClientFactory) -> None:
    """user 세션 → 403 (require_admin)."""
    user = await auth_client(role="user")
    r = await user.post("/api/v1/hosts", json=_payload())
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_unauthenticated_returns_401(client: AsyncClient) -> None:
    r = await client.post("/api/v1/hosts", json=_payload())
    assert r.status_code == 401
    assert r.json()["error"] == "unauthenticated"


@pytest.mark.asyncio
async def test_duplicate_hostname_returns_409(auth_client: AuthClientFactory) -> None:
    """동일 hostname 두 번 등록 시 두 번째는 409."""
    admin = await auth_client(role="admin")
    body = _payload()
    r1 = await admin.post("/api/v1/hosts", json=body)
    assert r1.status_code == 201, r1.text
    r2 = await admin.post("/api/v1/hosts", json=body)
    assert r2.status_code == 409, r2.text
    assert r2.json()["error"] == "hostname_conflict"
    assert r2.json()["detail"]["hostname"] == body["hostname"]


@pytest.mark.asyncio
async def test_rotate_agent_token_revokes_previous(
    auth_client: AuthClientFactory, db: AsyncSession
) -> None:
    """재발급 → 이전 토큰은 verify 실패, 새 토큰은 통과."""
    admin = await auth_client(role="admin")
    create = await admin.post("/api/v1/hosts", json=_payload())
    assert create.status_code == 201
    host_id = create.json()["id"]
    old_token = create.json()["agent_token"]

    rotate = await admin.post(f"/api/v1/hosts/{host_id}/agent-token")
    assert rotate.status_code == 200, rotate.text
    new_token = rotate.json()["agent_token"]
    assert rotate.json()["revoked_previous"] == 1
    assert new_token != old_token

    assert await verify_agent_token(db, old_token) is None
    assert await verify_agent_token(db, new_token) is not None


@pytest.mark.asyncio
async def test_rotate_unknown_host_returns_404(auth_client: AuthClientFactory) -> None:
    admin = await auth_client(role="admin")
    r = await admin.post("/api/v1/hosts/999999/agent-token")
    assert r.status_code == 404, r.text
    assert r.json()["error"] == "host_not_found"
    assert r.json()["detail"]["host_id"] == 999999
