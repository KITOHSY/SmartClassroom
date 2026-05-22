"""T07 토큰 검증 API 테스트.

- 내부 인증(X-Internal-Token) 가드 (T08 §11 A6)
- 무효 시그니처
- 만료 토큰
- consume=False 비파괴
- 응답 페이로드 shape
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from httpx import AsyncClient

if TYPE_CHECKING:
    from broker.tests.conftest import AuthClientFactory

# conftest._set_test_env의 INTERNAL_API_TOKEN 기본값과 일치.
INTERNAL_HEADERS = {"X-Internal-Token": "test-internal-token"}


def _grid_floor(dt: datetime) -> datetime:
    dt = dt.replace(second=0, microsecond=0)
    return dt.replace(minute=0 if dt.minute < 30 else 30)


def _near_future_slot(start_offset_minutes: int = 5) -> tuple[str, str]:
    start = _grid_floor(datetime.now(UTC) + timedelta(minutes=start_offset_minutes + 30))
    end = start + timedelta(minutes=30)
    return start.isoformat(), end.isoformat()


async def _create_reservation(ac: AsyncClient, host_id: int) -> int:
    starts, ends = _near_future_slot(5)
    r = await ac.post(
        "/api/v1/reservations",
        json={"host_id": host_id, "starts_at": starts, "ends_at": ends},
    )
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


async def _issue_token(ac: AsyncClient, host_id: int) -> tuple[int, str]:
    rid = await _create_reservation(ac, host_id)
    r = await ac.post(f"/api/v1/reservations/{rid}/connect")
    assert r.status_code == 201, r.text
    return rid, r.json()["token"]


@pytest.mark.asyncio
async def test_verify_requires_internal_token(auth_client: AuthClientFactory, host: int) -> None:
    """X-Internal-Token 헤더 없으면 401 — admin 세션으로도 통과 못 함 (§11 A6)."""
    owner = await auth_client()
    admin = await auth_client(role="admin")
    _, raw = await _issue_token(owner, host)

    # 헤더 없음 → 401 (admin 세션이어도 더 이상 통과 못 함).
    r = await admin.post("/api/v1/tokens/verify", json={"token": raw, "consume": False})
    assert r.status_code == 401

    # 올바른 헤더 → 200.
    r2 = await admin.post(
        "/api/v1/tokens/verify",
        json={"token": raw, "consume": False},
        headers=INTERNAL_HEADERS,
    )
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_verify_invalid_signature(
    auth_client: AuthClientFactory,
) -> None:
    """무작위 base64 → 200 valid=False reason=invalid_or_expired."""
    caller = await auth_client()
    r = await caller.post(
        "/api/v1/tokens/verify",
        json={"token": "AAAAAAAAAAAAAAAAAAAAAAAA", "consume": False},
        headers=INTERNAL_HEADERS,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is False
    assert body["reason"] == "invalid_or_expired"
    assert body["user_id"] is None
    assert body["host_id"] is None
    assert body["reservation_id"] is None


@pytest.mark.asyncio
async def test_verify_expired_token(auth_client: AuthClientFactory, host: int) -> None:
    """DB 직접 UPDATE로 expires_at 과거화 → valid=False."""
    owner = await auth_client()
    _, raw = await _issue_token(owner, host)

    import hashlib

    from broker.app.infra.db import get_session_factory
    from sqlalchemy import text

    jti = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            text(
                "UPDATE tokens SET expires_at = now() - interval '1 minute' WHERE jti = :j"
            ).bindparams(j=jti)
        )
        await session.commit()

    r = await owner.post(
        "/api/v1/tokens/verify",
        json={"token": raw, "consume": True},
        headers=INTERNAL_HEADERS,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is False
    assert body["reason"] == "invalid_or_expired"


@pytest.mark.asyncio
async def test_verify_consume_false_does_not_consume(
    auth_client: AuthClientFactory, host: int
) -> None:
    """consume=False 후 동일 토큰 consume=True 호출 → 두 번째도 valid=True."""
    owner = await auth_client()
    _, raw = await _issue_token(owner, host)

    r1 = await owner.post(
        "/api/v1/tokens/verify",
        json={"token": raw, "consume": False},
        headers=INTERNAL_HEADERS,
    )
    assert r1.status_code == 200
    assert r1.json()["valid"] is True

    r2 = await owner.post(
        "/api/v1/tokens/verify",
        json={"token": raw, "consume": True},
        headers=INTERNAL_HEADERS,
    )
    assert r2.status_code == 200
    assert r2.json()["valid"] is True


@pytest.mark.asyncio
async def test_verify_response_payload_shape(auth_client: AuthClientFactory, host: int) -> None:
    """valid=True 응답에 user_id/host_id/reservation_id/expires_at 모두 채워짐."""
    owner = await auth_client()
    rid, raw = await _issue_token(owner, host)

    r = await owner.post(
        "/api/v1/tokens/verify",
        json={"token": raw, "consume": False},
        headers=INTERNAL_HEADERS,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is True
    assert body["reason"] is None
    assert isinstance(body["user_id"], int) and body["user_id"] > 0
    assert body["host_id"] == host
    assert body["reservation_id"] == rid
    assert body["expires_at"] is not None
