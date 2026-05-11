# 인증 — AuthProvider · 세션 · SLO 가이드

> T04a 산출물. 신규 Provider(T04b CNU SSO 등)를 추가할 때 이 문서를 따른다.

## 1. 전체 구조

```
[브라우저] ──쿠키──► [AuthSessionMiddleware] ─► request.state.user 세팅
                                              │
                                              ▼
                                  [라우터 + Depends(get_current_user)]
                                              │
                                              ▼ (미인증 시 UnauthenticatedError)
                                  [errors.py 핸들러 → Accept 분기 응답]
```

- **세션 토큰** = 서버사이드 opaque. 쿠키 raw 값은 `secrets.token_urlsafe(32)`. DB(`tokens.purpose='session'`)에는 `sha256(raw)`만 저장.
- **인증 강제** = dependency가 담당. 미들웨어는 식별만.
- **미인증 응답** = `/api/*` 경로 또는 JSON 요청은 401 JSON, 그 외 + `Accept: text/html`은 302 redirect to `provider.initiate_login()`.

## 2. 파일 인벤토리

| 파일 | 역할 |
|---|---|
| `broker/app/core/auth.py` | `AuthProvider` Protocol + `UserIdentity` dataclass |
| `broker/app/providers/__init__.py` | `get_active_provider(settings)` 팩토리 (`@lru_cache`) |
| `broker/app/providers/mock.py` | `MockAuthProvider` — 학번/이름 폼 입력 즉시 식별 |
| `broker/app/providers/cnu_sso.py` | `CnuSsoProvider` — T04b 슬롯 (NotImplementedError) |
| `broker/app/core/auth_session.py` | `issue_session` / `verify_session` / `revoke_session` / `revoke_all_sessions_for_user` |
| `broker/app/core/auth_responses.py` | `UnauthenticatedError` + Accept 분기 응답 |
| `broker/app/core/middleware.py` | `AuthSessionMiddleware` (쿠키→user, structlog bind) |
| `broker/app/api/deps.py` | `get_current_user` / `get_optional_user` / `require_admin` |
| `broker/app/api/v1/auth.py` | `/auth/mock/login`, `/mock/callback`, `/logout`, `/me` 라우트 |
| `broker/app/services/user_upsert.py` | `(provider, external_id)` UNIQUE 기반 ON CONFLICT upsert |

## 3. 새 Provider 추가하는 법 (T04b 작업자 가이드)

### 3-1. 클래스 작성

`broker/app/providers/<your_name>.py`:

```python
from broker.app.core.auth import UserIdentity
from fastapi import Request

class YourProvider:
    name = "your_name"  # settings.auth_provider와 매칭되는 식별자

    async def initiate_login(self, request: Request) -> str:
        # 302 destination URL을 문자열로 반환. 응답 객체는 라우터 책임.
        return "https://idp.example/login?return=..."

    async def verify_callback(self, request: Request) -> UserIdentity:
        # 콜백 요청을 검증해 UserIdentity 반환. 실패는 ValueError raise.
        ...

    async def fetch_user_identity(self, token: str) -> UserIdentity:
        # bearer 토큰 흐름이 없으면 NotImplementedError raise.
        raise NotImplementedError
```

### 3-2. 팩토리에 등록

`broker/app/providers/__init__.py`의 `_build_provider`에 분기 추가:

```python
if name == "your_name":
    return YourProvider()
```

### 3-3. Settings에 값 허용

`broker/app/core/config.py`의 `auth_provider` Literal에 식별자 추가.

### 3-4. 콜백 라우트

`broker/app/api/v1/auth.py`에 prefix별 라우트 추가:

- `GET /auth/<your_name>/login` — `request`에서 `provider.initiate_login()` 호출 후 302
- `GET /auth/<your_name>/callback` — `provider.verify_callback()` → `upsert_user` → `issue_session` → audit `login_success` → `Set-Cookie` + 302
- `POST /auth/<your_name>/logout?logout=1` — IdP가 보내는 SLO 트리거. `revoke_all_sessions_for_user(user_id)` + audit `slo_triggered`

