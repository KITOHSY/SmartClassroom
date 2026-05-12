"""호스트 메타 read-only API.

- GET / — 인증된 사용자가 호스트 목록(메타데이터)을 조회.

T16 차단 요소 해소 목적. T06 본구현 시:
- POST /agents/heartbeat (ingest)
- GET /hosts/available (상태 필터)
- WebSocket/SSE 실시간 푸시
가 추가되며 본 라우터를 흡수/확장한다.
"""

from __future__ import annotations

from broker.app.api.deps import get_current_user, get_db
from broker.app.api.schemas.host import HostRead
from broker.app.domain.host import Host
from broker.app.domain.user import User
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("", response_model=list[HostRead])
async def list_hosts_endpoint(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[HostRead]:
    """호스트 목록을 id 오름차순으로 반환.

    인증 필수(미인증 401). admin/user 모두 동일 페이로드 — 호스트 메타는 학내 정보로 비공개.
    """
    result = await db.execute(select(Host).order_by(Host.id))
    hosts = result.scalars().all()
    return [HostRead.model_validate(h) for h in hosts]
