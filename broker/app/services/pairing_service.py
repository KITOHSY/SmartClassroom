"""T08 자동 페어링 서비스 — Sunshine confighttp `/api/pin` PIN 중계.

설계 (plan A1):
- 클라이언트(Moonlight)가 PIN을 생성하고 페어링 핸드셰이크를 *먼저* 시작 → Sunshine
  세션이 PIN을 기다리며 블록. 그 PIN을 Broker가 받아 Sunshine `/api/pin`으로 중계한다.
- 호출은 `Authorization: Bearer <host.sunshine_broker_token>` (T10 패치가 연 경로).
- Sunshine confighttp는 자가서명 HTTPS(포트 47990) — `verify=settings.sunshine_tls_verify`
  (기본 False, 캠퍼스 LAN 전제). cert pinning은 후속 강화 후보.
- 재시도: 클라이언트가 막 띄운 페어링 세션이 아직 없을 짧은 레이스 + 일시적 네트워크
  오류를 흡수. 지수 백오프. 401·그 외 4xx 같은 명백한 거부는 즉시 실패.

`sunshine_broker_token`은 로그·audit·예외 메시지 어디에도 남기지 않는다 (아웃바운드 시크릿).
commit은 호출자(router) 책임 — 본 모듈은 DB를 만지지 않는다.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx
from broker.app.core.config import Settings
from broker.app.core.logging import get_logger
from broker.app.domain.host import Host

log = get_logger(__name__)


class PairingError(Exception):
    """T08 페어링 도메인 예외 베이스 — 라우터가 HTTP로 매핑."""

    def __init__(self, message: str, *, reason: str, attempts: int = 0) -> None:
        super().__init__(message)
        self.message = message
        self.reason = reason
        self.attempts = attempts


class HostNotPairableError(PairingError):
    """호스트에 ip_address 또는 sunshine_broker_token 미등록 — 페어링 시작 불가."""


class PairingUnreachableError(PairingError):
    """Sunshine confighttp 도달 실패(연결 거부/타임아웃/5xx) — 재시도 소진."""


class PairingRejectedError(PairingError):
    """Sunshine이 PIN을 거부 — 401 인증 실패 / status:false 지속 / 그 외 4xx."""


@dataclass
class PairingResult:
    attempts: int


def _is_transient_status(status_code: int) -> bool:
    """5xx만 일시적으로 간주 — 그 외 4xx는 즉시 실패(401은 별도 처리)."""
    return status_code >= 500


def _sunshine_accepted(resp: httpx.Response) -> bool:
    """Sunshine `/api/pin` 응답의 `{"status": true}` 판정. 비-JSON/키 누락은 False."""
    try:
        payload = resp.json()
    except ValueError:
        return False
    return isinstance(payload, dict) and payload.get("status") is True


async def push_pin(
    host: Host,
    pin: str,
    *,
    reservation_id: int,
    settings: Settings,
    client: httpx.AsyncClient | None = None,
) -> PairingResult:
    """Sunshine `/api/pin`에 PIN을 중계. 성공 시 PairingResult, 실패 시 PairingError 계열 raise.

    `client`가 주입되면 그것을 쓰고 닫지 않는다(테스트용). 없으면 내부 생성·정리.
    """
    ip = host.ip_address
    token = host.sunshine_broker_token
    if not ip or not token:
        raise HostNotPairableError(
            "호스트에 IP 또는 Sunshine 페어링 토큰이 등록되지 않았습니다",
            reason="missing_ip_or_token",
        )

    url = f"https://{ip}:{settings.sunshine_config_port}/api/pin"
    headers = {"Authorization": f"Bearer {token}"}
    body = {"pin": pin, "name": f"sc-res-{reservation_id}"}
    max_attempts = max(1, settings.sunshine_pair_max_attempts)
    base = settings.sunshine_pair_backoff_base_seconds

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            verify=settings.sunshine_tls_verify,
            timeout=settings.sunshine_request_timeout_seconds,
        )
    try:
        last_reason = "unreachable"
        for attempt in range(1, max_attempts + 1):
            try:
                resp = await client.post(url, json=body, headers=headers)
            except httpx.TransportError as exc:
                last_reason = "unreachable"
                log.warning(
                    "pairing.attempt_failed",
                    host_id=host.id,
                    attempt=attempt,
                    error=type(exc).__name__,
                )
            else:
                if resp.status_code == 401:
                    # broker_api_token 불일치 — 재시도 무의미.
                    raise PairingRejectedError(
                        "Sunshine이 Broker 인증을 거부했습니다 (broker_api_token 불일치)",
                        reason="sunshine_unauthorized",
                        attempts=attempt,
                    )
                if 200 <= resp.status_code < 300:
                    if _sunshine_accepted(resp):
                        return PairingResult(attempts=attempt)
                    # status:false — 페어링 세션 아직 없음(레이스) 또는 PIN 불일치. 재시도.
                    last_reason = "sunshine_rejected"
                elif _is_transient_status(resp.status_code):
                    last_reason = "sunshine_server_error"
                    log.warning(
                        "pairing.attempt_failed",
                        host_id=host.id,
                        attempt=attempt,
                        status=resp.status_code,
                    )
                else:
                    # 그 외 4xx — 즉시 실패.
                    raise PairingRejectedError(
                        f"Sunshine이 요청을 거부했습니다 (HTTP {resp.status_code})",
                        reason="sunshine_rejected",
                        attempts=attempt,
                    )

            if attempt < max_attempts:
                await asyncio.sleep(base * (2 ** (attempt - 1)))

        # 재시도 소진.
        if last_reason == "sunshine_rejected":
            raise PairingRejectedError(
                "Sunshine이 PIN을 받지 못했습니다 (페어링 세션 부재 또는 PIN 불일치)",
                reason="sunshine_rejected",
                attempts=max_attempts,
            )
        raise PairingUnreachableError(
            "Sunshine confighttp에 도달하지 못했습니다",
            reason=last_reason,
            attempts=max_attempts,
        )
    finally:
        if owns_client:
            await client.aclose()
