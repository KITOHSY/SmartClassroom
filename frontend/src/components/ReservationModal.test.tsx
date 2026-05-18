import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement, ReactNode } from 'react';
import { ReservationModal } from './ReservationModal';
import { ToastProvider } from './Toast';
import { server } from '@/test/msw/server';
import {
  reservationConflictHandler,
  reservationInvalidWindowHandler,
  reservationQuotaConcurrentHandler,
  reservationQuotaDailyHandler,
} from '@/test/msw/handlers';
import type { HostRead } from '@/api/hosts';

const HOST: HostRead = {
  id: 1,
  hostname: 'pc-101',
  display_name: '강의실 A-101',
  location: null,
  status: 'ACTIVE',
  sunshine_port: 47989,
  ip_address: '10.0.0.1',
};

const STARTS_AT = '2026-05-13T00:00:00.000Z'; // KST 09:00

function createWrapper(qc: QueryClient): (props: { children: ReactNode }) => ReactElement {
  return function Wrapper({ children }: { children: ReactNode }): ReactElement {
    return (
      <QueryClientProvider client={qc}>
        <ToastProvider>{children}</ToastProvider>
      </QueryClientProvider>
    );
  };
}

function renderModal(opts: {
  onClose?: () => void;
  onCreated?: () => void | Promise<void>;
} = {}) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  const Wrapper = createWrapper(qc);
  const onClose = opts.onClose ?? vi.fn();
  const onCreated = opts.onCreated ?? vi.fn();
  const utils = render(
    <Wrapper>
      <ReservationModal
        open
        host={HOST}
        startsAt={STARTS_AT}
        onClose={onClose}
        onCreated={onCreated}
      />
    </Wrapper>,
  );
  return { ...utils, onClose, onCreated, queryClient: qc };
}

describe('<ReservationModal />', () => {
  it('201 success → onCreated + onClose 호출', async () => {
    const user = userEvent.setup();
    const { onClose, onCreated } = renderModal();
    await user.click(screen.getByRole('button', { name: '예약' }));
    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('422 invalid_reservation_window → 모달 inline 메시지 표시 (onClose 미호출)', async () => {
    server.use(reservationInvalidWindowHandler);
    const user = userEvent.setup();
    const { onClose } = renderModal();
    await user.click(screen.getByRole('button', { name: '예약' }));
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/시작 시간은 현재 이후/);
    });
    expect(onClose).not.toHaveBeenCalled();
  });

  it('409 conflict → toast 노출 + onClose 호출', async () => {
    server.use(reservationConflictHandler);
    const user = userEvent.setup();
    const { onClose } = renderModal();
    await user.click(screen.getByRole('button', { name: '예약' }));
    await waitFor(() => {
      // ToastProvider가 .text를 라이브 영역에 노출
      expect(screen.getByText(/이미 예약된 슬롯/)).toBeInTheDocument();
    });
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('429 quota concurrent → 활성 예약 분기 메시지가 toast로 표시', async () => {
    server.use(reservationQuotaConcurrentHandler);
    const user = userEvent.setup();
    const { onClose } = renderModal();
    await user.click(screen.getByRole('button', { name: '예약' }));
    await waitFor(() => {
      expect(screen.getByText(/현재 활성 예약 2건/)).toBeInTheDocument();
    });
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('429 quota daily_minutes → 누적 분 분기 메시지가 toast로 표시', async () => {
    server.use(reservationQuotaDailyHandler);
    const user = userEvent.setup();
    renderModal();
    await user.click(screen.getByRole('button', { name: '예약' }));
    await waitFor(() => {
      expect(screen.getByText(/오늘 누적 240분/)).toBeInTheDocument();
    });
  });

  it('duration select에 240분 초과 옵션 없음 (클라이언트 차단)', () => {
    renderModal();
    const select = screen.getByLabelText('예약 길이') as HTMLSelectElement;
    const values = Array.from(select.options).map((o) => Number(o.value));
    expect(Math.max(...values)).toBe(240);
    expect(values.some((v) => v > 240)).toBe(false);
    // 30분 그리드만 — 30, 60, ..., 240 = 8개.
    expect(values.length).toBe(8);
  });
});
