# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

SmartClassroom은 충남대 강의실 PC 원격 접속 플랫폼의 Broker 백엔드다 (Sunshine 호스트 + Moonlight 클라이언트 + Broker 오케스트레이터). 제품 정의는 `PRD.md`, 실행 계획과 태스크별 상태는 `EXP.md`에 있으며 둘 다 작업 범위를 잡을 때의 근거다. 코드·커밋 메시지 곳곳에서 `T03`, `T04a`, `T05` 같은 태스크 ID를 인용하므로 논의 단위로 그대로 사용한다.

레포는 향후 모노레포로 확장 예정이다. 현재는 `broker/` 하나뿐이지만 `frontend/`, `agent/` (T11 호스트 에이전트), `client-patches/` (T13/T14 Moonlight fork)가 형제로 들어올 자리를 가정하고 구조가 짜여 있다. `broker/`가 루트라는 전제로 파일을 위로 끌어올리지 말 것.

## 자주 쓰는 명령어

패키지 매니저는 **uv** — Dockerfile과 CI가 이를 전제로 한다. 아래는 모두 `uv run …`으로 실행.

```bash
uv sync --extra dev                                   # 의존성 + dev 도구 설치

# 테스트 (testcontainers가 Postgres를 자동 기동 — Docker 데몬 실행 필수)
uv run pytest -v
uv run pytest broker/tests/test_reservation_crud.py   # 파일 단위
uv run pytest broker/tests/test_reservation_crud.py::test_create_reservation_happy_path  # 단일 테스트

# Lint / format / 타입
uv run ruff check .
uv run ruff format --check .
uv run mypy broker                                    # strict mode

# Alembic
uv run alembic upgrade head
uv run alembic check                                  # 모델/마이그레이션 drift 검증
uv run alembic revision --autogenerate -m "..."       # ⚠ EXCLUDE/JSONB default/GIN/GIST는 수동 보정 필요
uv run alembic downgrade -1

# 로컬 서버 (DB 없어도 기동 — /readyz만 503)
uv run uvicorn broker.app.main:app --reload

# 통합 스택 (컨테이너 진입 시 alembic upgrade 자동 실행)
docker compose up --build
docker compose up postgres -d                         # pytest용 Postgres만 띄울 때
```

## 셸 규칙

사용자에게 안내하는 셸 명령은 **Windows `cmd.exe` 문법**을 기본으로 한다 (`%VAR%`, `^` 줄바꿈, `nul` not `/dev/null`). PowerShell `$env:` 문법으로 답해서 여러 차례 수정을 받은 이력이 있다. Docker `exec` 내부에서는 bash 문법 OK.

`cmd.exe` 퍼센트 이스케이프 함정: `%%2B`는 `.bat` 파일에서만 동작한다. 대화형 cmd에서는 URL의 `+`를 **그냥 `%2B`** 로 적는다.

## 아키텍처 — 여러 파일을 봐야 보이는 큰 그림

### 레이어드 패키지 배치

```
broker/app/
  main.py            # create_app() + lifespan + 운영 가드
  core/              # 횡단 관심사: config, logging, errors, middleware, auth_session
  api/v1/            # FastAPI 라우터 (리소스 1파일)
  api/schemas/       # Pydantic v2 요청/응답 모델
  api/deps.py        # get_db / get_current_user / get_optional_user / require_admin
  domain/            # SQLAlchemy 2.0 ORM (테이블 1파일) + audit.write_audit() 헬퍼
  services/          # 비즈니스 로직 — 라우터가 호출, 서비스는 도메인 예외를 raise
  providers/         # AuthProvider 구현 (mock, cnu_sso)
  infra/db.py        # async engine, sessionmaker, Base — 전역 싱글톤
alembic/versions/    # 필요 시 raw SQL (EXCLUDE GIST, JSONB default)
broker/tests/        # pytest + pytest-asyncio + testcontainers + asgi-lifespan
```

### DB 제약이 비즈니스 룰

`reservations`에 `EXCLUDE USING GIST (host_id WITH =, time_range WITH &&) WHERE status IN ('CONFIRMED','COMPLETED')`가 걸려 있다 (`alembic/versions/0001_initial.py:147`). 시간 겹침은 **PostgreSQL이 잡는다** — 서비스는 `IntegrityError`를 catch해서 `orig.diag.constraint_name == "reservations_no_overlap"` 인지 확인한다 (`services/reservation.py`의 `RESERVATION_OVERLAP_CONSTRAINT` 상수). Python 측에서 별도 overlap 검사를 짜지 말 것 — 레이스 발생.

이 제약은 **user_id를 보지 않는다** — 동일 호스트·동일 슬롯은 사용자가 달라도 차단된다. 의도된 자원 격리.

`status='CANCELED'`는 predicate 밖이라 같은 슬롯 재예약이 가능하다 (soft delete + EXCLUDE 자동 우회). 그 외 의미로 `status`를 "감춤" 용도로 바꾸려 한다면 EXCLUDE 영향을 먼저 따져볼 것.

