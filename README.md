# SmartClassroom Broker

충남대 강의실 PC 원격 접속 시스템의 Broker 백엔드. 예약 / 인증 / 동적 토큰 / 자동 페어링 / 세션 라이프사이클을 오케스트레이션한다.

기획 문서: [PRD.md](./PRD.md), 실행 계획: [EXP.md](./EXP.md).

---

## Quickstart

### Docker (권장)

```bash
docker compose up --build
# postgres가 healthy 상태가 되면 broker가 alembic upgrade head 후 기동
```

검증:
```bash
curl http://localhost:8000/healthz                           # {"status":"ok"}
curl http://localhost:8000/readyz                            # {"status":"ready",...}
curl http://localhost:8000/api/v1/version                    # {"version":"0.1.0",...}
curl http://localhost:8000/metrics | head                    # Prometheus 메트릭
open http://localhost:8000/docs                              # Swagger UI
```

### 로컬 실행 (DB 없이)

```bash
pip install uv
uv sync --extra dev
uv run uvicorn broker.app.main:app --reload
curl http://localhost:8000/healthz   # /readyz는 DB 없으면 503
```

### 테스트

```bash
docker compose up postgres -d
uv run pytest -v
```

### Frontend (T16)

```cmd
cd frontend
pnpm install
pnpm dev
```

Vite는 5173 포트, `/api/*`는 `http://localhost:8000` (broker)으로 프록시. 백엔드 동시 기동 후 `http://localhost:5173/`. 자세한 내용은 [`frontend/README.md`](./frontend/README.md).

### Agent (T11)

```cmd
cd agent
uv sync --extra dev
uv run python -m smartclassroom_agent doctor --config agent.yaml
```

강의실 PC에 설치하는 사이드카. `agent.yaml`에 `broker_url`/`host_id`/`agent_token`(admin이 `POST /api/v1/hosts`로 받은 raw 토큰) 주입 후 `run` 명령으로 30s 주기 heartbeat. 자세한 내용은 [`agent/README.md`](./agent/README.md).

---

## Stack

- Python 3.12 + FastAPI + SQLAlchemy 2.0 (async) + Alembic
- PostgreSQL 16 (`btree_gist`, `pgcrypto` 확장 사용)
- structlog (JSON 로깅) + prometheus-fastapi-instrumentator (메트릭)
- Docker + docker-compose + GitHub Actions
- 패키지 매니저: 백엔드 `uv`, 프런트 `pnpm` (Node 20)
- 프런트(T16): React 18 + Vite + TypeScript strict + TanStack Query + Tailwind

---

## 디렉터리 구조

```
broker/
├── app/
│   ├── main.py                  # create_app() + lifespan + 운영 가드
│   ├── core/
│   │   ├── config.py            # pydantic-settings Settings
│   │   ├── logging.py           # structlog JSON 설정
│   │   ├── middleware.py        # RequestIdMiddleware, AccessLogMiddleware
│   │   ├── metrics.py           # setup_metrics() + 후속 커스텀 카운터
│   │   ├── errors.py            # 표준 에러 핸들러 + ErrorResponse
│   │   └── auth.py              # AuthProvider Protocol (T04a 슬롯)
│   ├── api/
│   │   ├── deps.py              # get_db
│   │   ├── v1/{router,health,meta}.py
│   │   └── schemas/common.py
│   ├── domain/                  # 6개 SQLAlchemy 모델
│   │   ├── user.py / host.py / reservation.py
│   │   ├── session.py / token.py / audit.py (write_audit 헬퍼 포함)
│   │   └── _mixins.py           # IdMixin, TimestampMixin
│   └── infra/
│       ├── db.py                # async engine, sessionmaker, Base
│       └── repositories/        # 후속 태스크가 채움
├── alembic/
│   ├── env.py                   # async 모드
│   └── versions/0001_initial.py # 6개 테이블 + EXCLUDE GIST 제약
├── tests/                       # pytest + testcontainers
└── Dockerfile                   # 멀티스테이지 (uv builder + slim runtime)
```

`broker/`로 한 번 더 감싸는 이유: `frontend/`(T16, 아래 참조)와 `agent/`(T11, 아래 참조)가 형제로 들어와 있고, 향후 `client-patches/`(T13/T14 Moonlight fork)가 합류할 모노레포 가정.

