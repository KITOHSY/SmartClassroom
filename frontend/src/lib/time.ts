import { addMinutes } from 'date-fns';
import { formatInTimeZone, toZonedTime } from 'date-fns-tz';

export const KST = 'Asia/Seoul';
export const SLOT_MINUTES = 30;
export const LOOKAHEAD_DAYS = 14;

export function formatSlotLabel(date: Date | string): string {
  return formatInTimeZone(typeof date === 'string' ? new Date(date) : date, KST, 'HH:mm');
}

export function formatDateLabel(date: Date | string): string {
  return formatInTimeZone(typeof date === 'string' ? new Date(date) : date, KST, 'yyyy-MM-dd');
}

export function formatDateTimeLabel(date: Date | string): string {
  return formatInTimeZone(
    typeof date === 'string' ? new Date(date) : date,
    KST,
    'yyyy-MM-dd HH:mm',
  );
}

/** available_until(ISO)까지 남은 시간을 사람이 읽는 문자열로 — "15분", "2시간 30분". */
export function formatAvailableWindow(untilIso: string): string {
  const mins = Math.round((new Date(untilIso).getTime() - Date.now()) / 60_000);
  if (mins <= 0) return '곧 다음 예약 시작';
  if (mins < 60) return `${mins}분`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return m === 0 ? `${h}시간` : `${h}시간 ${m}분`;
}

export function floorToSlot(date: Date, slotMinutes: number = SLOT_MINUTES): Date {
  const result = new Date(date);
  result.setSeconds(0, 0);
  const remainder = result.getMinutes() % slotMinutes;
  if (remainder !== 0) {
    result.setMinutes(result.getMinutes() - remainder);
  }
  return result;
}

export function ceilToSlot(date: Date, slotMinutes: number = SLOT_MINUTES): Date {
  const floored = floorToSlot(date, slotMinutes);
  if (floored.getTime() === date.getTime()) return floored;
  return addMinutes(floored, slotMinutes);
}

/**
 * KST 기준 그날 시작(00:00)을 UTC ISO로 반환.
 * 백엔드는 timezone-aware datetime을 요구하므로 offset 포함 ISO 사용.
 */
export function kstStartOfDay(date: Date): Date {
  const zoned = toZonedTime(date, KST);
  zoned.setHours(0, 0, 0, 0);
  // toZonedTime이 만든 시각은 KST를 표시하지만 내부적으로 UTC offset 만큼 어긋난다 —
  // formatInTimeZone으로 KST ISO를 다시 만들어 정확한 instant 확보.
  const iso = formatInTimeZone(zoned, KST, "yyyy-MM-dd'T'00:00:00XXX");
  return new Date(iso);
}

/**
 * 캘린더 윈도우 종료 시각 — 반열림 구간 [from, to).
 *
 * T21은 캘린더를 하루가 아닌 2일(96칸) 윈도우로 렌더해 드래그가 자정 경계를 넘어
 * 다음 날 칸까지 이어지게 한다. 종료는 항상 KST 00:00 경계 — 백엔드 `_ensure_grid`가
 * 30분 그리드(:00/:30)만 허용하므로 23:59:59 같은 비그리드 종료는 422.
 */
export function kstWindowEnd(date: Date, days = 2): Date {
  const zoned = toZonedTime(date, KST);
  zoned.setHours(0, 0, 0, 0);
  const end = addDays(zoned, days);
  const iso = formatInTimeZone(end, KST, "yyyy-MM-dd'T'00:00:00XXX");
  return new Date(iso);
}

export function toIsoWithOffset(date: Date): string {
  // Plus offset (e.g. 2026-05-12T09:00:00+09:00) — 백엔드가 timezone-aware로 파싱.
  return formatInTimeZone(date, KST, "yyyy-MM-dd'T'HH:mm:ssXXX");
}

export function addDays(date: Date, days: number): Date {
  const result = new Date(date);
  result.setDate(result.getDate() + days);
  return result;
}
