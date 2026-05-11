from broker.app.core.config import get_settings
from fastapi import APIRouter

router = APIRouter()


@router.get("/version", tags=["meta"])
async def version() -> dict[str, str]:
    settings = get_settings()
    return {"version": settings.app_version, "env": settings.app_env}
