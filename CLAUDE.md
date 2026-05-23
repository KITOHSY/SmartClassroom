# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

SmartClassroom은 충남대 강의실 PC 원격 접속 플랫폼의 Broker 백엔드다 (Sunshine 호스트 + Moonlight 클라이언트 + Broker 오케스트레이터). 제품 정의는 `PRD.md`, 실행 계획과 태스크별 상태는 `EXP.md`에 있으며 둘 다 작업 범위를 잡을 때의 근거다. 코드·커밋 메시지 곳곳에서 `T03`, `T04a`, `T05` 같은 태스크 ID를 인용하므로 논의 단위로 그대로 사용한다.

레포는 모노레포다. `broker/` (FastAPI 백엔드) + `frontend/` (T16 React+Vite+TS 프런트엔드) + `agent/` (T11 호스트 에이전트 사이드카, Python+uv) + `host-patches/sunshine/` (T10 — Sunshine 호스트 포크 패치 시리즈, 아래 "Sunshine 호스트 포크" 절 참조). 향후 `client-patches/` (T13/T14 Moonlight fork)가 형제로 합류한다. `broker/` / `frontend/` / `agent/` 가 각자 루트라는 전제로 파일을 위로 끌어올리지 말 것.

## 자주 쓰는 명령어

백엔드 패키지 매니저는 **uv**, 프런트는 **pnpm 9 / Node 20**. Dockerfile·CI가 이를 전제로 한다.

```bash
# 백엔드 — 모두 uv run …
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

```cmd
:: 프런트 (T16) — frontend/ 안에서 실행
cd frontend
pnpm install
pnpm dev          :: Vite 5173 + /api 프록시 → localhost:8000
pnpm test         :: Vitest + RTL + MSW (script가 이미 `vitest run` — `--run` 붙이면 unknown option)
pnpm lint
pnpm typecheck    :: tsc strict, exactOptionalPropertyTypes
pnpm build        :: tsc --noEmit + vite build
```

```cmd
:: 에이전트 (T11) — agent/ 안에서 실행 (자체 venv)
cd agent
uv sync --extra dev
uv run pytest -v
uv run ruff check .
uv run mypy smartclassroom_agent
uv run python -m smartclassroom_agent doctor --config agent.yaml    :: 1회 heartbeat 점검
uv run python -m smartclassroom_agent run --config agent.yaml       :: 30s 주기 loop
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
  api/deps.py        # get_db / get_current_user / get_optional_user / require_admin / require_internal_token
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

### 즉시 사용 예약은 `_validate_window`만 우회 (T17)

`create_instant_reservation` (`services/reservation.py`)은 `create_reservation`과 같은 raw `INSERT ... tstzrange(:s, :e, '[)') RETURNING id` 패턴이지만 **`_validate_window`(30분 그리드 / 과거 시각 / lookahead)를 호출하지 않는다** — 윈도우를 서버가 산정하므로 그리드 검증이 무의미. 단 **`_validate_quota`(동시 5건 / 일 8시간)는 그대로 호출**한다. 우회 대상은 그리드 제약 하나뿐 — reservation 검증 로직을 "통합" 리팩터링할 때 즉시 사용 경로에 그리드 검사를 다시 끼우지 말 것.

`_instant_window(now, next_reservation_at)`: `starts_at=now`(초 절삭, 비그리드), `ends_at = floor_30min(now + INSTANT_USE_DURATION) + 30min`을 그 호스트의 다음 CONFIRMED 예약 시작(`_next_reservation_start`, raw SQL `min(lower(time_range))`)으로 cap. 반열림 `[)`이라 `ends_at == next_start` 경계는 EXCLUDE가 겹침으로 안 본다. IDLE 아닌 호스트는 도메인 예외 `HostNotAvailableError` → 라우터가 409 `host_not_available` dict-detail로 변환.

`POST /reservations/instant`는 예약 생성 + connect 토큰 발급 + audit을 **한 응답**(`ConnectTokenResponse`)으로 반환 — 진짜 원클릭(1 API 콜). 토큰 발급+audit 조립 블록은 `connect_token_endpoint`와 공용 헬퍼(`_issue_connect_token_response`)로 공유하므로 한쪽만 고치지 말 것.

### 도메인 예외 → HTTP 핸들러 패턴

서비스는 순수 Python 예외를 raise한다. `core/errors.py`의 `ReservationConflictError` / `ReservationQuotaError` / `InvalidReservationWindowError` / `InvalidConnectWindowError`, `services/reservation.py`의 `NotOwnerError` / `ReservationNotFoundError` / `HostNotFoundError`. `register_error_handlers`가 앞쪽 4종을 409/429/422/422로 **전역 매핑**한다. `NotOwnerError` / `ReservationNotFoundError`는 라우터에서 **404로 변환**한다 — 존재 노출 방지가 목적이므로 403 금지.

