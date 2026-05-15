"""collectors/rtt.py — pytest-httpx로 broker /healthz mock 응답 측정."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock


@pytest.mark.asyncio
async def test_measure_rtt_returns_float_on_200(httpx_mock: HTTPXMock) -> None:
    from smartclassroom_agent.collectors.rtt import measure_rtt

    httpx_mock.add_response(
        url="http://broker.test/healthz",
        status_code=200,
        json={"status": "ok"},
    )
    rtt = await measure_rtt("http://broker.test")
    assert rtt is not None
    assert rtt >= 0.0


@pytest.mark.asyncio
async def test_measure_rtt_returns_none_on_5xx(httpx_mock: HTTPXMock) -> None:
    from smartclassroom_agent.collectors.rtt import measure_rtt

    httpx_mock.add_response(url="http://broker.test/healthz", status_code=503)
    assert await measure_rtt("http://broker.test") is None


@pytest.mark.asyncio
async def test_measure_rtt_returns_none_on_connect_error(httpx_mock: HTTPXMock) -> None:
    import httpx
    from smartclassroom_agent.collectors.rtt import measure_rtt

    httpx_mock.add_exception(httpx.ConnectError("refused"))
    assert await measure_rtt("http://broker.test") is None
