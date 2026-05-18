import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { CalendarGrid } from '@/components/CalendarGrid';
import { ReservationModal } from '@/components/ReservationModal';
import { ToastProvider } from '@/components/Toast';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { HostRead } from '@/api/hosts';
import type { CalendarSlot } from '@/api/reservations';

/**
 * 가벼운 접근성 스모크 — `axe-core`를 devDep으로 추가하지 않기로 결정했으므로
 * `@testing-library/jest-dom`의 기본 a11y matcher (toHaveAccessibleName, toHaveRole)로
 * 핵심 명명/역할만 검증한다. 본격 axe 스캔은 추후 `@axe-core/react`(이미 devDep)를
 * dev 런타임에서 활용하거나 별 도 태스크로 도입한다.
 */

const HOST: HostRead = {
  id: 1,
  hostname: 'pc-101',
  display_name: '강의실 A-101',
  location: null,
  status: 'ACTIVE',
  sunshine_port: 47989,
  ip_address: '10.0.0.1',
};

function makeSlots(): Map<number, CalendarSlot[]> {
  const map = new Map<number, CalendarSlot[]>();
  const base = new Date('2026-05-13T00:00:00+09:00').getTime();
  map.set(1, [
    {
      starts_at: new Date(base).toISOString(),
      ends_at: new Date(base + 30 * 60_000).toISOString(),
      host_id: 1,
      reservation_id: null,
      user_id: null,
      status: 'OPEN',
    },
  ]);
  return map;
}

describe('a11y smoke', () => {
  it('CalendarGrid: grid는 accessible name을 가진다', () => {
    render(
      <CalendarGrid
        hosts={[HOST]}
        slotsByHost={makeSlots()}
        currentUserId={1}
        onCellActivate={() => undefined}
      />,
    );
    const grid = screen.getByRole('grid');
    expect(grid).toHaveAccessibleName('예약 캘린더');
  });

  it('CalendarGrid: 모든 gridcell은 비어 있지 않은 aria-label을 가진다', () => {
    render(
      <CalendarGrid
        hosts={[HOST]}
        slotsByHost={makeSlots()}
        currentUserId={1}
        onCellActivate={() => undefined}
      />,
    );
    const cells = screen.getAllByRole('gridcell');
    for (const cell of cells) {
      expect(cell).toHaveAccessibleName();
    }
  });

  it('ReservationModal: dialog는 aria-modal과 labelledby 제목을 가진다', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ToastProvider>
          <ReservationModal
            open
            host={HOST}
            startsAt="2026-05-13T00:00:00.000Z"
            onClose={() => undefined}
            onCreated={() => undefined}
          />
        </ToastProvider>
      </QueryClientProvider>,
    );
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAccessibleName('예약 생성');
    // 닫기 버튼은 명명되어 있어야 한다
    const close = within(dialog).getByRole('button', { name: '모달 닫기' });
    expect(close).toBeInTheDocument();
  });
});
