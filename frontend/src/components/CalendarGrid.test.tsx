import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CalendarGrid, type CalendarCell } from './CalendarGrid';
import type { HostRead } from '@/api/hosts';
import type { CalendarSlot } from '@/api/reservations';

const HOSTS: HostRead[] = [
  {
    id: 1,
    hostname: 'pc-101',
    display_name: '강의실 A-101',
    location: null,
    status: 'IDLE',
    sunshine_port: 47989,
    ip_address: '10.0.0.1',
  },
  {
    id: 2,
    hostname: 'pc-102',
    display_name: '강의실 A-102',
    location: null,
    status: 'IN_USE',
    sunshine_port: 47989,
    ip_address: '10.0.0.2',
  },
];

function makeSlots(hostId: number, count: number, occupiedIdx: number[] = []): CalendarSlot[] {
  // base = 09:00 KST. 테스트는 슬롯 0=09:00~09:30, 슬롯 1=09:30~10:00 라벨로 검증.
  const base = new Date('2026-05-13T09:00:00+09:00').getTime();
  return Array.from({ length: count }, (_, i) => {
    const startMs = base + i * 30 * 60_000;
    const occupied = occupiedIdx.includes(i);
    return {
      starts_at: new Date(startMs).toISOString(),
      ends_at: new Date(startMs + 30 * 60_000).toISOString(),
      host_id: hostId,
      reservation_id: occupied ? 999 : null,
      user_id: occupied ? 42 : null,
      status: occupied ? 'OCCUPIED' : 'OPEN',
    };
  });
}

function buildSlotsByHost(occupiedIdx: number[] = []) {
  const map = new Map<number, CalendarSlot[]>();
  for (const h of HOSTS) {
    map.set(h.id, makeSlots(h.id, 4, occupiedIdx));
  }
  return map;
}

describe('<CalendarGrid />', () => {
  it('grid ARIA 속성: role=grid + aria-rowcount + aria-colcount', () => {
    const slotsByHost = buildSlotsByHost();
    render(
      <CalendarGrid
        hosts={HOSTS}
        slotsByHost={slotsByHost}
        currentUserId={1}
        onCellActivate={() => undefined}
      />,
    );
    const grid = screen.getByRole('grid', { name: /예약 캘린더/ });
    // 헤더 행 + 데이터 행 / 헤더 열 + 데이터 열 — 컴포넌트는 hosts.length+1 / colCount+1을 보고함.
    expect(grid).toHaveAttribute('aria-rowcount', String(HOSTS.length + 1));
    expect(grid).toHaveAttribute('aria-colcount', String(4 + 1));
  });

  it('OPEN 셀은 gridcell role + aria-label에 호스트/시간/state 포함', () => {
    const slotsByHost = buildSlotsByHost();
    render(
      <CalendarGrid
        hosts={HOSTS}
        slotsByHost={slotsByHost}
        currentUserId={1}
        onCellActivate={() => undefined}
      />,
    );
    const cells = screen.getAllByRole('gridcell');
    expect(cells.length).toBeGreaterThan(0);
    const firstLabel = cells[0]!.getAttribute('aria-label') ?? '';
    expect(firstLabel).toContain('강의실 A-101');
    expect(firstLabel).toMatch(/\d{2}:\d{2}~\d{2}:\d{2}/);
    expect(firstLabel).toContain('예약 가능');
  });

  it('키보드 ArrowRight로 다음 셀에 tabindex=0이 부여', async () => {
    const user = userEvent.setup();
    const slotsByHost = buildSlotsByHost();
    render(
      <CalendarGrid
        hosts={HOSTS}
        slotsByHost={slotsByHost}
        currentUserId={1}
        onCellActivate={() => undefined}
      />,
    );
    const first = screen.getByRole('gridcell', { name: /강의실 A-101 09:00/ });
    first.focus();
    expect(first).toHaveAttribute('tabindex', '0');
    await user.keyboard('{ArrowRight}');
    const next = screen.getByRole('gridcell', { name: /강의실 A-101 09:30/ });
    expect(next).toHaveAttribute('tabindex', '0');
  });

  it('OPEN 셀에서 Enter → onCellActivate 호출', async () => {
    const user = userEvent.setup();
    const slotsByHost = buildSlotsByHost();
    const onActivate = vi.fn<(c: CalendarCell) => void>();
    render(
      <CalendarGrid
        hosts={HOSTS}
        slotsByHost={slotsByHost}
        currentUserId={1}
        onCellActivate={onActivate}
      />,
    );
    const cell = screen.getByRole('gridcell', { name: /강의실 A-101 09:00/ });
    cell.focus();
    await user.keyboard('{Enter}');
    expect(onActivate).toHaveBeenCalledTimes(1);
    expect(onActivate.mock.calls[0]?.[0].host.id).toBe(1);
  });

  it('호스트 행 헤더에 status 배지가 표시된다', () => {
    render(
      <CalendarGrid
        hosts={HOSTS}
        slotsByHost={buildSlotsByHost()}
        currentUserId={1}
        onCellActivate={() => undefined}
      />,
    );
    expect(screen.getByText('대기 중')).toBeInTheDocument();
    expect(screen.getByText('사용 중')).toBeInTheDocument();
  });

  it('OCCUPIED(타인) 셀은 disabled — 클릭해도 콜백 미호출', async () => {
    const user = userEvent.setup();
    const slotsByHost = buildSlotsByHost([1]); // 두 번째 슬롯 점유
    const onActivate = vi.fn<(c: CalendarCell) => void>();
    render(
      <CalendarGrid
        hosts={HOSTS}
        slotsByHost={slotsByHost}
        currentUserId={1}
        onCellActivate={onActivate}
      />,
    );
    const occupied = screen.getByRole('gridcell', { name: /강의실 A-101 09:30.*다른 사용자/ });
    expect(occupied).toBeDisabled();
    await user.click(occupied);
    expect(onActivate).not.toHaveBeenCalled();
  });
});
