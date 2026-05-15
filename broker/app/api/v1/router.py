from broker.app.api.v1 import agents, auth, host_events, hosts, meta, reservations, tokens
from fastapi import APIRouter

api_router = APIRouter()
api_router.include_router(meta.router, tags=["meta"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(reservations.router, prefix="/reservations", tags=["reservations"])
api_router.include_router(tokens.router, prefix="/tokens", tags=["tokens"])
# T16 차단 요소 해소용 read-only 라우터 + T11 admin enrollment — T06 본구현이 흡수.
api_router.include_router(hosts.router, prefix="/hosts", tags=["hosts"])
# T11 호스트 에이전트 ingest — heartbeat 등. T06 본구현이 상태머신/필터 흡수.
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
# T06 — 관리자용 SSE 채널.
api_router.include_router(host_events.router, prefix="/events", tags=["events"])

# 후속 태스크 추가 지점:
# from broker.app.api.v1 import sessions
# api_router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
