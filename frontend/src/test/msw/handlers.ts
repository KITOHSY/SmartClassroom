import { http, HttpResponse } from 'msw';
import type { User } from '@/lib/auth';
import type { HostRead } from '@/api/hosts';
import type { CalendarMatrix, Reservation } from '@/api/reservations';

/**
 * MSW handlers — 백엔드 contract 모킹.
 *
 * 기본 흐름은 "기본은 401 미인증, 로그인 mutation 후 /auth/me가 200 user를 반환"이지만
 * 테스트별로 서버 상태를 격리하기 위해 named export를 두고 `server.use(...)`로 덮어쓰는
 * 방식을 권장한다 — 이 모듈 내부의 mutable state(`mockSessionUser`)는 각 테스트의
 * `afterEach(server.resetHandlers)` 시점에 setup.ts에서 함께 리셋한다.
 */

export const TEST_USER: User = {
  id: 1001,
  external_id: 'mock-202000001',
  display_name: '홍길동',
  email: 'gildong@cnu.ac.kr',
  role: 'user',
  provider: 'mock',
};

export const TEST_ADMIN: User = {
  id: 1002,
  external_id: 'mock-admin',
  display_name: '관리자',
  email: 'admin@cnu.ac.kr',
  role: 'admin',
  provider: 'mock',
};

export const TEST_HOSTS: HostRead[] = [
  {
    id: 1,
    hostname: 'pc-101',
    display_name: '강의실 A-101',
    location: '공대 1호관 101호',
    status: 'ACTIVE',
    sunshine_port: 47989,
  },
  {
    id: 2,
    hostname: 'pc-102',
    display_name: '강의실 A-102',
    location: '공대 1호관 102호',
    status: 'ACTIVE',
    sunshine_port: 47989,
  },
];

let mockSessionUser: User | null = null;

export function setMockSession(user: User | null): void {
  mockSessionUser = user;
}

export function getMockSession(): User | null {
  return mockSessionUser;
}

/** Asia/Seoul 기준 임의의 미래 일자에 30분 슬롯 매트릭스를 생성. */
export function buildCalendarMatrix(
  hosts: HostRead[] = TEST_HOSTS,
  baseDate: Date = new Date('2026-05-13T00:00:00+09:00'),
  slotCount: number = 6,
): CalendarMatrix {
  const slotMinutes = 30;
  // KST 09:00부터 30분 간격 slotCount개.
  const baseStartUtcMs =
    new Date(baseDate.toISOString().slice(0, 10) + 'T09:00:00+09:00').getTime();
  const slots = [];
  for (const host of hosts) {
    for (let i = 0; i < slotCount; i++) {
      const startMs = baseStartUtcMs + i * slotMinutes * 60_000;
      const endMs = startMs + slotMinutes * 60_000;
      slots.push({
        starts_at: new Date(startMs).toISOString(),
        ends_at: new Date(endMs).toISOString(),
        host_id: host.id,
        reservation_id: null,
        user_id: null,
        status: 'OPEN' as const,
      });
    }
  }
  return {
    from_: new Date(baseStartUtcMs).toISOString(),
    to_: new Date(baseStartUtcMs + slotCount * slotMinutes * 60_000).toISOString(),
    slot_minutes: slotMinutes,
    slots,
  };
}

export function buildReservation(overrides: Partial<Reservation> = {}): Reservation {
  return {
    id: 1,
    user_id: 1,
    host_id: 1,
    starts_at: '2026-05-13T00:00:00+00:00',
    ends_at: '2026-05-13T00:30:00+00:00',
    status: 'CONFIRMED',
    created_at: '2026-05-12T00:00:00+00:00',
    canceled_at: null,
    ...overrides,
  };
}