새 도메인 예외 추가 시 같은 분리 원칙: 매핑이 보편적이면 전역 핸들러, 라우트별 의미라면 라우터에서 변환.

라우트별 1회성 4xx에는 `raise HTTPException(status_code=..., detail={"error": "snake_code", "message": "..."})` 형태를 쓴다 — `_http_exc` 핸들러(`core/errors.py:64`)가 dict detail을 받으면 `error`/`message`를 ErrorResponse 최상위로 끌어올리고 나머지 키는 `detail`로 보존한다. T11 `get_agent_host`의 `missing_bearer`/`invalid_agent_token`/`host_missing`이 이 패턴 — 도메인 예외 클래스를 새로 만들 가치는 없지만 응답 코드는 라우트가 의도한 snake_case로 내고 싶을 때. 문자열 detail은 기존 동작 그대로 (`"http_error"` 코드).

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
| `agent` | `services/agent_token_service.py` (T11) | 해당 호스트 | NULL | now + agent_token_ttl_days | 미사용 (다회) | `revoke_active_agent_tokens(host_id)` |

함의:
- DB 덤프로 활성 토큰 재현 불가 (raw가 어디에도 없다).
- `tokens.host_id`는 nullable (`0002_token_host_nullable`) — session 때문. connect는 항상 채움.
- `ix_tokens_active_expires` 부분 인덱스(`consumed_at IS NULL AND revoked_at IS NULL`)가 활성 토큰 조회의 인덱스 — 새 purpose도 이 predicate를 따른다.
- 새 purpose 추가 시 위 표 한 줄 + `CONNECT_PURPOSE` 같은 모듈 상수 + 회수 헬퍼 격리. 라우터에서 토큰 lifecycle 직접 만지지 말 것.

### 1회 소비 / 동시성은 DB UPDATE의 predicate로

`token_service.mark_consumed()`는 `UPDATE tokens SET consumed_at=now WHERE id=:id AND consumed_at IS NULL AND revoked_at IS NULL` 의 `rowcount==1` 만 "이번 호출이 소비" 로 인정한다. Python 측 `if token.consumed_at is None: token.consumed_at = now`는 **레이스가 난다** — 금지. 같은 철학이 `reservations`의 EXCLUDE GIST(서비스가 IntegrityError 잡음)에 이미 있다.

새로운 멱등/race-safe 동작이 필요하면 같은 패턴: predicate UPDATE → rowcount 검사 → audit. ORM `flush()` 후 객체 비교로 분기하지 말 것.

### 내부 호출 API는 X-Internal-Token (T08, §11 A6)

`POST /tokens/verify`처럼 **외부 사용자가 아닌 내부 컴포넌트**(T08 자동 페어링, T10 Sunshine fork 등)가 호출하는 엔드포인트는 `Depends(require_internal_token)`(`api/deps.py`)로 보호한다 — `X-Internal-Token` 헤더를 `Settings.internal_api_token`과 상수시간 비교, 불일치 시 401 dict-detail. 사용자 세션쿠키·admin·에이전트 Bearer와 별개인 **4번째 인증 채널**. production은 `internal_api_token` 미설정/placeholder 시 부팅 거부(`_enforce_production_guards`). 새 내부 API도 같은 의존성. (T07~T08 이전엔 `require_admin` 임시 가드 + `TODO(T08)` 마커였고 T08에서 일괄 교체했다.)

검증 응답 정책: **200 + `valid: bool`** 모델 — `HTTPException` 으로 4xx/5xx 분기하지 않는다. 호출자(T10 Sunshine fork 등)가 단순 JSON 파싱 + `valid` 플래그로 분기할 수 있게 하기 위함. 4xx는 internal-auth 자체 실패에만.

### 자동 페어링 — Broker가 PIN을 중계 (T08)

Moonlight↔Sunshine 페어링의 4자리 PIN을 사람이 입력하지 않도록 Broker가 중계한다. 여러 파일을 봐야 보이는 불변식:

