"""T08 자동 페어링 Pydantic 스키마.

- PairingRequest: POST /api/v1/pairing 요청 — connect 토큰(인증 겸용) + 클라이언트 PIN.
- PairingResponse: PIN 중계 성공 응답 — 호스트 접속정보 임베딩.

connect 토큰 raw는 요청에만 실린다. 응답은 토큰을 돌려주지 않는다.
"""

from __future__ import annotations

from broker.app.api.schemas.token import HostConnectionInfo
from pydantic import BaseModel, ConfigDict, Field


class PairingRequest(BaseModel):
    """POST /api/v1/pairing 요청 — connect 토큰 + Moonlight가 생성한 4자리 PIN."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(..., min_length=16, description="connect 토큰 raw 값 (인증 겸용)")
    pin: str = Field(..., pattern=r"^\d{4}$", description="Moonlight가 생성한 4자리 PIN")


class PairingResponse(BaseModel):
    """페어링 PIN 중계 성공 응답.

    `status='paired_pending'` — Broker가 Sunshine에 PIN을 전달했음을 뜻한다. 핸드셰이크
    완성은 클라이언트↔Sunshine 사이에서 진행되며 Broker는 거기까지 관여하지 않는다.
    """

    status: str
    host: HostConnectionInfo