export const handlers = [
  // GET /api/v1/auth/me — 세션 상태에 따라 200 user 또는 401.
  http.get('/api/v1/auth/me', () => {
    if (mockSessionUser) {
      return HttpResponse.json(mockSessionUser, { status: 200 });
    }
    return HttpResponse.json(
      {
        error: 'unauthenticated',
        message: 'Authentication required',
        request_id: 'req-test-401',
        detail: { login_url: '/api/v1/auth/mock' },
      },
      { status: 401 },
    );
  }),

  // POST /api/v1/auth/mock/callback — 200 + 세션 시뮬레이션.
  http.post('/api/v1/auth/mock/callback', async ({ request }) => {
    const body = (await request.json()) as {
      external_id: string;
      display_name: string;
      role: 'user' | 'admin';
    };
    const user: User = {
      id: body.role === 'admin' ? TEST_ADMIN.id : TEST_USER.id,
      external_id: body.external_id,
      display_name: body.display_name,
      email: null,
      role: body.role,
      provider: 'mock',
    };
    mockSessionUser = user;
    return HttpResponse.json(
      { user, expires_at: '2026-05-13T00:00:00+00:00' },
      {
        status: 200,
        headers: {
          // 실제 백엔드 흉내 — jsdom은 Set-Cookie를 자동 처리하지 않으나 contract 노출 목적.
          'Set-Cookie': 'sc_session=mock-token; HttpOnly; Path=/; SameSite=Lax',
        },
      },
    );
  }),

  // POST /api/v1/auth/logout — 204.
  http.post('/api/v1/auth/logout', () => {
    mockSessionUser = null;
    return new HttpResponse(null, { status: 204 });
  }),

  // GET /api/v1/hosts — 200 + 호스트 목록.
  http.get('/api/v1/hosts', () => {
    return HttpResponse.json(TEST_HOSTS, { status: 200 });
  }),

  // GET /api/v1/reservations/calendar — 200 + 슬롯 매트릭스.
  http.get('/api/v1/reservations/calendar', () => {
    return HttpResponse.json(buildCalendarMatrix(), { status: 200 });
  }),

  // POST /api/v1/reservations — 기본 201 (테스트별로 server.use로 덮어쓰기).
  http.post('/api/v1/reservations', async ({ request }) => {
    const body = (await request.json()) as {
      host_id: number;
      starts_at: string;
      ends_at: string;
    };
    return HttpResponse.json(
      buildReservation({
        id: 100,
        host_id: body.host_id,
        starts_at: body.starts_at,
        ends_at: body.ends_at,
      }),
      { status: 201 },
    );
  }),

  // GET /api/v1/reservations — 본인 예약 목록.
  http.get('/api/v1/reservations', () => {
    return HttpResponse.json([buildReservation()], { status: 200 });
  }),

  // DELETE /api/v1/reservations/:id — 204.
  http.delete('/api/v1/reservations/:id', () => {
    return new HttpResponse(null, { status: 204 });
  }),
];

/**
 * 시나리오별 reservation POST 응답 — 테스트 안에서 `server.use(...)`로 덮어쓴다.
 */
export const reservationConflictHandler = http.post('/api/v1/reservations', () =>
  HttpResponse.json(
    {
      error: 'reservation_conflict',
      message: '이미 예약된 슬롯입니다',
      request_id: 'req-test-409',
      detail: { constraint: 'reservations_no_overlap' },
    },
    { status: 409 },
  ),
);

export const reservationInvalidWindowHandler = http.post('/api/v1/reservations', () =>
  HttpResponse.json(
    {
      error: 'invalid_reservation_window',
      message: '예약 시작 시간이 유효하지 않습니다',
      request_id: 'req-test-422',
      detail: { reason: 'too_early', field: 'starts_at' },
    },
    { status: 422 },
  ),
);

export const reservationQuotaConcurrentHandler = http.post('/api/v1/reservations', () =>
  HttpResponse.json(
    {
      error: 'reservation_quota_exceeded',
      message: '동시 예약 한도 초과',
      request_id: 'req-test-429',
      detail: { limit: 'concurrent', current: 2, max: 2 },
    },
    { status: 429 },
  ),
);

export const reservationQuotaDailyHandler = http.post('/api/v1/reservations', () =>
  HttpResponse.json(
    {
      error: 'reservation_quota_exceeded',
      message: '일일 예약 한도 초과',
      request_id: 'req-test-429',
      detail: { limit: 'daily_minutes', current: 240, max: 240 },
    },
    { status: 429 },
  ),
);

export const reservationValidationErrorHandler = http.post('/api/v1/reservations', () =>
  HttpResponse.json(
    {
      error: 'validation_error',
      message: '입력값 검증 실패',
      request_id: 'req-test-422v',
      detail: {
        errors: [
          { loc: ['body', 'host_id'], msg: 'field required', type: 'missing' },
        ],
      },
    },
    { status: 422 },
  ),
);