### 3-5. 운영 가드

`broker/app/main.py::_enforce_production_guards`는 다음을 강제:

- `APP_ENV=production` + `AUTH_PROVIDER=mock` → 부팅 거부
- `SESSION_SECRET in ("change-me","dev-secret","")` → 부팅 거부
- `SESSION_COOKIE_SECURE=false` → 부팅 거부

새 Provider는 별도 가드 추가가 필요한 경우(예: 사이드카 healthcheck)에만 함수 본문을 확장한다.

## 4. 세션 토큰 메커니즘

- **쿠키 raw** (`broker_session`): `secrets.token_urlsafe(32)` → 43자 URL-safe Base64
- **DB jti** (`tokens.jti`): `sha256(raw).hexdigest()` 64자. UNIQUE 인덱스 활용
- **만료**: `tokens.expires_at`. 기본 `SESSION_TTL_SECONDS=28800` (8시간)
- **검증 쿼리** (`verify_session`): `jti AND purpose='session' AND revoked_at IS NULL AND consumed_at IS NULL AND expires_at > now() AND users.is_active`
- **회수**: `tokens.revoked_at = now()` UPDATE. 즉시 차단.

`tokens` 테이블이 `host_id` NULL 허용으로 바뀐 이유 — 세션 토큰은 host와 무관. 마이그레이션 `0002_token_host_nullable`.

## 5. SLO (Single Logout) 백본

- **방향**: 포털→우리 단방향. 우리가 IdP의 글로벌 로그아웃 체인에 등록되어 IdP의 logout 트리거를 받는다. 우리 logout 버튼은 본인 세션만 끊는다.
- **백본 헬퍼**: `core/auth_session.revoke_all_sessions_for_user(session, user_id)` — 사용자의 모든 `purpose='session'` 행을 `revoked_at=now()`로 UPDATE.
- **audit action**: `slo_triggered`. T04b의 SLO 수신 엔드포인트가 호출.

## 6. Provider 식별자가 보장하는 것

- `users.provider` + `users.external_id` UNIQUE — Provider별 사용자 namespace 격리.
- `audit_logs.auth_provider` — 모든 인증 이벤트에 Provider 식별자 기록.
- structlog contextvars `auth_provider` — access log/구조 로그 자동 enrich.

## 7. 개발 로컬 e2e (cmd 기준)

```cmd
set APP_ENV=development
set AUTH_PROVIDER=mock
set SESSION_COOKIE_SECURE=false
uv run alembic upgrade head
uv run uvicorn broker.app.main:app --reload
```

다른 터미널에서:

```cmd
curl -i -X POST -H "Content-Type: application/json" ^
  -d "{\"external_id\":\"202012345\",\"display_name\":\"홍길동\"}" ^
  -c cookies.txt http://localhost:8000/api/v1/auth/mock/callback
curl -i -b cookies.txt http://localhost:8000/api/v1/auth/me
curl -i -X POST -b cookies.txt http://localhost:8000/api/v1/auth/logout
curl -i -b cookies.txt http://localhost:8000/api/v1/auth/me
```

브라우저: `http://localhost:8000/api/v1/auth/mock/login` 폼.

## 8. 보안 주의사항

1. 쿠키 raw 값은 절대 DB/로그에 남기지 않는다. jti = sha256(raw)만 저장.
2. `Set-Cookie`는 항상 `HttpOnly` + `SameSite=Lax`. production은 `Secure=true` 강제.
3. Mock 폼 라우트는 `app_env=='production'`에서 404 반환 (라우트 존재 노출 방지).
4. SLO 트리거 엔드포인트는 IdP에서 오는지 검증 — Provider 측 토큰/서명 확인 필요(T04b 책임).
5. SESSION_SECRET은 운영 시 32바이트 이상 랜덤 시크릿. `.env` 비커밋.
