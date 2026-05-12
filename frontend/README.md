# SmartClassroom Frontend

React 18 + Vite + TypeScript (strict) — 충남대 강의실 PC 예약 포털 v1.

## Quickstart (cmd.exe)

```cmd
cd frontend
pnpm install
pnpm dev
```

Vite는 5173 포트에서 기동되고 `/api/*`는 `http://localhost:8000` (broker) 으로 프록시된다.
백엔드 동시 기동:

```cmd
docker compose up postgres -d
uv run uvicorn broker.app.main:app --reload
```

## 주요 스크립트

| 명령 | 용도 |
| --- | --- |
| `pnpm dev` | dev server (HMR + /api 프록시) |
| `pnpm build` | typecheck + 프로덕션 번들 |
| `pnpm preview` | build 결과 로컬 서빙 |
| `pnpm lint` / `pnpm lint:fix` | ESLint |
| `pnpm format:check` / `pnpm format` | Prettier |
| `pnpm typecheck` | tsc strict (no emit) |
| `pnpm test` | Vitest run |
| `pnpm test:ui` | Vitest watch UI |

## 인증 흐름 (T16, Mock)

1. `/` 진입 → 미인증이면 `/login`으로 redirect.
2. `/login`에서 external_id / display_name / role 입력 → POST `/api/v1/auth/mock/callback`.
3. 세션 쿠키(HttpOnly) 발급 → 캘린더 진입.

> T04b CNU SSO 머지 시 `LoginPage`의 mock 폼을 SSO 리다이렉트로 교체한다 (`TODO(T04b)` 마커 참조).
