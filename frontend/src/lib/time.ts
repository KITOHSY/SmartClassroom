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

export function kstEndOfDay(date: Date): Date {
  // 캘린더 매트릭스 to는 반열림 구간 [from, to) — 같은 날 23:30 슬롯을 포함하려면 다음날 00:00.
  // 백엔드 _ensure_grid는 30분 그리드(:00/:30)만 허용 → 23:59:59는 422.
  const zoned = toZonedTime(date, KST);
  zoned.setHours(0, 0, 0, 0);
  const next = addDays(zoned, 1);
  const iso = formatInTimeZone(next, KST, "yyyy-MM-dd'T'00:00:00XXX");
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
