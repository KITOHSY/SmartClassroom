"""T08 — /tokens/verify 내부 인증(X-Internal-Token) 가드 테스트 (§11 A6).

T07 시점 임시 가드(`require_admin`)를 X-Internal-Token 헤더 공유 비밀로 교체했다.
내부 컴포넌트(Sunshine fork 등)는 사용자/admin 세션이 없는 머신이므로 별도 채널을 쓴다.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

# conftest._set_test_env의 INTERNAL_API_TOKEN 기본값.
VALID_HEADERS = {"X-Internal-Token": "test-internal-token"}
_GARBAGE_TOKEN = "AAAAAAAAAAAAAAAAAAAAAAAA"


@pytest.mark.asyncio
async def test_no_header_rejected(client: AsyncClient) -> None:
    """X-Internal-Token 헤더 부재 → 401 invalid_internal_token."""
    r = await client.post("/api/v1/tokens/verify", json={"token": _GARBAGE_TOKEN, "consume": False})
    assert r.status_code == 401
    assert r.json()["error"] == "invalid_internal_token"


@pytest.mark.asyncio
async def test_wrong_header_rejected(client: AsyncClient) -> None:
    """틀린 토큰 값 → 401."""
    r = await client.post(
        "/api/v1/tokens/verify",
        json={"token": _GARBAGE_TOKEN, "consume": False},
        headers={"X-Internal-Token": "wrong-token-value"},
    )
    assert r.status_code == 401
    assert r.json()["error"] == "invalid_internal_token"


@pytest.mark.asyncio
async def test_valid_header_passes(client: AsyncClient) -> None:
    """올바른 토큰 → 인증 통과. token이 garbage라 valid=False지만 200이면 인증 통과한 것."""
    r = await client.post(
        "/api/v1/tokens/verify",
        json={"token": _GARBAGE_TOKEN, "consume": False},
        headers=VALID_HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["valid"] is False