```
agent/                              # T11 호스트 에이전트 (Python + uv, 자체 루트)
├── smartclassroom_agent/
│   ├── cli.py                      # typer (run / doctor / install-service)
│   ├── client.py                   # httpx — Bearer agent token 자동 첨부
│   ├── heartbeat.py                # asyncio loop, 30s 주기
│   ├── collectors/                 # system / session / gpu / rtt
│   └── service/                    # windows.py(NSSM), systemd.py(unit 헬퍼)
└── tests/                          # pytest + pytest-httpx (34건)
```

```
frontend/                           # T16 React+Vite+TS 프런트엔드
├── src/
│   ├── api/                        # axios + 백엔드 contract 매핑
│   ├── components/                 # CalendarGrid, ReservationModal, RequireAuth, Layout, Toast
│   ├── hooks/                      # useRovingTabIndex, useFocusTrap
│   ├── lib/                        # auth, errors, time(KST), queryClient
│   ├── pages/                      # LoginPage, CalendarPage, MyReservationsPage
│   ├── routes/                     # React Router v6 정의
│   ├── styles/                     # Tailwind index.css
│   └── test/                       # Vitest setup + MSW handlers
├── package.json (pnpm 9, Node 20)
├── vite.config.ts (5173, /api 프록시)
└── tsconfig.json (strict, exactOptionalPropertyTypes)
```

---

## ER 다이어그램

```mermaid
erDiagram
    USERS ||--o{ RESERVATIONS : owns
    HOSTS ||--o{ RESERVATIONS : booked_for
    RESERVATIONS ||--o{ SESSIONS : produces
    USERS ||--o{ SESSIONS : occupies
    HOSTS ||--o{ SESSIONS : runs_on
    USERS ||--o{ TOKENS : issued_for
    HOSTS ||--o{ TOKENS : grants_access_to
    RESERVATIONS ||--o{ TOKENS : derived_from
    USERS ||--o{ AUDIT_LOGS : actor

    USERS {
        bigint id PK
        uuid public_id
        string external_id
        string provider
        string display_name
        string email
        string role
        bool is_active
    }
    HOSTS {
        bigint id PK
        uuid public_id
        string hostname
        string display_name
        inet ip_address
        int sunshine_port
        string status
        timestamptz last_heartbeat_at
    }
    RESERVATIONS {
        bigint id PK
        uuid public_id
        bigint user_id FK
        bigint host_id FK
        tstzrange time_range
        string status
    }
    SESSIONS {
        bigint id PK
        uuid public_id
        bigint reservation_id FK
        string state
        timestamptz started_at
        timestamptz ended_at
        string end_reason
    }
    TOKENS {
        bigint id PK
        string jti UK
        bigint user_id FK
        bigint host_id FK
        string purpose
        timestamptz expires_at
        timestamptz consumed_at
    }
    AUDIT_LOGS {
        bigint id PK
        timestamptz occurred_at
        bigint actor_user_id FK
        string action
        string target_kind
        string request_id
        string auth_provider
        string result
    }
```

**핵심 제약**: `reservations` 에는 `EXCLUDE USING GIST (host_id WITH =, time_range WITH &&) WHERE status IN ('CONFIRMED','COMPLETED')` 가 걸려 있어, 동일 호스트의 시간 겹침 예약을 DB 레벨에서 차단한다.

---

## Observability 가이드

### 로깅

모든 로그는 stdout에 JSON 한 줄로 출력. 표준 필드:

| 필드 | 설명 |
|---|---|
| `timestamp` | ISO8601 UTC |
| `level` | debug/info/warning/error |
| `event` | 메시지 키 (snake_case 권장) |
| `request_id` | `RequestIdMiddleware`가 자동 주입 |
| `user_id`, `auth_provider` | T04a 인증 미들웨어가 contextvars로 주입 |

핸들러 코드 예:
```python
import structlog
log = structlog.get_logger(__name__)
log.info("reservation.created", reservation_id=42, user_id=1, host_id=7)
```

### 메트릭 카탈로그

- `http_requests_total{method,handler,status}` — 요청 수
- `http_request_duration_seconds_bucket{handler,...}` — 지연 분포 (버킷: 25ms / 50ms / 100ms / **200ms** / 500ms / 1s / 2s / 5s)
- `broker_reservation_conflict_total{host_id}` — 예약 슬롯 충돌 횟수 (T05)
- `broker_token_issued_total{purpose}` — 동적 접속 토큰 발급 (T07)
- `broker_pairing_duration_seconds{result}` — 자동 페어링 소요 시간 (T08)

`/metrics`는 `ENABLE_METRICS=true` (기본) 일 때 활성. `/healthz`, `/readyz`, `/metrics` 자체는 라벨링 제외.

### 헬스 엔드포인트