### 도메인 예외 → HTTP 핸들러 패턴

서비스는 순수 Python 예외를 raise한다. `core/errors.py`의 `ReservationConflictError` / `ReservationQuotaError` / `InvalidReservationWindowError` / `InvalidConnectWindowError`, `services/reservation.py`의 `NotOwnerError` / `ReservationNotFoundError` / `HostNotFoundError`. `register_error_handlers`가 앞쪽 4종을 409/429/422/422로 **전역 매핑**한다. `NotOwnerError` / `ReservationNotFoundError`는 라우터에서 **404로 변환**한다 — 존재 노출 방지가 목적이므로 403 금지.

새 도메인 예외 추가 시 같은 분리 원칙: 매핑이 보편적이면 전역 핸들러, 라우트별 의미라면 라우터에서 변환.

422 핸들러는 `exc.errors()`에 `jsonable_encoder`를 한 번 건다 — Pydantic v2가 `ctx`에 raw `datetime`/`bytes`를 박아 두는데 orjson이 못 직렬화한다. 이 정규화를 제거하지 말 것.

### 미들웨어 순서는 LIFO이며 테스트가 보장

`main.create_app()`이 등록하는 순서 — **나중에 add한 게 요청 시 먼저** 동작한다:

1. `CORSMiddleware` (가장 안쪽)
2. `AccessLogMiddleware`
3. `AuthSessionMiddleware`
4. `RequestIdMiddleware` (가장 바깥)

요청 흐름: `RequestId → AuthSession → AccessLog → CORS → 라우터`. `AuthSessionMiddleware`가 `user_id`/`auth_provider`를 structlog contextvars에 바인딩한 **뒤** `AccessLogMiddleware`가 그 값을 읽는다. 순서를 바꾸면 access log 보강이 깨진다.

`audit.write_audit()`도 호출자가 `request_id`를 명시하지 않으면 같은 contextvars에서 픽업 — 같은 결합.

### `tokens` 테이블은 다중 purpose의 서버사이드 opaque

raw 토큰은 `secrets.token_urlsafe(32)` 로 만들고 **응답에만** 노출, DB에는 `sha256(raw)` 64자 hex만 `jti` 컬럼에 저장한다. JWT 아님 — 서버가 항상 진실. `purpose` 컬럼으로 종류 구분:

| purpose | 발급자 | host_id | reservation_id | expires_at | consumed_at | 회수 헬퍼 |
| --- | --- | --- | --- | --- | --- | --- |
| `session` | `core/auth_session.py` | NULL | NULL | now + session_ttl | 미사용 | `revoke_all_sessions_for_user()` |
| `connect` | `services/token_service.py` (T07) | 예약 호스트 | 예약 id | `reservation.ends_at` | 1회 소비 | `revoke_active_tokens_for_reservation()` |

함의:
- DB 덤프로 활성 토큰 재현 불가 (raw가 어디에도 없다).
- `tokens.host_id`는 nullable (`0002_token_host_nullable`) — session 때문. connect는 항상 채움.
- `ix_tokens_active_expires` 부분 인덱스(`consumed_at IS NULL AND revoked_at IS NULL`)가 활성 토큰 조회의 인덱스 — 새 purpose도 이 predicate를 따른다.
- 새 purpose 추가 시 위 표 한 줄 + `CONNECT_PURPOSE` 같은 모듈 상수 + 회수 헬퍼 격리. 라우터에서 토큰 lifecycle 직접 만지지 말 것.

### 1회 소비 / 동시성은 DB UPDATE의 predicate로

`token_service.mark_consumed()`는 `UPDATE tokens SET consumed_at=now WHERE id=:id AND consumed_at IS NULL AND revoked_at IS NULL` 의 `rowcount==1` 만 "이번 호출이 소비" 로 인정한다. Python 측 `if token.consumed_at is None: token.consumed_at = now`는 **레이스가 난다** — 금지. 같은 철학이 `reservations`의 EXCLUDE GIST(서비스가 IntegrityError 잡음)에 이미 있다.

새로운 멱등/race-safe 동작이 필요하면 같은 패턴: predicate UPDATE → rowcount 검사 → audit. ORM `flush()` 후 객체 비교로 분기하지 말 것.

### 내부 호출 API는 require_admin 임시 가드 (T08까지)

T07 `POST /tokens/verify`처럼 **외부 사용자가 아닌 내부 컴포넌트**(T08 자동 페어링, T10 Sunshine fork 등)가 호출하는 엔드포인트는 현재 `Depends(require_admin)` 로 임시 보호하고 라우터 docstring에 `TODO(T08): internal auth 교체 (§11 A6)` 마커를 붙인다. T08에서 X-Internal-Token / mTLS 로 일괄 교체할 때 이 마커로 찾는다. 새 내부 API도 같은 마커 + 같은 임시 가드 패턴.

