import { describe, it, expect } from 'vitest';
import { ceilToSlot, floorToSlot, toIsoWithOffset } from './time';

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
