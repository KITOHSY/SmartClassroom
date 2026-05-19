import { describe, it, expect } from 'vitest';
import { ceilToSlot, floorToSlot, formatAvailableWindow, kstWindowEnd, toIsoWithOffset } from './time';

describe('floorToSlot (30분 단위)', () => {
  it('14:14 → 14:00', () => {
    const input = new Date('2026-05-12T14:14:00+09:00');
    const out = floorToSlot(input);
    expect(out.getMinutes()).toBe(0);
    expect(out.getHours()).toBe(input.getHours());
  });

  it('14:30 → 14:30 (경계는 그대로)', () => {
    const input = new Date('2026-05-12T14:30:00+09:00');
    const out = floorToSlot(input);
    expect(out.getMinutes()).toBe(30);
  });

  it('14:31 → 14:30', () => {
    const input = new Date('2026-05-12T14:31:00+09:00');
    const out = floorToSlot(input);
    expect(out.getMinutes()).toBe(30);
  });

  it('초/밀리초 잔여를 제거', () => {
    const input = new Date('2026-05-12T14:00:45.500+09:00');
    const out = floorToSlot(input);
    expect(out.getSeconds()).toBe(0);
    expect(out.getMilliseconds()).toBe(0);
  });
});

describe('ceilToSlot (30분 단위)', () => {
  it('14:00 → 14:00 (경계는 그대로)', () => {
    const input = new Date('2026-05-12T14:00:00+09:00');
    const out = ceilToSlot(input);
    expect(out.getTime()).toBe(input.getTime());
  });

  it('14:01 → 14:30', () => {
    const input = new Date('2026-05-12T14:01:00+09:00');
    const out = ceilToSlot(input);
    expect(out.getMinutes()).toBe(30);
  });

  it('14:30 → 14:30', () => {
    const input = new Date('2026-05-12T14:30:00+09:00');
    const out = ceilToSlot(input);
    expect(out.getMinutes()).toBe(30);
  });

  it('14:45 → 15:00', () => {
    const input = new Date('2026-05-12T14:45:00+09:00');
    const out = ceilToSlot(input);
    expect(out.getMinutes()).toBe(0);
  });
});

describe('toIsoWithOffset', () => {
  it('출력에 +09:00 KST offset 포함', () => {
    const input = new Date('2026-05-12T05:00:00.000Z'); // KST 14:00
    const iso = toIsoWithOffset(input);
    expect(iso).toMatch(/\+09:00$/);
    expect(iso).toContain('14:00:00');
  });

  it('자정 경계도 KST로 변환', () => {
    const input = new Date('2026-05-12T15:00:00.000Z'); // KST 익일 00:00
    const iso = toIsoWithOffset(input);
    expect(iso).toMatch(/\+09:00$/);
    expect(iso).toContain('2026-05-13T00:00:00');
  });
});

describe('kstWindowEnd (2일 윈도우)', () => {
  it('기본 2일 뒤 KST 00:00을 반환 (반열림 [from, to))', () => {
    const base = new Date('2026-05-18T05:00:00.000Z'); // KST 2026-05-18 14:00
    const end = kstWindowEnd(base);
    // 2026-05-18 00:00 KST + 2일 = 2026-05-20 00:00 KST = 2026-05-19T15:00Z
    expect(end.toISOString()).toBe('2026-05-19T15:00:00.000Z');
  });

  it('days 인자로 윈도우 길이를 조정', () => {
    const base = new Date('2026-05-18T05:00:00.000Z');
    const end = kstWindowEnd(base, 1);
    expect(end.toISOString()).toBe('2026-05-18T15:00:00.000Z');
  });
});

describe('formatAvailableWindow', () => {
  it('1시간 미만은 분으로', () => {
    const until = new Date(Date.now() + 15 * 60_000).toISOString();
    expect(formatAvailableWindow(until)).toBe('15분');
  });

  it('정시는 시간만', () => {
    const until = new Date(Date.now() + 120 * 60_000).toISOString();
    expect(formatAvailableWindow(until)).toBe('2시간');
  });

  it('시간 + 분', () => {
    const until = new Date(Date.now() + 150 * 60_000).toISOString();
    expect(formatAvailableWindow(until)).toBe('2시간 30분');
  });

  it('이미 지난 시각은 안내 문구', () => {
    const until = new Date(Date.now() - 60_000).toISOString();
    expect(formatAvailableWindow(until)).toBe('곧 다음 예약 시작');
  });
});
