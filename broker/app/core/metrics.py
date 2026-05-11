from fastapi import FastAPI
from prometheus_client import Counter, Histogram
from prometheus_fastapi_instrumentator import Instrumentator, metrics

# 후속 태스크용 커스텀 메트릭 슬롯 (T05/T07/T08이 호출)
RESERVATION_CONFLICT_TOTAL = Counter(
    "broker_reservation_conflict_total",
    "예약 슬롯 충돌 발생 횟수",
    labelnames=("host_id",),
)
TOKEN_ISSUED_TOTAL = Counter(
    "broker_token_issued_total",
    "동적 접속 토큰 발급 횟수",
    labelnames=("purpose",),
)
PAIRING_DURATION_SECONDS = Histogram(
    "broker_pairing_duration_seconds",
    "자동 페어링 소요 시간",
    labelnames=("result",),
)


def setup_metrics(app: FastAPI) -> Instrumentator:
    instrumentator = (
        Instrumentator(
            should_group_status_codes=False,
            should_ignore_untemplated=True,
            should_respect_env_var=True,
            env_var_name="ENABLE_METRICS",
            excluded_handlers=["/healthz", "/readyz", "/metrics"],
        )
        .add(metrics.default())
        .add(metrics.latency(buckets=(0.025, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0)))
        .add(metrics.requests())
    )
    instrumentator.instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    return instrumentator