| 경로 | 용도 | 검증 항목 | 실패 응답 |
|---|---|---|---|
| `/healthz` | Liveness (K8s liveness probe) | (없음) | 호출 자체 실패 |
| `/readyz` | Readiness (K8s readiness probe) | DB `SELECT 1` | 503 + `{"status":"not_ready","checks":{...}}` |

K8s 운영 시 liveness가 DB까지 검증하면 일시 장애로 모든 파드가 강제 재시작되므로 두 엔드포인트를 분리.

---

## 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `APP_ENV` | `development` | `development`/`staging`/`production`/`test` |
| `LOG_LEVEL` | `INFO` | structlog 레벨 |
| `DATABASE_URL` | `postgresql+asyncpg://broker:broker@localhost:5432/broker` | async URL 필수 |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | JSON list |
| `EXPOSE_DOCS` | `true` | production은 `false` 권장 |
| `AUTH_PROVIDER` | `mock` | T04a가 `cnu_sso` 등 추가 |
| `SESSION_SECRET` | `change-me` | production에서 부팅 시 거부 |
| `ENABLE_METRICS` | `true` | `/metrics` 노출 토글 |

### 운영 가드

`APP_ENV=production` AND `AUTH_PROVIDER=mock` 조합은 `lifespan` 시작 시 `RuntimeError`로 거부 — EXP §11 Mock-first 운영 가드 충족. `SESSION_SECRET`이 기본값(`change-me`/`dev-secret`/빈 문자열) 인 경우에도 production 부팅 거부.

---

## 마이그레이션

```bash
# 적용
uv run alembic upgrade head

# 새 리비전 생성 (autogenerate)
uv run alembic revision --autogenerate -m "add foo column"
# ⚠ EXCLUDE/JSONB default/GIN/GIST 인덱스는 autogenerate가 못 잡음 — 사람 검토 필수.

# 모델/마이그레이션 drift 검증
uv run alembic check

# 1단계 롤백
uv run alembic downgrade -1
```

---

## Pitfalls (구현 시 자주 만나는 함정)

1. **Async SQLAlchemy** — `expire_on_commit=False` 강제(이미 `infra/db.py`). lazy loading 금지(`selectinload`/`joinedload`만). `Depends(get_db)` yield로 세션 lifecycle 보장. `MissingGreenlet`이 가장 흔한 사고.
2. **Alembic async env.py** — `alembic init -t async` 템플릿 패턴. autogenerate는 `EXCLUDE`, JSONB default, GIN/GIST 인덱스를 못 잡음 → raw SQL로 직접.
3. **FastAPI lifespan** — `@app.on_event` 금지, `lifespan` async context 표준. 테스트에서 lifespan 효과 필요 시 `asgi-lifespan.LifespanManager`로 감쌀 것.
4. **미들웨어 LIFO** — `add_middleware`는 나중 등록이 가장 바깥. `main.py::create_app()`의 add 순서를 임의로 바꾸지 말 것.
5. **Prometheus 라벨링** — `instrumentator.expose(app)`는 모든 `include_router` 후 호출. 그래야 `/users/{id}` 패턴으로 라벨링됨.
6. **시간대** — 모든 컬럼 `TIMESTAMPTZ`, 코드 내 `datetime.now(timezone.utc)`. naive datetime 한 번 섞이면 비교 에러.
7. **운영 보안** — `.env` 비커밋, Docker 비루트 유저(`USER broker`), `EXPOSE_DOCS=false` in production.
8. **uv vs pip** — Dockerfile/CI는 uv 가정. 로컬은 `pip install -e ".[dev]"` 도 가능.

---

## 후속 태스크와의 인터페이스

| 후속 | T03이 비워둔 슬롯 |
|---|---|
| **T04a (인증)** | `core/auth.py` `AuthProvider` Protocol + 더미 `get_current_user`. structlog `bind_contextvars`에 `user_id`, `auth_provider` 추가 |
| **T05 (예약)** | `domain/reservation.py` 모델 + `EXCLUDE GIST` 제약 완비. `api/v1/router.py`의 include 자리 |
| **T06 (호스트 상태)** | `domain/host.py` `last_heartbeat_at`, `status`. SSE는 raw ASGI 미들웨어 검토 필요 |
| **T07 (토큰)** | `domain/token.py` 완비, `Token.jti` UNIQUE |
| **T09 (라이프사이클)** | `domain/session.py` 완비. 잡 스케줄러는 별도 프로세스 — main.py lifespan에 포함하지 않음 |
| 모두 | `domain/audit.py::write_audit()` 헬퍼 — request_id 자동 픽업 |
