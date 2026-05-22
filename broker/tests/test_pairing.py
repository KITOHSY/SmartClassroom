"""T08 자동 페어링 테스트.

- push_pin: Sunshine /api/pin 중계 — httpx MockTransport 가짜 Sunshine으로
  happy / retry / 재시도 소진 / 401 / 도달 실패 / 호스트 미설정 검증.
- POST /api/v1/pairing: connect 토큰 검증 + 성공·실패 매핑 (push_pin은 monkeypatch).
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import httpx
import pytest
from broker.app.core.config import Settings
from broker.app.domain.host import Host
from broker.app.services import pairing_service
from broker.app.services.pairing_service import (
    HostNotPairableError,
    PairingRejectedError,
    PairingResult,
    PairingUnreachableError,
    push_pin,
)
from httpx import AsyncClient

if TYPE_CHECKING:
    from broker.tests.conftest import AuthClientFactory


# --- push_pin 단위 테스트 (MockTransport 가짜 Sunshine) -----------------------


def _host(
    ip: str | None = "192.0.2.10",
    pair_token: str | None = "broker-secret",  # noqa: S107  (테스트용 가짜 값)
) -> Host:
    return Host(
        hostname="pc-test",
        display_name="강의실 PC",
        ip_address=ip,
        sunshine_port=47984,
        sunshine_broker_token=pair_token,
    )


def _mock_client(handler: Callable[[httpx.Request], httpx.Response]) -> AsyncClient:
    return AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_push_pin_happy_path() -> None:
    """200 {"status": true} → 1회 시도로 성공."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/pin"
        assert request.headers["authorization"] == "Bearer broker-secret"
        return httpx.Response(200, json={"status": True})

    async with _mock_client(handler) as client:
        result = await push_pin(
            _host(), "1234", reservation_id=1, settings=Settings(), client=client
        )
    assert result.attempts == 1


@pytest.mark.asyncio
async def test_push_pin_retries_then_succeeds() -> None:
    """status:false 2회(세션 레이스) 후 true → 3회째 성공."""
    counter = itertools.count(1)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": next(counter) >= 3})

    async with _mock_client(handler) as client:
        result = await push_pin(
            _host(), "1234", reservation_id=1, settings=Settings(), client=client
        )
    assert result.attempts == 3


@pytest.mark.asyncio
async def test_push_pin_exhausts_on_persistent_false() -> None:
    """status:false 지속 → 재시도 소진 후 PairingRejectedError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": False})

    with pytest.raises(PairingRejectedError) as exc:
        async with _mock_client(handler) as client:
            await push_pin(_host(), "1234", reservation_id=1, settings=Settings(), client=client)
    assert exc.value.reason == "sunshine_rejected"


@pytest.mark.asyncio
async def test_push_pin_401_fails_immediately() -> None:
    """401 → 재시도 없이 즉시 PairingRejectedError (attempts==1)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"status": False})

    with pytest.raises(PairingRejectedError) as exc:
        async with _mock_client(handler) as client:
            await push_pin(_host(), "1234", reservation_id=1, settings=Settings(), client=client)
    assert exc.value.reason == "sunshine_unauthorized"
    assert exc.value.attempts == 1


