import { AxiosError, isAxiosError } from 'axios';

export interface ApiErrorBody {
  error: string;
  message: string;
  request_id?: string | null;
  detail?: Record<string, unknown> | null;
}

export interface ParsedApiError {
  status: number | null;
  code: string;
  message: string;
  requestId: string | null;
  detail: Record<string, unknown> | null;
}

const FALLBACK: Omit<ParsedApiError, 'status'> = {
  code: 'unknown_error',
  message: '알 수 없는 오류가 발생했습니다',
  requestId: null,
  detail: null,
};

export function parseApiError(err: unknown): ParsedApiError {
  if (isAxiosError(err)) {
    const ax = err as AxiosError<ApiErrorBody>;
    const status = ax.response?.status ?? null;
    const body = ax.response?.data;
    if (body && typeof body === 'object' && 'error' in body) {
      return {
        status,
        code: body.error || FALLBACK.code,
        message: body.message || ax.message || FALLBACK.message,
        requestId: body.request_id ?? null,
        detail: (body.detail as Record<string, unknown> | null | undefined) ?? null,
      };
    }
    return {
      status,
      code: FALLBACK.code,
      message: ax.message || FALLBACK.message,
      requestId: null,
      detail: null,
    };
  }
  if (err instanceof Error) {
    return { status: null, ...FALLBACK, message: err.message };
  }
  return { status: null, ...FALLBACK };
}

export interface ValidationFieldError {
  loc: (string | number)[];
  msg: string;
  type?: string;
}

export function extractValidationErrors(parsed: ParsedApiError): ValidationFieldError[] {
  if (parsed.code !== 'validation_error' || !parsed.detail) return [];
  const errors = parsed.detail.errors;
  if (!Array.isArray(errors)) return [];
  return errors.filter(
    (e): e is ValidationFieldError =>
      typeof e === 'object' &&
      e !== null &&
      Array.isArray((e as ValidationFieldError).loc) &&
      typeof (e as ValidationFieldError).msg === 'string',
  );
}

export function isReservationConflict(parsed: ParsedApiError): boolean {
  return parsed.status === 409 && parsed.code === 'reservation_conflict';
}

export function isReservationQuotaExceeded(parsed: ParsedApiError): boolean {
  return parsed.status === 429 && parsed.code === 'reservation_quota_exceeded';
}

export function isInvalidReservationWindow(parsed: ParsedApiError): boolean {
  return parsed.status === 422 && parsed.code === 'invalid_reservation_window';
}