- **PIN은 클라이언트(Moonlight)가 생성** — 프로토콜상 호스트가 아니라 클라이언트가 PIN을 만든다. 따라서 흐름은 `client→broker→Sunshine`: 클라이언트가 PIN 생성 + 페어링 핸드셰이크를 **먼저** 시작 → `POST /api/v1/pairing`에 `{token, pin}` 전달 → `services/pairing_service.py::push_pin`이 Sunshine `/api/pin`으로 중계. 클라이언트가 먼저 시작하므로 Sunshine 페어링 세션이 이미 존재 — 지수 백오프는 짧은 레이스·일시 오류용 보험이지 본 메커니즘이 아니다.
- **`/pairing` 인증 = connect 토큰 자체** — `verify_connect_token`으로 검증만 하고 **소비(consume)는 안 한다**(소비는 스트림 시작 시점). Moonlight는 세션 쿠키가 없으므로 토큰이 곧 인증. `/tokens/verify`(내부 인증 X-Internal-Token)와 다른 채널 — `/pairing`은 사용자 connect-token 채널이다. 섞지 말 것.
- **Sunshine confighttp 포트는 47990** — `hosts.sunshine_port`(스트리밍, 기본 47984)와 **별개**. `Settings.sunshine_config_port`. 자가서명 HTTPS라 `verify=Settings.sunshine_tls_verify`(기본 False — 캠퍼스 LAN 전제, cert pinning은 후속 강화).
- **`hosts.sunshine_broker_token`** — Sunshine `sunshine.conf`의 `broker_api_token`과 짝인 per-host Bearer 토큰. Broker가 raw로 제시해야 하므로 해시 불가 — **평문 컬럼**. 응답 스키마·로그·audit `detail` 어디에도 미노출. admin이 `POST /hosts`(생성 시) 또는 `PUT /hosts/{id}/sunshine-token`(기존 호스트)으로 등록.
- **실패는 `fallback: manual_pin` 신호** — `pairing_service`의 도메인 예외(`HostNotPairableError`/`PairingUnreachableError`/`PairingRejectedError`)를 라우터가 422/502/409 dict-detail로 매핑, 전부 `fallback: manual_pin` 키 포함(T19 수동 PIN 폴백 신호). audit는 결과 1행(`pairing_succeeded`/`pairing_failed`)만 — 재시도마다 남기지 않는다.
- **Broker 우회 경계** — T08은 *새 페어링*을 Broker 독점 경로로 만든다(PIN 주입 크리덴셜을 학생이 못 가짐). 단 강의실 PC Sunshine 웹UI 비번이 비밀·비기본값이어야 성립(T20 배포 요건). *기존 페어링* 재사용 차단은 세션 종료 시 인증서 un-pair = T09/T12. T14(Moonlight 자동화)·Sunshine→Broker `/tokens/verify` 콜백은 T08 범위 밖.
- **페어링된 호스트 = connect 토큰 검증 우회** — connect 토큰의 역할은 **페어링 단계의 Broker 호출 인증** 단 하나. 페어링 핸드셰이크가 끝나면 클라이언트 인증서(mTLS)가 trust anchor가 되어 Moonlight가 Sunshine에 직접 stream — T14 `scEvaluateAutoConnect`도 paired면 `ScBrokerClient`를 아예 호출 안 한다. 즉 **한 번 페어링된 클라이언트는 그 호스트로 토큰 없이도/잘못된 broker URL로도 계속 접속 가능**. e2e(2026-05-24) 시나리오 ③에서 broker=`http://localhost:9999`로 호출했지만 페어링됨 호스트라 broker 무시하고 즉시 스트림 진입한 사실로 확인. T09/T12(세션 종료 시 un-pair)가 빠지면 학생이 한 번 예약하고 페어링 받으면 이후 임의 시점에 재접속 가능 — KPI상으론 무관하나 자원 격리·감사 측면에서 T09/T12가 운영 출시 전 필수.

### 운영 가드는 lifespan에서

`main._enforce_production_guards()`가 `APP_ENV=production` 일 때 (`AUTH_PROVIDER=mock` OR `SESSION_SECRET`이 알려진 placeholder OR `SESSION_COOKIE_SECURE=false`)면 부팅을 거부한다. 세 가지 모두 테스트가 회귀 확인한다. 비프로덕션 환경을 통과시키려고 가드를 느슨하게 만들지 말고 env를 고칠 것.

### Async SQLAlchemy 불변식

