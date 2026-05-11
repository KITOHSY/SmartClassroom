"""Mock 인증 흐름 + 세션 미들웨어 통합 테스트 (단계 5/6 검증)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import update


@pytest.mark.asyncio
async def test_mock_login_then_me_then_logout(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/mock/callback",
        json={
            "external_id": "mflow-001",
            "display_name": "Flow User",
            "email": "flow@example.com",
        },
    )
    assert r.status_code == 200, r.text
    assert "broker_session" in r.cookies
    body = r.json()
    assert body["user"]["external_id"] == "mflow-001"
    assert body["user"]["provider"] == "mock"

    r2 = await client.get("/api/v1/auth/me")
    assert r2.status_code == 200
    assert r2.json()["display_name"] == "Flow User"

    r3 = await client.post("/api/v1/auth/logout")
    assert r3.status_code == 200

    r4 = await client.get("/api/v1/auth/me")
    assert r4.status_code == 401


@pytest.mark.asyncio
async def test_me_without_cookie_returns_401_json(client: AsyncClient) -> None:
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401
    body = r.json()
    assert body["error"] == "unauthenticated"
    assert "login_url" in (body.get("detail") or {})


@pytest.mark.asyncio
async def test_me_with_garbage_cookie_returns_401(client: AsyncClient) -> None:
    client.cookies.set("broker_session", "garbage-cookie-value")
    try:
        r = await client.get("/api/v1/auth/me")
        assert r.status_code == 401
    finally:
        client.cookies.clear()


@pytest.mark.asyncio
async def test_expired_session_returns_401(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/mock/callback",
        json={"external_id": "mexp-001", "display_name": "Expired User"},
    )
    assert r.status_code == 200

    from broker.app.domain.token import Token
    from broker.app.infra.db import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        await db.execute(
            update(Token)
            .where(Token.purpose == "session")
            .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )
        await db.commit()

    r2 = await client.get("/api/v1/auth/me")
    assert r2.status_code == 401


@pytest.mark.asyncio
async def test_mock_callback_rejects_missing_fields(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/mock/callback",
        json={"external_id": "mmiss-001"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_mock_callback_redirects_when_accept_html(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/mock/callback",
        json={"external_id": "mhtml-001", "display_name": "HTML User"},
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers.get("location") == "/"
    assert "broker_session" in r.cookies


@pytest.mark.asyncio
async def test_mock_callback_accepts_form_urlencoded(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/mock/callback",
        data={"external_id": "mform-001", "display_name": "Form User"},
    )
    assert r.status_code == 200
    assert r.json()["user"]["external_id"] == "mform-001"
