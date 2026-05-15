from fastapi import FastAPI
from prometheus_client import Counter, Gauge, Histogram
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

# T06 — heartbeat 수신 시 갱신, OFFLINE 전이 시 라벨 정리.
# label은 hostname만 (host_id 동시 노출은 high-cardinality 회피).
# 1m/5m 평균은 Prometheus의 avg_over_time이 담당 — broker DB는 latest만.
HOST_CPU_PERCENT = Gauge(
    "broker_host_cpu_percent",
    "호스트 CPU 사용률 (heartbeat 시 갱신)",
    labelnames=("hostname",),
)
HOST_MEM_PERCENT = Gauge(
    "broker_host_mem_percent",
    "호스트 메모리 사용률 (heartbeat 시 갱신)",
    labelnames=("hostname",),
)
HOST_GPU_PERCENT = Gauge(
    "broker_host_gpu_percent",
    "호스트 GPU 사용률 — 다중 GPU는 max (heartbeat 시 갱신)",
    labelnames=("hostname",),
)
HOST_STATUS_INFO = Gauge(
    "broker_host_status_info",
    "호스트 상태 indicator — 현재 상태만 1, 나머지 0",
    labelnames=("hostname", "status"),
)


def set_host_status_indicator(hostname: str, status: str) -> None:
    """status enum을 1/0 indicator로 변환해 set."""
    for s in ("OFFLINE", "IDLE", "IN_USE", "DEGRADED"):
        HOST_STATUS_INFO.labels(hostname=hostname, status=s).set(1.0 if s == status else 0.0)


def clear_host_metrics(hostname: str) -> None:
    """OFFLINE 전이 시 stale label 제거 — high-cardinality 방어."""
    import contextlib

    for gauge in (HOST_CPU_PERCENT, HOST_MEM_PERCENT, HOST_GPU_PERCENT):
        with contextlib.suppress(KeyError):
            gauge.remove(hostname)


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