- `expire_on_commit=False`가 `infra/db.py`에 강제. 세션별로 override 금지.
- Lazy loading은 `MissingGreenlet` — `selectinload`/`joinedload`만 사용.
- 모든 datetime 컬럼은 `TIMESTAMPTZ`, 모든 Python datetime은 `datetime.now(UTC)` 또는 tz-aware. naive 한 번 섞이면 EXCLUDE 비교가 조용히 깨진다.
- `TSTZRANGE`는 ORM `add()` 매핑이 어색하다 — `reservation_service.create_reservation`이 raw `INSERT ... RETURNING id`를 쓰는 이유. 다른 range 컬럼을 추가할 때도 같은 패턴, ORM과 싸우지 말 것.
- `asyncpg.Range`의 lower/upper가 naive로 돌아올 수 있다 — `reservation_bounds()`가 UTC 보정한다. 이 헬퍼를 통해 접근.
- SQLAlchemy `text()`의 bind parameter는 **`:name::type` 캐스트 문법과 충돌** — `:` 두 개를 두 번째 파라미터 시작으로 파싱해 `IndexError`/`InvalidRequestError`. range/타입 캐스트가 필요하면 PostgreSQL operator·함수가 추론하게 두기 (`get_active_reservation_for_host`의 `text("time_range @> :at_time")` — `at_time` 단독, `::timestamptz` 없이 `@>` 좌변에서 timestamptz 추론). 굳이 명시 캐스트가 필요하면 `tstzrange(:from_, :to_, '[)')`처럼 함수 호출로 감쌀 것.
- `hosts` 테이블의 ORM 속성은 `host_metadata`이지만 **DB 컬럼명은 `metadata`** — `Base.metadata` (SQLAlchemy 예약어) 충돌 회피로 `mapped_column("metadata", JSONB, ...)` 매핑(`domain/host.py:24`). raw SQL/psql/마이그레이션은 `metadata`, ORM 속성 접근은 `host.host_metadata`. 비슷하게 다른 테이블에서 SQLAlchemy 예약어와 겹치면 같은 분리 패턴.
- JSONB 컬럼 변경은 **새 dict 할당으로 트리거** — `host.host_metadata["k"] = v` (in-place) 는 SQLAlchemy가 변경을 감지 못 해 commit이 noop. `metadata = dict(host.host_metadata or {}); metadata["k"] = v; host.host_metadata = metadata` 패턴 (`api/v1/agents.py:36-45`).

### Commit은 라우터, service는 안 한다

`services/*` 와 `auth_session.*` 는 `db.add()` / `db.execute()` / `db.flush()`만 쓴다. 라우터(또는 `auth.py` 콜백)가 `db.commit()` 한다. 멀티스텝 작업(세션 발급 + audit 기록 등)의 원자성 유지가 목적. 서비스 함수 안에 commit을 흩어 두지 말 것.

### 정책 상수는 env 기반 (정책 테이블 없음)

`core/config.py`의 `Settings`가 정책 자체다. 변경 = 재배포/재시작.

- 예약: `reservation_*` 5종 (slot_minutes, max_concurrent, max_hours_per_day, max_duration_minutes, lookahead_days).
- 토큰: `connect_token_grace_seconds` (T07 — `starts_at - grace ~ ends_at` 발급 게이트), `agent_token_ttl_days` (T11 — 기본 3650일, 다회 사용 long-lived).
- 호스트 상태(T06): `host_offline_after_seconds` / `host_status_monitor_interval_seconds` / `host_degraded_cpu_pct` / `host_degraded_mem_pct`. **`host_offline_after_seconds`는 agent의 `interval_seconds`보다 반드시 커야** (권장 ≥ 1.5×). 작거나 같으면 monitor가 IDLE↔OFFLINE flapping — heartbeat가 도착하기 전에 stale 판정. agent 기본 30s → 최소 45s. 테스트 conftest는 `HOST_OFFLINE_AFTER_SECONDS=10` + `HOST_STATUS_MONITOR_INTERVAL_SECONDS=2`로 빠른 검증을 위해 의도적으로 작게 — production .env에서 동일 값 쓰지 말 것.

정책 테이블이 필요해지면 별도 태스크로 의식적으로 도입, 지나가다 만들지 말 것. 새 env 추가 시 `tests/conftest.py::_set_test_env` 에 testcontainer 기본값을 같이 넣을 것 (테스트가 `Settings(...)` 로 우회하지 못하도록).

### Auth provider는 Protocol + factory

`core/auth.AuthProvider`가 계약, `providers/__init__.get_active_provider(settings)`가 `settings.auth_provider` 기반 `lru_cache` 팩토리. provider 추가 절차: `providers/` 하위에 Protocol 구현 → `_build_provider`에 이름 등록 → `Settings.auth_provider`의 `Literal`에 값 추가 → `api/v1/auth.py`에 라우트 추가. 라우터에서 구체 provider를 직접 import하지 말 것.

### Agent ↔ Backend 계약 (T11 + T06)

`agent/` (Python 사이드카)와 broker 라우터가 결합되는 invariant — 한 쪽만 보면 안 보인다:

