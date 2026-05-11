import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_request_id_reflected_in_response_header(
    client_no_lifespan: AsyncClient,
) -> None:
    response = await client_no_lifespan.get("/healthz", headers={"X-Request-ID": "test-rid-001"})
    assert response.headers.get("X-Request-ID") == "test-rid-001"


@pytest.mark.asyncio
async def test_request_id_generated_when_absent(
    client_no_lifespan: AsyncClient,
) -> None:
    response = await client_no_lifespan.get("/healthz")
    rid = response.headers.get("X-Request-ID")
    assert rid is not None
    assert len(rid) >= 16
