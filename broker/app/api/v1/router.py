from broker.app.api.v1 import auth, hosts, meta, reservations, tokens
from fastapi import APIRouter

api_router = APIRouter()
api_router.include_router(meta.router, tags=["meta"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(reservations.router, prefix="/reservations", tags=["reservations"])
api_router.include_router(tokens.router, prefix="/tokens", tags=["tokens"])
# T16 차단 요소 해소용 read-only 라우터 — T06 본구현 시 ingest/상태머신/필터 추가하며 흡수.
api_router.include_router(hosts.router, prefix="/hosts", tags=["hosts"])

# 후속 태스크 추가 지점:
# from broker.app.api.v1 import sessions
# api_router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