- **Agent 인증은 별도 Bearer 채널** — 세션 쿠키/admin 의존성과 다른 경로. `Authorization: Bearer <agent_token>` → `get_agent_host` 의존성(`api/deps.py:57`)이 `(Host, Token)` 튜플을 주입한다. 새 agent-facing 라우트도 `Depends(get_agent_host)` 만 — `get_current_user`/`require_admin` 섞지 말 것.
- **raw agent_token은 enrollment + rotation에서만 1회 노출** — `POST /hosts` (admin 등록) 응답과 `POST /hosts/{id}/agent-token` (회전) 응답에만 raw 값 포함. DB에는 `sha256(raw)` 만 저장 — connect token과 동일 규칙. 분실하면 회전이 유일한 복구 경로.
- **Heartbeat 라우트는 UPDATE-only + status 전이 평가** — `POST /agents/heartbeat` (`api/v1/agents.py`)는 `hosts.last_heartbeat_at` + `host_metadata` JSONB 갱신 + T06 status 전이(`evaluate_host_status` → `transition_host`)를 한 트랜잭션에서 수행. audit_logs는 status 변화 시에만 1행(`host_status_change`) — 30s 주기 폭증 회피. 다른 고빈도 ingest도 같은 원칙: audit는 상태 전이/보안 이벤트에만.
- **상태 머신 전이는 세 경로** — ① heartbeat 라우터가 즉시 IDLE/IN_USE/DEGRADED 평가 (방금 받은 메트릭 기반), ② `host_status_monitor` background task(`services/host_status_monitor.py`, lifespan에서 60s tick)가 stale heartbeat → OFFLINE, ③ 예약 라우터가 사용자 액션 직후 `transition_host`로 IN_USE/IDLE을 즉시 반영 — `POST /reservations/instant`는 IN_USE, `DELETE /reservations/{id}`는 취소 후 그 호스트에 활성 예약이 없으면 IDLE (상태 배지 즉답용; 다음 heartbeat가 재확인·보정, T21). **OFFLINE 전이는 여전히 monitor의 단독 책임** — 라우터가 OFFLINE을 직접 set하지 말 것. ③도 IDLE/IN_USE만 건드린다 — DEGRADED/OFFLINE은 메트릭·heartbeat 주도라 예약 라우터가 손대지 않는다.
- **상태 전이 평가는 순수 함수** — `evaluate_host_status` (`services/host_status.py`)는 DB I/O 없이 메트릭만 받아 다음 status를 반환. 새 룰 추가는 이 함수 + 단위 테스트(`test_host_status_evaluator.py`)로. `transition_host` 헬퍼만 audit + SSE publish 부수효과를 갖는다.
- **SSE 채널은 단일 broker 인스턴스 가정** — `HostEventBroker` (`services/host_events.py`)는 in-process asyncio.Queue per subscriber. `app.state.host_event_broker`로 lifespan에 묶이며, `get_host_event_broker` 의존성으로만 접근. 멀티 broker 인스턴스 스케일아웃 시 Redis pubsub 등 외부 broker 도입 필요 (§11 A10).
- **`HOST_*` Prometheus gauge는 hostname 라벨 단일** — `core/metrics.py`의 `HOST_CPU_PERCENT` / `HOST_MEM_PERCENT` / `HOST_GPU_PERCENT` / `HOST_STATUS_INFO`. host_id 동시 라벨링은 high-cardinality 회피로 금지. 1m/5m 평균은 PromQL `avg_over_time(...[1m])`이 담당 — broker DB는 latest만(`host_metadata.metrics`). OFFLINE 전이 시 `clear_host_metrics(hostname)`이 cpu/mem/gpu 라벨을 삭제(`status_info`만 유지) — 죽은 호스트가 마지막 부하값으로 alert 일으키는 것 방지.
- **`ENABLE_METRICS`는 `Settings`에 없다 — `prometheus-fastapi-instrumentator`가 `os.environ`을 직접 검사** — `core/metrics.py:setup_metrics`의 `should_respect_env_var=True`. pydantic-settings는 `.env`를 Settings 필드로만 로드하지 process env에 propagate 하지 않으므로, host에서 `uv run uvicorn` 직접 기동할 땐 cmd `set ENABLE_METRICS=true` (또는 셸 export)를 별도로 거쳐야 `/metrics` 노출. docker compose는 `environment:` 항목이 process env로 들어가 자동 충족. 새로 같은 라이브러리 옵션을 더 활성화할 때도 같은 채널 — `.env`만 믿지 말 것.

### Frontend ↔ Backend 계약 (T16)

`frontend/` (React+Vite+TS)와 broker 라우터가 결합되는 invariant — 어느 한 쪽만 봐서는 안 보이고, 둘 다 같이 고쳐야 한다:

- **`GET /api/v1/auth/me` 응답에 내부 PK `id`** (`api/v1/auth.py::me`) — 프런트가 admin "내 예약" 화면에서 `?user_id=me.id`로 본인 예약만 필터하기 위함 (`frontend/src/pages/MyReservationsPage.tsx`). 빠지면 admin이 전체 사용자의 예약을 보는 노출 버그 (2026-05-12 e2e 발견). 회귀 assert는 `broker/tests/test_auth_mock_flow.py`. 내부 PK 노출이지만 본인 ID 한정이라 보안 영향 미미.
- **캘린더 시간 범위는 반열림 `[from, to)` + 30분 그리드** — 백엔드 `_ensure_grid` (`services/reservation.py`)는 `:00`/`:30`만 허용해 `23:59:59`는 422. 프런트 `kstEndOfDay` (`frontend/src/lib/time.ts`)가 다음날 00:00 KST를 반환해 같은 날 마지막 23:30 슬롯을 포함하면서 422를 회피한다. 새 range 입력을 추가할 때도 시계열 helper에서 그리드 정렬을 보장하고 라우트가 `_ensure_grid`로 한 번 더 방어하는 이중 패턴을 유지할 것.
- **`moonlight://connect?token=&host-id=&host=&port=&broker=` URL 스키마는 T13/T14 fork와의 선계약** — `frontend/src/lib/moonlight.ts::buildMoonlightUrl`이 조립하고, moonlight-qt fork의 커스텀 URL 핸들러 `--connect-token`/`--host-id`/`--broker` 인자에 대응한다. 이 스키마가 프런트↔클라이언트의 유일한 계약 — 파라미터 키를 바꾸면 양쪽을 같이 고쳐야 한다. `broker`(T14 추가)는 Moonlight가 페어링 PIN을 POST할 Broker base URL로, `window.location.origin`을 넣는다(학생 브라우저·Moonlight가 같은 PC라 same-origin; 배포가 프런트/API origin을 분리하면 `buildMoonlightUrl` 한 곳만 고치면 된다). `launchMoonlight`의 핸들러 등록 여부 판정은 `visibilitychange`/`blur` + 1.8s 타이머 **휴리스틱**(브라우저에 동기 확인 API 부재) — `false`라도 실제로는 실행됐을 수 있다.
- **`GET /hosts/available`은 파라미터 유무로 듀얼 모드** — `from`/`to` 쿼리가 있으면 슬롯 가용 필터(원래 동작), 없으면 T17 바로 접속 모드(`list_instant_available_hosts` — `status='IDLE'`이고 now를 덮는 활성 예약이 없는 호스트 + 호스트별 `available_until`). 한 라우트가 분기하므로 새 쿼리 파라미터를 더할 때 두 모드 모두 영향을 따질 것.
- **예약 불가 호스트 차단은 프런트 게이트 전용 (T21)** — DEGRADED/OFFLINE 또는 `ip_address` 미등록 호스트의 정규 예약 차단은 `CalendarGrid`의 `hostBlockedReason()` 헬퍼에서만 한다. `create_reservation`(정규 예약)에는 호스트 상태 검증을 **일부러 넣지 않았다**: ⓐ 테스트 `host` 픽스처가 호스트를 `OFFLINE`로 시드(`conftest.py`)해 정규 예약 테스트 9+개가 깨지고, ⓑ 미래 슬롯을 *현재* 호스트 상태로 막으면 일시적으로 오프라인인 PC의 사전 예약이 불가능해진다. 캘린더가 유일한 예약 진입점이라 프런트 게이트로 충분. 반면 `create_instant_reservation`은 "지금 사용"이라 백엔드 `status=='IDLE'` 가드(`HostNotAvailableError`)를 유지 — 정규 예약과 성격이 다르다. 정규 예약에 백엔드 호스트 상태 가드를 "일관성" 명목으로 추가하지 말 것.

### 테스트는 testcontainers에 의존

`tests/conftest.py::pg_url`(session-scoped)이 실제 Postgres 16을 Docker로 띄우고 `alembic upgrade head`를 적용한다. `client` fixture가 그 DB URL로 앱을 재생성하고 `get_settings` 캐시를 비운다. 새로운 `Settings` env를 추가하면 `client` fixture 호출 전에 `os.environ`으로 주입할 것 — `Settings(...)` kwargs로 우회하지 말고 `_set_test_env` 패턴을 따른다.

인증된 client는 `auth_client(role="user"|"admin")` fixture를 사용. 테스트에서 세션 쿠키를 손으로 만들지 말 것.

