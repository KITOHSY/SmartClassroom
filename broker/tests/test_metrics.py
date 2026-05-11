import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_metrics_endpoint(client_no_lifespan: AsyncClient) -> None:
    # 워밍업 요청으로 메트릭 카운터 채우기
    await client_no_lifespan.get("/api/v1/version")
    response = await client_no_lifespan.get("/metrics")
    assert response.status_code == 200
    text = response.text
    # prometheus-fastapi-instrumentator 표준 메트릭 (type 선언) 존재 확인
    assert "# TYPE http_request_duration_seconds histogram" in text
    assert "# TYPE http_requests_total counter" in text
    # 후속 태스크용 커스텀 메트릭 슬롯도 노출되는지
    assert "broker_reservation_conflict_total" in text
    assert "broker_token_issued_total" in text


@pytest.mark.asyncio
async def test_metrics_excludes_health(client_no_lifespan: AsyncClient) -> None:
    for _ in range(3):
        await client_no_lifespan.get("/healthz")
    response = await client_no_lifespan.get("/metrics")
    text = response.text
    # /healthz는 라벨링 제외 대상
    assert "/healthz" not in text