@pytest.mark.asyncio
async def test_push_pin_unreachable() -> None:
    """연결 거부 지속 → PairingUnreachableError."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(PairingUnreachableError) as exc:
        async with _mock_client(handler) as client:
            await push_pin(_host(), "1234", reservation_id=1, settings=Settings(), client=client)
    assert exc.value.reason == "unreachable"


@pytest.mark.asyncio
async def test_push_pin_host_not_pairable() -> None:
    """ip 또는 sunshine_broker_token 미등록 → HTTP 호출 전 즉시 HostNotPairableError."""
    with pytest.raises(HostNotPairableError):
        await push_pin(_host(ip=None), "1234", reservation_id=1, settings=Settings())
    with pytest.raises(HostNotPairableError):
        await push_pin(_host(pair_token=None), "1234", reservation_id=1, settings=Settings())


# --- POST /api/v1/pairing 엔드포인트 -----------------------------------------


def _grid_floor(dt: datetime) -> datetime:
    dt = dt.replace(second=0, microsecond=0)
    return dt.replace(minute=0 if dt.minute < 30 else 30)


async def _issue_connect_token(ac: AsyncClient, host_id: int) -> str:
    start = _grid_floor(datetime.now(UTC) + timedelta(minutes=35))
    end = start + timedelta(minutes=30)
    r = await ac.post(
        "/api/v1/reservations",
        json={
            "host_id": host_id,
            "starts_at": start.isoformat(),
            "ends_at": end.isoformat(),
        },
    )
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    tr = await ac.post(f"/api/v1/reservations/{rid}/connect")
    assert tr.status_code == 201, tr.text
    token: str = tr.json()["token"]
    return token


@pytest.mark.asyncio
async def test_pairing_invalid_token(auth_client: AuthClientFactory) -> None:
    """위조 connect 토큰 → 401 + manual_pin 폴백 신호."""
    user = await auth_client()
    r = await user.post("/api/v1/pairing", json={"token": "x" * 20, "pin": "1234"})
    assert r.status_code == 401
    body = r.json()
    assert body["error"] == "invalid_connect_token"
    assert body["detail"]["fallback"] == "manual_pin"


@pytest.mark.asyncio
async def test_pairing_pin_format_validated(auth_client: AuthClientFactory, host: int) -> None:
    """pin이 4자리 숫자가 아니면 422 validation_error."""
    user = await auth_client()
    token = await _issue_connect_token(user, host)
    r = await user.post("/api/v1/pairing", json={"token": token, "pin": "abc"})
    assert r.status_code == 422
    assert r.json()["error"] == "validation_error"


@pytest.mark.asyncio
async def test_pairing_success(
    auth_client: AuthClientFactory, host: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """유효 토큰 + PIN 중계 성공 → 200 paired_pending + audit pairing_succeeded."""

    async def fake_push_pin(
        host_obj: Host,
        pin: str,
        *,
        reservation_id: int,
        settings: Settings,
        client: AsyncClient | None = None,
    ) -> PairingResult:
        assert pin == "1234"
        return PairingResult(attempts=2)

    monkeypatch.setattr(pairing_service, "push_pin", fake_push_pin)

    user = await auth_client()
    token = await _issue_connect_token(user, host)
    r = await user.post("/api/v1/pairing", json={"token": token, "pin": "1234"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "paired_pending"
    assert body["host"]["id"] == host

    from broker.app.domain.audit import AuditLog
    from broker.app.infra.db import get_session_factory
    from sqlalchemy import select

    factory = get_session_factory()
    async with factory() as session:
        actions = (
            (
                await session.execute(
                    select(AuditLog.action).where(
                        AuditLog.target_kind == "host",
                        AuditLog.target_id == host,
                        AuditLog.action == "pairing_succeeded",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(actions) == 1


@pytest.mark.asyncio
async def test_pairing_rejected_maps_409(
    auth_client: AuthClientFactory, host: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PairingRejectedError → 409 + audit pairing_failed."""

    async def fake(*_args: object, **_kwargs: object) -> PairingResult:
        raise PairingRejectedError("Sunshine 거부", reason="sunshine_rejected", attempts=5)

    monkeypatch.setattr(pairing_service, "push_pin", fake)

    user = await auth_client()
    token = await _issue_connect_token(user, host)
    r = await user.post("/api/v1/pairing", json={"token": token, "pin": "1234"})
    assert r.status_code == 409
    body = r.json()
    assert body["error"] == "sunshine_rejected"
    assert body["detail"]["fallback"] == "manual_pin"

    from broker.app.domain.audit import AuditLog
    from broker.app.infra.db import get_session_factory
    from sqlalchemy import select

    factory = get_session_factory()
    async with factory() as session:
        actions = (
            (
                await session.execute(
                    select(AuditLog.action).where(
                        AuditLog.target_kind == "host",
                        AuditLog.target_id == host,
                        AuditLog.action == "pairing_failed",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(actions) == 1


@pytest.mark.asyncio
async def test_pairing_unreachable_maps_502(
    auth_client: AuthClientFactory, host: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PairingUnreachableError → 502."""

    async def fake(*_args: object, **_kwargs: object) -> PairingResult:
        raise PairingUnreachableError("도달 실패", reason="unreachable", attempts=5)

    monkeypatch.setattr(pairing_service, "push_pin", fake)

    user = await auth_client()
    token = await _issue_connect_token(user, host)
    r = await user.post("/api/v1/pairing", json={"token": token, "pin": "1234"})
    assert r.status_code == 502


@pytest.mark.asyncio
async def test_pairing_host_not_pairable_maps_422(
    auth_client: AuthClientFactory, host: int
) -> None:
    """host 픽스처는 ip/sunshine_broker_token 미등록 → 실제 push_pin이 422로 매핑."""
    user = await auth_client()
    token = await _issue_connect_token(user, host)
    r = await user.post("/api/v1/pairing", json={"token": token, "pin": "1234"})
    assert r.status_code == 422
    assert r.json()["error"] == "missing_ip_or_token"
