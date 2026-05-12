import { describe, it, expect } from 'vitest';
import { AxiosError, AxiosHeaders } from 'axios';
import {
  extractValidationErrors,
  isInvalidReservationWindow,
  isReservationConflict,
  isReservationQuotaExceeded,
  parseApiError,
  type ApiErrorBody,
} from './errors';

function makeAxiosError(status: number, body: ApiErrorBody | unknown): AxiosError<ApiErrorBody> {
  const headers = new AxiosHeaders();
  const err = new AxiosError(
    'Request failed',
    String(status),
    { headers } as never,
    null,
    {
      status,
      statusText: 'ERR',
      headers: {},
      config: { headers } as never,
      data: body as ApiErrorBody,
    },
  );
  return err as AxiosError<ApiErrorBody>;
}

describe('parseApiError', () => {
  it('axios 422 validation_error에서 errors[]를 detail에 보존', () => {
    const err = makeAxiosError(422, {
      error: 'validation_error',
      message: '입력값 검증 실패',
      detail: {
        errors: [{ loc: ['body', 'host_id'], msg: 'field required', type: 'missing' }],
      },
    });
    const parsed = parseApiError(err);
    expect(parsed.status).toBe(422);
    expect(parsed.code).toBe('validation_error');
    expect(extractValidationErrors(parsed)).toHaveLength(1);
    expect(extractValidationErrors(parsed)[0]?.msg).toBe('field required');
  });

  it('422 invalid_reservation_window에서 detail.reason 보존', () => {
    const err = makeAxiosError(422, {
      error: 'invalid_reservation_window',
      message: '예약 시작 시간이 유효하지 않습니다',
      detail: { reason: 'too_early', field: 'starts_at' },
    });
    const parsed = parseApiError(err);
    expect(isInvalidReservationWindow(parsed)).toBe(true);
    expect(parsed.detail?.reason).toBe('too_early');
  });

  it('409 reservation_conflict 인식', () => {
    const err = makeAxiosError(409, {
      error: 'reservation_conflict',
      message: '이미 예약된 슬롯입니다',
      detail: { constraint: 'reservations_no_overlap' },
    });
    const parsed = parseApiError(err);
    expect(isReservationConflict(parsed)).toBe(true);
    expect(parsed.status).toBe(409);
  });

  it('429 reservation_quota_exceeded에서 limit/current/max 보존', () => {
    const err = makeAxiosError(429, {
      error: 'reservation_quota_exceeded',
      message: '한도 초과',
      detail: { limit: 'concurrent', current: 2, max: 2 },
    });
    const parsed = parseApiError(err);
    expect(isReservationQuotaExceeded(parsed)).toBe(true);
    expect(parsed.detail?.limit).toBe('concurrent');
    expect(parsed.detail?.current).toBe(2);
    expect(parsed.detail?.max).toBe(2);
  });

  it('비-axios 에러 → fallback code', () => {
    const parsed = parseApiError(new Error('boom'));
    expect(parsed.code).toBe('unknown_error');
    expect(parsed.message).toBe('boom');
    expect(parsed.status).toBeNull();
  });

  it('axios지만 body 형식이 다르면 fallback code 유지', () => {
    const err = makeAxiosError(500, 'plain text');
    const parsed = parseApiError(err);
    expect(parsed.status).toBe(500);
    expect(parsed.code).toBe('unknown_error');
  });
});