T05 `starts_at >= now` 정책 때문에 **NOW를 덮는 활성 예약은 service/API로 못 만든다** — T06 IN_USE 평가처럼 "지금 진행 중인 예약"이 전제인 시나리오는 raw SQL `INSERT INTO reservations (..., time_range, status) VALUES (..., tstzrange(now(), now() + interval '30 minutes', '[)'), 'CONFIRMED')`로 정책을 우회 (`test_heartbeat_in_use_with_active_reservation`). 이 우회는 의도적인 테스트 hack이므로 service helper로 노출하지 말 것 — production 경로는 항상 정책을 거쳐야 한다. e2e도 같은 psql 패턴 (가이드 단계 8 참조).

### 마이그레이션 — autogenerate의 사각지대

`alembic check`가 CI에 포함되어 있지만, autogenerate는 `EXCLUDE` 제약 / JSONB `server_default` / 부분 인덱스 / GIN·GIST 인덱스를 못 본다. 모델과 마이그레이션이 이쪽에서 어긋나면 autogenerate가 못 잡는 drift가 되므로 마이그레이션을 직접 손으로 보정한다.

별개로, `alembic check`가 **정상적으로 잡는** 기존 drift 3건(`id` 컬럼 `BIGINT`↔`Integer` / 일부 `server_default` / `tokens.host_id` nullable 모델 미반영)이 `0001`/`0002`부터 누적돼 현재 `alembic check`는 실패 상태다 — 새 마이그레이션이 깬 게 아닌지 볼 땐 EXP.md §11 A12에 적힌 이 기존 항목을 제외하고 본다. 새 컬럼/제약이 drift 목록에 안 나오면 모델·마이그레이션 일치.

### Sunshine 호스트 포크는 `host-patches/`의 패치 시리즈로 관리 (T10)

강의실 PC의 Sunshine 호스트는 업스트림이 아니라 SmartClassroom 포크를 쓴다. 포크 소스 자체는 이 레포에 두지 않고, **업스트림 고정 태그 위에 순서대로 적용하는 번호 붙은 `.patch` 시리즈**(`host-patches/sunshine/`)로만 관리한다:

- 포크 체크아웃: `D:/Hongsun/Sunshine`, origin `KITOHSY/Sunshine`, 패치 브랜치 `smartclassroom/t10-token-pin`, 고정 업스트림 태그 `v2025.628.4510`.
- 적용: 클린 클론에 `git am host-patches/sunshine/*.patch`. 재생성: `git format-patch <태그>..HEAD -o host-patches/sunshine -- src/` — `-- src/` 경로 한정이 핵심으로, CI 워크플로 커밋이 패치 시리즈에 섞이지 않게 한다.
- T10이 첫 시리즈(`sunshine.conf`의 `broker_api_token` 키 + `confighttp` Bearer 인증 경로). 패치 0003/0004는 빌드 보정 — autogenerate 같은 자동화가 없으므로 멤버 추가 시 aggregate initializer 동기화 등은 수동으로 챙긴다. Windows 빌드·검증 절차와 환경 전제(MSYS2 UCRT64, Boost 1.87 강제, 설치본 `SunshineService` 포트 충돌, Bearer 검증 전 관리자 자격증명 1회 설정 필요)는 `host-patches/sunshine/BUILD.md`, 패치 목록은 같은 폴더 `README.md`.
- connect 토큰 동적 검증(Sunshine→Broker `/tokens/verify` 콜백, §11 A6 B안)은 **미구현** — T08은 정상 흐름에 불필요(페어링 후 인증은 mTLS 클라이언트 인증서)하다고 보고 범위 밖으로 뒀다. 필요해지면 이 시리즈에 후속 패치로 추가(같은 번호 규칙). `client-patches/` (T13/T14 Moonlight fork)도 같은 패턴 — T13 시리즈는 머지 완료(아래 절).

### Moonlight 클라이언트 포크는 `client-patches/`의 패치 시리즈로 관리 (T13/T14)

학생 PC의 Moonlight 클라이언트도 업스트림이 아니라 SmartClassroom 포크를 쓴다. Sunshine과 같은 모델 — 포크 소스는 이 레포에 두지 않고, **업스트림 고정 태그 위에 순서대로 적용하는 번호 붙은 `.patch` 시리즈**(`client-patches/moonlight-qt/`)로 관리한다:

