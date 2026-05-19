import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CalendarGrid, type CalendarCell } from './CalendarGrid';
import type { HostRead } from '@/api/hosts';
import type { CalendarSlot } from '@/api/reservations';

/** 현재 시각을 첫 슬롯 안에 포함하는 연속 30분 슬롯 — 즉시 사용/부분 바 검증용. */
function makeNowSlots(hostId: number, count: number): CalendarSlot[] {
  const base = Date.now() - 15 * 60_000;
  return Array.from({ length: count }, (_, i) => {
    const startMs = base + i * 30 * 60_000;
    return {
      starts_at: new Date(startMs).toISOString(),
      ends_at: new Date(startMs + 30 * 60_000).toISOString(),
      host_id: hostId,
      reservation_id: null,
      user_id: null,
      status: 'OPEN' as const,
    };
  });
}

/** 23:00 KST부터 6칸 — 자정 경계(00:00)를 가로지른다. */
function makeMidnightSlots(hostId: number): CalendarSlot[] {
  const base = new Date('2026-05-13T23:00:00+09:00').getTime();
  return Array.from({ length: 6 }, (_, i) => {
    const startMs = base + i * 30 * 60_000;
    return {
      starts_at: new Date(startMs).toISOString(),
      ends_at: new Date(startMs + 30 * 60_000).toISOString(),
      host_id: hostId,
      reservation_id: null,
      user_id: null,
      status: 'OPEN' as const,
    };
  });
}

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

  it('오늘 뷰: instant 호스트 행에만 [즉시 사용] 버튼이 노출된다', () => {
    const slotsByHost = new Map<number, CalendarSlot[]>([
      [1, makeNowSlots(1, 4)],
      [2, makeNowSlots(2, 4)],
    ]);
    const until = new Date(Date.now() + 90 * 60_000).toISOString();
    render(
      <CalendarGrid
        hosts={HOSTS}
        slotsByHost={slotsByHost}
        currentUserId={1}
        onCellActivate={() => undefined}
        isToday
        instantByHost={new Map([[1, until]])}
        onInstantUse={() => undefined}
      />,
    );
    // instantByHost에 host 1만 → 버튼 1개.
    expect(screen.getAllByRole('button', { name: '즉시 사용' })).toHaveLength(1);
  });

  it('오늘 뷰: [즉시 사용] 호버 시에만 instant 호스트 셀에 부분 바가 나타난다', () => {
    const slotsByHost = new Map<number, CalendarSlot[]>([[1, makeNowSlots(1, 4)]]);
    const until = new Date(Date.now() + 90 * 60_000).toISOString();
    render(
      <CalendarGrid
        hosts={[HOSTS[0]!]}
        slotsByHost={slotsByHost}
        currentUserId={1}
        onCellActivate={() => undefined}
        isToday
        instantByHost={new Map([[1, until]])}
        onInstantUse={() => undefined}
      />,
    );
    const button = screen.getByRole('button', { name: '즉시 사용' });
    // 기본 상태 — 바 없음.
    expect(screen.queryByTestId('instant-window-bar')).not.toBeInTheDocument();
    // 버튼 호버 → 그 행 셀에 초록(preview) 부분 바 표시.
    fireEvent.mouseEnter(button);
    const bars = screen.getAllByTestId('instant-window-bar');
    expect(bars.length).toBeGreaterThan(0);
    expect(bars[0]).toHaveAttribute('data-kind', 'preview');
    // 호버 해제 → 다시 사라짐.
    fireEvent.mouseLeave(button);
    expect(screen.queryByTestId('instant-window-bar')).not.toBeInTheDocument();
  });

  it('즉시 사용 확정(confirmedInstants) 시 호버 없이도 파란 부분 바가 표시된다', () => {
    const until = new Date(Date.now() + 90 * 60_000).toISOString();
    render(
      <CalendarGrid
        hosts={[HOSTS[0]!]}
        slotsByHost={new Map([[1, makeNowSlots(1, 4)]])}
        currentUserId={1}
        onCellActivate={() => undefined}
        isToday
        confirmedInstants={[{ hostId: 1, untilIso: until }]}
      />,
    );
    // 호버 없이 즉시 — data-kind='confirmed' 바.
    const bars = screen.getAllByTestId('instant-window-bar');
    expect(bars.length).toBeGreaterThan(0);
    expect(bars[0]).toHaveAttribute('data-kind', 'confirmed');
  });

  it('confirmedInstants의 여러 호스트 행에 각각 파란 부분 바가 그려진다', () => {
    const until = new Date(Date.now() + 90 * 60_000).toISOString();
    render(
      <CalendarGrid
        hosts={HOSTS}
        slotsByHost={
          new Map([
            [1, makeNowSlots(1, 4)],
            [2, makeNowSlots(2, 4)],
          ])
        }
        currentUserId={1}
        onCellActivate={() => undefined}
        isToday
        confirmedInstants={[
          { hostId: 1, untilIso: until },
          { hostId: 2, untilIso: until },
        ]}
      />,
    );
    // 두 호스트 행(row 0·1) 모두에 confirmed 바가 존재해야 한다.
    const rows = new Set(
      screen
        .getAllByTestId('instant-window-bar')
        .map((b) => b.closest('[data-row]')?.getAttribute('data-row')),
    );
    expect(rows.has('0')).toBe(true);
    expect(rows.has('1')).toBe(true);
  });

  it('드래그로 2칸 선택 → onCellActivate에 spanMinutes=60', () => {
    const onActivate = vi.fn<(c: CalendarCell) => void>();
    render(
      <CalendarGrid
        hosts={HOSTS}
        slotsByHost={buildSlotsByHost()}
        currentUserId={1}
        onCellActivate={onActivate}
      />,
    );
    const c0 = screen.getByRole('gridcell', { name: /강의실 A-101 09:00/ });
    const c1 = screen.getByRole('gridcell', { name: /강의실 A-101 09:30/ });
    fireEvent.mouseDown(c0);
    fireEvent.mouseEnter(c1);
    fireEvent.mouseUp(window);
    expect(onActivate).toHaveBeenCalledTimes(1);
    expect(onActivate.mock.calls[0]?.[0].spanMinutes).toBe(60);
  });

  it('자정을 넘는 드래그도 spanMinutes가 경계 너머로 누적된다', () => {
    const onActivate = vi.fn<(c: CalendarCell) => void>();
    render(
      <CalendarGrid
        hosts={[HOSTS[0]!]}
        slotsByHost={new Map([[1, makeMidnightSlots(1)]])}
        currentUserId={1}
        onCellActivate={onActivate}
      />,
    );
    // 23:00(col0)에서 01:00(col4)까지 5칸 드래그 — 자정(col2)을 가로지른다.
    const start = screen.getByRole('gridcell', { name: /강의실 A-101 23:00/ });
    const end = screen.getByRole('gridcell', { name: /강의실 A-101 01:00/ });
    fireEvent.mouseDown(start);
    fireEvent.mouseEnter(end);
    fireEvent.mouseUp(window);
    expect(onActivate.mock.calls[0]?.[0].spanMinutes).toBe(150);
  });

  it('8칸(4시간)을 넘는 드래그는 spanMinutes가 240으로 캡된다', () => {
    const onActivate = vi.fn<(c: CalendarCell) => void>();
    render(
      <CalendarGrid
        hosts={[HOSTS[0]!]}
        slotsByHost={new Map([[1, makeSlots(1, 12)]])}
        currentUserId={1}
        onCellActivate={onActivate}
      />,
    );
    const cells = screen.getAllByRole('gridcell'); // 단일 행 12칸, data-col 0..11 순
    fireEvent.mouseDown(cells[0]!);
    fireEvent.mouseEnter(cells[11]!);
    fireEvent.mouseUp(window);
    expect(onActivate.mock.calls[0]?.[0].spanMinutes).toBe(240);
  });

  it('드래그 강조는 8칸까지만 — col 7은 파랑, col 8부터는 미강조', () => {
    render(
      <CalendarGrid
        hosts={[HOSTS[0]!]}
        slotsByHost={new Map([[1, makeSlots(1, 12)]])}
        currentUserId={1}
        onCellActivate={() => undefined}
      />,
    );
    const cells = screen.getAllByRole('gridcell');
    fireEvent.mouseDown(cells[0]!);
    fireEvent.mouseEnter(cells[11]!);
    // mouseup 전 — 강조 상태. 앵커(col0)부터 8칸(col0~7)까지만 bg-blue-200.
    // 드래그 셀은 bg-slate-100과 함께 붙으면 안 됨(클래스 충돌 → 회색이 이김).
    expect(cells[7]!.className).toContain('bg-blue-200');
    expect(cells[7]!.className).not.toContain('bg-slate-100');
    expect(cells[8]!.className).not.toContain('bg-blue-200');
    expect(cells[8]!.className).toContain('bg-slate-100');
    fireEvent.mouseUp(window); // 정리
  });

  it('selectedRange가 있으면 모달 대상 셀이 파랑으로 유지된다', () => {
    const slots = makeSlots(1, 6);
    render(
      <CalendarGrid
        hosts={[HOSTS[0]!]}
        slotsByHost={new Map([[1, slots]])}
        currentUserId={1}
        onCellActivate={() => undefined}
        selectedRange={{ hostId: 1, startsAt: slots[0]!.starts_at, minutes: 90 }}
      />,
    );
    const cells = screen.getAllByRole('gridcell');
    // 90분 = 3칸(col 0~2) 강조, col 3부터는 회색.
    expect(cells[0]!.className).toContain('bg-blue-200');
    expect(cells[2]!.className).toContain('bg-blue-200');
    expect(cells[2]!.className).not.toContain('bg-slate-100');
    expect(cells[3]!.className).not.toContain('bg-blue-200');
    expect(cells[3]!.className).toContain('bg-slate-100');
  });

  it('과거 시각 셀(nowColIndex 이하)을 mousedown하면 onBlockedAttempt("past")·드래그 미시작', () => {
    const onActivate = vi.fn<(c: CalendarCell) => void>();
    const onBlocked = vi.fn();
    render(
      <CalendarGrid
        hosts={[HOSTS[0]!]}
        slotsByHost={new Map([[1, makeSlots(1, 8)]])}
        currentUserId={1}
        onCellActivate={onActivate}
        isToday
        nowColIndex={3}
        onBlockedAttempt={onBlocked}
      />,
    );
    const cells = screen.getAllByRole('gridcell');
    fireEvent.mouseDown(cells[2]!); // col 2 <= nowColIndex 3 → 과거
    fireEvent.mouseUp(window);
    expect(onBlocked).toHaveBeenCalledWith('past');
    expect(onActivate).not.toHaveBeenCalled();
  });

  it('점검 중·오프라인 호스트 행 셀을 mousedown하면 onBlockedAttempt("host-unreservable")', () => {
    const onActivate = vi.fn<(c: CalendarCell) => void>();
    const onBlocked = vi.fn();
    const degradedHost: HostRead = { ...HOSTS[0]!, status: 'DEGRADED' };
    render(
      <CalendarGrid
        hosts={[degradedHost]}
        slotsByHost={new Map([[degradedHost.id, makeSlots(degradedHost.id, 6)]])}
        currentUserId={1}
        onCellActivate={onActivate}
        onBlockedAttempt={onBlocked}
      />,
    );
    fireEvent.mouseDown(screen.getAllByRole('gridcell')[0]!);
    fireEvent.mouseUp(window);
    expect(onBlocked).toHaveBeenCalledWith('host-unreservable');
    expect(onActivate).not.toHaveBeenCalled();
  });

  it('접속 정보(IP) 없는 호스트 행 셀을 mousedown하면 onBlockedAttempt("host-no-ip")', () => {
    const onActivate = vi.fn<(c: CalendarCell) => void>();
    const onBlocked = vi.fn();
    const noIpHost: HostRead = { ...HOSTS[0]!, ip_address: null };
    render(
      <CalendarGrid
        hosts={[noIpHost]}
        slotsByHost={new Map([[noIpHost.id, makeSlots(noIpHost.id, 6)]])}
        currentUserId={1}
        onCellActivate={onActivate}
        onBlockedAttempt={onBlocked}
      />,
    );
    fireEvent.mouseDown(screen.getAllByRole('gridcell')[0]!);
    fireEvent.mouseUp(window);
    expect(onBlocked).toHaveBeenCalledWith('host-no-ip');
    expect(onActivate).not.toHaveBeenCalled();
  });

  it('미래 셀에서 과거로 드래그하면 now 경계(minReservableCol)에서 클램프된다', () => {
    const slots = makeSlots(1, 8);
    const onActivate = vi.fn<(c: CalendarCell) => void>();
    render(
      <CalendarGrid
        hosts={[HOSTS[0]!]}
        slotsByHost={new Map([[1, slots]])}
        currentUserId={1}
        onCellActivate={onActivate}
        isToday
        nowColIndex={3}
        onBlockedAttempt={() => undefined}
      />,
    );
    const cells = screen.getAllByRole('gridcell');
    // 미래 col6에서 시작 → 과거 col1로 드래그. minReservableCol=4에서 잘려 col4~6(=90분).
    fireEvent.mouseDown(cells[6]!);
    fireEvent.mouseEnter(cells[1]!);
    fireEvent.mouseUp(window);
    expect(onActivate.mock.calls[0]?.[0].spanMinutes).toBe(90);
    expect(onActivate.mock.calls[0]?.[0].slot.starts_at).toBe(slots[4]!.starts_at);
  });

  it('오늘 뷰 진입 시 now 셀의 현재 시각 위치로 스크롤한다 (슬롯 시작 아님)', () => {
    const slots = makeNowSlots(1, 6); // slot 0이 현재 시각을 포함
    const { container, rerender } = render(
      <CalendarGrid
        hosts={[HOSTS[0]!]}
        slotsByHost={new Map([[1, slots]])}
        currentUserId={1}
        onCellActivate={() => undefined}
        isToday
        nowColIndex={null}
      />,
    );
    const scroller = container.querySelector('.overflow-x-auto') as HTMLElement;
    const setSpy = vi.fn<(v: number) => void>();
    Object.defineProperty(scroller, 'scrollLeft', {
      configurable: true,
      get: () => 0,
      set: setSpy,
    });
    rerender(
      <CalendarGrid
        hosts={[HOSTS[0]!]}
        slotsByHost={new Map([[1, slots]])}
        currentUserId={1}
        onCellActivate={() => undefined}
        isToday
        nowColIndex={0}
      />,
    );
    expect(setSpy).toHaveBeenCalledTimes(1);
    // 슬롯 시작(0)이 아니라 슬롯 안 현재 시각 비율만큼 — (0, 44) 범위.
    const scrolledTo = setSpy.mock.calls[0]?.[0];
    expect(scrolledTo).toBeGreaterThan(0);
    expect(scrolledTo).toBeLessThan(44);
  });

  it('다른 날짜(비-오늘) 진입 시 00:00(scrollLeft 0)으로 스크롤한다', () => {
    const { container, rerender } = render(
      <CalendarGrid
        hosts={HOSTS}
        slotsByHost={buildSlotsByHost()}
        currentUserId={1}
        onCellActivate={() => undefined}
        isToday
        nowColIndex={null}
      />,
    );
    const scroller = container.querySelector('.overflow-x-auto') as HTMLElement;
    const setSpy = vi.fn();
    Object.defineProperty(scroller, 'scrollLeft', {
      configurable: true,
      get: () => 0,
      set: setSpy,
    });
    // 비-오늘 날짜로 전환 → 00:00(맨 왼쪽)으로 스크롤.
    rerender(
      <CalendarGrid
        hosts={HOSTS}
        slotsByHost={buildSlotsByHost()}
        currentUserId={1}
        onCellActivate={() => undefined}
        isToday={false}
        nowColIndex={null}
      />,
    );
    expect(setSpy).toHaveBeenCalledWith(0);
  });
});
