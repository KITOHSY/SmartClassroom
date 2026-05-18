"""GET /api/v1/hosts read-only API 테스트 (T16 차단 요소 해소).

- 미인증 → 401 + login_url 안내
- user 200 + 페이로드 shape
- admin 200 + 동일 페이로드 (역할 무관)
- 다수 호스트 시드 후 id 오름차순 정렬
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from httpx import AsyncClient

if TYPE_CHECKING:
    from broker.tests.conftest import AuthClientFactory


@pytest.mark.asyncio
async def test_hosts_requires_auth(client: AsyncClient) -> None:
    """쿠키 없이 호출 → 401 + 통일 에러 형식."""
    r = await client.get("/api/v1/hosts")
    assert r.status_code == 401
    body = r.json()
    assert body["error"] == "unauthenticated"
    assert "login_url" in body["detail"]


@pytest.mark.asyncio
async def test_hosts_user_returns_payload(auth_client: AuthClientFactory, host: int) -> None:
    """user 세션 → 200, host fixture로 시드한 행이 보임."""
    user = await auth_client(role="user")
    r = await user.get("/api/v1/hosts")
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    rows = [row for row in body if row["id"] == host]
    assert len(rows) == 1
    row = rows[0]
    assert row["display_name"] == "강의실 PC"
    assert row["status"] == "OFFLINE"
    assert row["sunshine_port"] == 47984
    assert "hostname" in row
    assert "location" in row  # null 허용 필드


@pytest.mark.asyncio
async def test_hosts_admin_same_payload(auth_client: AuthClientFactory, host: int) -> None:
    """admin 세션 → 200, user와 동일 페이로드(역할 분기 없음)."""
    admin = await auth_client(role="admin")
    r = await admin.get("/api/v1/hosts")
    assert r.status_code == 200, r.text
    body = r.json()
    rows = [row for row in body if row["id"] == host]
    assert len(rows) == 1
    keys = set(rows[0].keys())
    assert keys == {
        "id",
        "hostname",
        "display_name",
        "location",
        "status",
        "sunshine_port",
        "ip_address",
    }


@pytest.mark.asyncio
async def test_hosts_sorted_by_id_ascending(
    auth_client: AuthClientFactory, host: int, other_host: int
) -> None:
    """다수 시드 → id 오름차순 (행은 id 기준 단조 증가)."""
    user = await auth_client()
    r = await user.get("/api/v1/hosts")
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [row["id"] for row in body]
    assert ids == sorted(ids)
    assert host in ids
    assert other_host in ids