검증 응답 정책: **200 + `valid: bool`** 모델 — `HTTPException` 으로 4xx/5xx 분기하지 않는다. 호출자(T10 Sunshine fork 등)가 단순 JSON 파싱 + `valid` 플래그로 분기할 수 있게 하기 위함. 4xx는 admin/internal-auth 자체 실패에만.

### 운영 가드는 lifespan에서

`main._enforce_production_guards()`가 `APP_ENV=production` 일 때 (`AUTH_PROVIDER=mock` OR `SESSION_SECRET`이 알려진 placeholder OR `SESSION_COOKIE_SECURE=false`)면 부팅을 거부한다. 세 가지 모두 테스트가 회귀 확인한다. 비프로덕션 환경을 통과시키려고 가드를 느슨하게 만들지 말고 env를 고칠 것.

### Async SQLAlchemy 불변식

- `expire_on_commit=False`가 `infra/db.py`에 강제. 세션별로 override 금지.
- Lazy loading은 `MissingGreenlet` — `selectinload`/`joinedload`만 사용.
- 모든 datetime 컬럼은 `TIMESTAMPTZ`, 모든 Python datetime은 `datetime.now(UTC)` 또는 tz-aware. naive 한 번 섞이면 EXCLUDE 비교가 조용히 깨진다.
- `TSTZRANGE`는 ORM `add()` 매핑이 어색하다 — `reservation_service.create_reservation`이 raw `INSERT ... RETURNING id`를 쓰는 이유. 다른 range 컬럼을 추가할 때도 같은 패턴, ORM과 싸우지 말 것.
- `asyncpg.Range`의 lower/upper가 naive로 돌아올 수 있다 — `reservation_bounds()`가 UTC 보정한다. 이 헬퍼를 통해 접근.

### Commit은 라우터, service는 안 한다

`services/*` 와 `auth_session.*` 는 `db.add()` / `db.execute()` / `db.flush()`만 쓴다. 라우터(또는 `auth.py` 콜백)가 `db.commit()` 한다. 멀티스텝 작업(세션 발급 + audit 기록 등)의 원자성 유지가 목적. 서비스 함수 안에 commit을 흩어 두지 말 것.

### 정책 상수는 env 기반 (정책 테이블 없음)

`core/config.py`의 `Settings`가 정책 자체다. 변경 = 재배포/재시작.

- 예약: `reservation_*` 5종 (slot_minutes, max_concurrent, max_hours_per_day, max_duration_minutes, lookahead_days).
- 토큰: `connect_token_grace_seconds` (T07 — `starts_at - grace ~ ends_at` 발급 게이트).

정책 테이블이 필요해지면 별도 태스크로 의식적으로 도입, 지나가다 만들지 말 것. 새 env 추가 시 `tests/conftest.py::_set_test_env` 에 testcontainer 기본값을 같이 넣을 것 (테스트가 `Settings(...)` 로 우회하지 못하도록).

### Auth provider는 Protocol + factory

`core/auth.AuthProvider`가 계약, `providers/__init__.get_active_provider(settings)`가 `settings.auth_provider` 기반 `lru_cache` 팩토리. provider 추가 절차: `providers/` 하위에 Protocol 구현 → `_build_provider`에 이름 등록 → `Settings.auth_provider`의 `Literal`에 값 추가 → `api/v1/auth.py`에 라우트 추가. 라우터에서 구체 provider를 직접 import하지 말 것.

### 테스트는 testcontainers에 의존

`tests/conftest.py::pg_url`(session-scoped)이 실제 Postgres 16을 Docker로 띄우고 `alembic upgrade head`를 적용한다. `client` fixture가 그 DB URL로 앱을 재생성하고 `get_settings` 캐시를 비운다. 새로운 `Settings` env를 추가하면 `client` fixture 호출 전에 `os.environ`으로 주입할 것 — `Settings(...)` kwargs로 우회하지 말고 `_set_test_env` 패턴을 따른다.

인증된 client는 `auth_client(role="user"|"admin")` fixture를 사용. 테스트에서 세션 쿠키를 손으로 만들지 말 것.

### 마이그레이션 — autogenerate의 사각지대

`alembic check`가 CI에 포함되어 있지만, autogenerate는 `EXCLUDE` 제약 / JSONB `server_default` / 부분 인덱스 / GIN·GIST 인덱스를 못 본다. 모델과 마이그레이션이 이쪽에서 어긋나면 autogenerate가 못 잡는 drift가 되므로 마이그레이션을 직접 손으로 보정한다.

## 헷갈릴 때 참조

- `PRD.md` — 제품이 무엇이고 무엇이 아닌지.
- `EXP.md` — 어떤 작업이 어떤 순서·의존성으로 계획되어 있는지. 크리티컬 패스는 `§0`. 태스크를 마칠 때 여기에 상태를 갱신한다.
- `README.md` — Quickstart, 관측성 카탈로그 (메트릭 이름, 헤더, 환경 변수).
