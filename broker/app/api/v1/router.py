from broker.app.api.v1 import auth, meta, reservations
from fastapi import APIRouter

api_router = APIRouter()
api_router.include_router(meta.router, tags=["meta"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(reservations.router, prefix="/reservations", tags=["reservations"])

# 후속 태스크 추가 지점:
# from broker.app.api.v1 import hosts, tokens, sessions
# api_router.include_router(hosts.router, prefix="/hosts", tags=["hosts"])
# api_router.include_router(tokens.router, prefix="/tokens", tags=["tokens"])
# api_router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
