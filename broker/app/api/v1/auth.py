"""인증 라우트.

- GET  /auth/mock/login    : Mock 로그인 HTML 폼 (개발/스테이징/test 한정)
- POST /auth/mock/callback : form 또는 JSON 본문 수용 → 세션 발급
- POST /auth/logout        : 본인 세션 revoke
- GET  /auth/me            : 현재 사용자 정보

T04b 슬롯 (구현 X — 라우트 등록은 T04b 작업자가 채움):
- GET  /auth/cnu-sso/login            → CnuSsoProvider.initiate_login() 302
- GET  /auth/cnu-sso/callback         → CnuSsoProvider.verify_callback() + 세션 발급
- POST /auth/cnu-sso/logout?logout=1  → SLO 수신 (revoke_all_sessions_for_user)
"""

from __future__ import annotations

from pathlib import Path

from broker.app.api.deps import get_current_user, get_db
from broker.app.core.auth_session import issue_session, revoke_session
from broker.app.core.config import Settings, get_settings
from broker.app.domain.audit import write_audit
from broker.app.domain.user import User
from broker.app.providers import get_active_provider
from broker.app.services.user_upsert import upsert_user
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, ORJSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _set_session_cookie(response: Response, raw_cookie: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_cookie,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        domain=settings.cookie_domain,
        path="/",
    )


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _wants_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/html" in accept


@router.get("/mock/login", include_in_schema=False)
async def mock_login_form(
    request: Request, settings: Settings = Depends(get_settings)
) -> HTMLResponse:
    if settings.app_env == "production":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return templates.TemplateResponse(request, "mock_login.html")


@router.post("/mock/callback")
async def mock_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    if settings.app_env == "production":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    provider = get_active_provider(settings)
    if provider.name != "mock":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AUTH_PROVIDER가 mock이 아닙니다",
        )

    try:
        identity = await provider.verify_callback(request)
    except ValueError as exc:
        await write_audit(
            db,
            action="login_failure",
            actor_user_id=None,
            actor_kind="user",
            result="failure",
            auth_provider=provider.name,
            ip_address=_client_ip(request),
            detail={"reason": str(exc)},
        )
        await db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    user = await upsert_user(db, identity)
    raw_cookie, token = await issue_session(db, user, ttl_seconds=settings.session_ttl_seconds)
    await write_audit(
        db,
        action="login_success",
        actor_user_id=user.id,
        actor_kind="user",
        result="success",
        auth_provider=provider.name,
        ip_address=_client_ip(request),
        target_kind="token",
        target_id=token.id,
    )
    await db.commit()

    response: Response
    if _wants_html(request):
        response = RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    else:
        response = ORJSONResponse(
            content={
                "user": {
                    "external_id": user.external_id,
                    "display_name": user.display_name,
                    "email": user.email,
                    "role": user.role,
                    "provider": user.provider,
                },
                "expires_at": token.expires_at.isoformat(),
            }
        )
    _set_session_cookie(response, raw_cookie, settings)
    return response


@router.post("/logout")
async def logout(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ORJSONResponse:
    raw_cookie = request.cookies.get(settings.session_cookie_name)
    user_obj = getattr(request.state, "user", None)
    user_id = getattr(user_obj, "id", None) if user_obj is not None else None
    if raw_cookie:
        revoked = await revoke_session(db, raw_cookie)
        if revoked:
            await write_audit(
                db,
                action="logout",
                actor_user_id=user_id,
                actor_kind="user",
                result="success",
                auth_provider=settings.auth_provider,
                ip_address=_client_ip(request),
            )
            await db.commit()
    response = ORJSONResponse(content={"ok": True})
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        domain=settings.cookie_domain,
    )
    return response


@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> dict[str, object]:
    return {
        "id": user.id,
        "external_id": user.external_id,
        "display_name": user.display_name,
        "email": user.email,
        "role": user.role,
        "provider": user.provider,
    }