- 포크 체크아웃: `D:/Hongsun/moonlight-qt`, origin `KITOHSY/moonlight-qt`, upstream `moonlight-stream/moonlight-qt`, 패치 브랜치 `smartclassroom/t13-url-handler`, 고정 업스트림 태그 `v6.1.0`.
- 적용: 클린 클론에 `git am client-patches/moonlight-qt/*.patch`. 재생성: `git format-patch <태그>..HEAD -o client-patches/moonlight-qt -- app/ wix/` — `-- app/ wix/` 경로 한정이 CI 워크플로 커밋·submodule 잡음을 시리즈에서 제외한다 (Sunshine의 `-- src/`와 같은 원칙).
- 패치 시리즈는 현재 **11건** — T13 0001–0008 (기능 6 + 빌드 보정 0007/0008), T14 0009/0010/0011. T13 시리즈: ① `connect` 서브커맨드 CLI 파서, ② `moonlight://` URL 핸들러 + URL→CLI 확장 + `QLocalServer/QLocalSocket` 단일 인스턴스 forward, ③ `ComputerManager::requestConnect` + `NvComputer::pendingConnectToken`·`pendingHostId` 비-영속 멤버, ④ Windows WiX `HKCR\moonlight` URL Protocol 등록, ⑤ macOS `Info.plist` `CFBundleURLTypes`, ⑥ Linux `.desktop` `MimeType=x-scheme-handler/moonlight;`. T14 시리즈: 0009 `ScBrokerClient`(Broker `POST /api/v1/pairing`), 0010 자동 연결(broker URL 파라미터 + 헤드리스 페어링 + 자동연결 상태머신 + `main.qml` `StreamSegue` 자동 진입), 0011 e2e 보정(`main.cpp`의 `queryItemValue("broker")` 기본 `PrettyDecoded`가 `:` `/`를 percent-encoded로 두는 문제 → `QUrl::FullyDecoded`로 변경). 빌드 toolchain은 **Qt 6.7 `msvc2019_64` flavor + MSVC v143/v144** (업스트림 v6.1.0 CI 매트릭스 `appveyor.yml` 답습 — Sunshine의 MSYS2 UCRT64와는 다르다). 검증 절차·환경 전제·OS별 hazard는 `client-patches/moonlight-qt/BUILD.md`.
- **선계약 (변경 시 양쪽 같이)**: URL 스키마 `moonlight://connect?token=&host-id=&host=&port=&broker=`는 `frontend/src/lib/moonlight.ts::buildMoonlightUrl`가 조립 — 키 이름을 바꾸면 T13/T14 fork와 프런트를 함께 고쳐야 한다. `broker`(T14 추가)는 Moonlight가 페어링 PIN을 POST할 Broker base URL — 프런트가 `window.location.origin`을 넣는다. **`port=`는 Sunshine HTTP 폴링 포트(47989)**다, 스트리밍 HTTPS 포트(47984) 아님 — Moonlight `requestConnect` → `addNewHost` → `NvHTTP::getServerInfo`가 HTTP로 폴링하므로. Broker `HostCreate.sunshine_port` 기본값이 47984(HTTPS)라 그대로 등록하면 Moonlight가 47984에 HTTP를 보내 실패한다 — 2026-05-24 e2e에서 발견, 임시 `sunshine_port=47989`로 등록(§11 A13 정식 fix 후보).
- **T13 v1 폴백 → T14가 해소**: T13만 머지된 상태에서는 token이 `pendingConnectToken`에 보관만 되고 페어링된 호스트는 통상 stream, 미페어링 호스트는 표준 PIN 입력 화면으로 fall-through(KPI 미충족이지만 회귀 없음). **T14(0009/0010)가 자동 페어링 + 자동 스트림을 더해 "입력 0개" KPI를 달성** — connect 토큰을 Sunshine NvHTTP 헤더에 싣는 게 아니라(그 설계는 폐기) `ScBrokerClient`가 토큰+PIN을 Broker `/api/v1/pairing`에 POST하면 T08이 Sunshine `/api/pin`에 relay하는 **PIN-relay 모델**. 미페어링 호스트는 `ComputerManager::beginHeadlessPairing`(다이얼로그 없는 헤드리스 페어링) → 상태머신이 "Desktop" 앱 잡아 `Session` 생성 → `StreamSegue` 자동 진입. 실패·타임아웃 시 표준 PcView로 폴백.

## 헷갈릴 때 참조

- `PRD.md` — 제품이 무엇이고 무엇이 아닌지.
- `EXP.md` — 어떤 작업이 어떤 순서·의존성으로 계획되어 있는지. 크리티컬 패스는 `§0`. 태스크를 마칠 때 여기에 상태를 갱신한다.
- `README.md` — Quickstart, 관측성 카탈로그 (메트릭 이름, 헤더, 환경 변수).
- `host-patches/sunshine/README.md` · `BUILD.md` — Sunshine 호스트 포크 패치 목록과 Windows 빌드·검증 절차.
- `client-patches/moonlight-qt/README.md` · `BUILD.md` — Moonlight 클라이언트 포크 패치 목록과 Windows 빌드·검증 절차.
