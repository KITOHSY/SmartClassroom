"""Broker로의 자기-RTT 측정 — `/healthz` 1회 GET 후 ms 단위 elapsed."""

from __future__ import annotations

import time

import httpx


async def measure_rtt(broker_url: str, *, timeout_sec: float = 5.0) -> float | None:
    """broker /healthz GET 후 elapsed_ms. 실패 시 None."""
    url = broker_url.rstrip("/") + "/healthz"
    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            start = time.perf_counter()
            r = await client.get(url)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            if r.status_code == 200:
                return round(elapsed_ms, 2)
    except (httpx.HTTPError, OSError):
        return None
    return None
