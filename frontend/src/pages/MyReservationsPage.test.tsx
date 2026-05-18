import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { MyReservationsPage } from './MyReservationsPage';
import { ToastProvider } from '@/components/Toast';
import { server } from '@/test/msw/server';
import {
  buildReservation,
  connectTooEarlyHandler,
  setMockSession,
  TEST_USER,
} from '@/test/msw/handlers';

const { launchMoonlightMock } = vi.hoisted(() => ({ launchMoonlightMock: vi.fn() }));

vi.mock('@/lib/moonlight', () => ({
  buildMoonlightUrl: vi.fn(() => 'moonlight://connect?token=x'),
  launchMoonlight: launchMoonlightMock,
  detectOS: () => 'windows' as const,
}));

// 진행 가능한(미래 종료) CONFIRMED 예약 — 기본 핸들러의 과거 예약은 [접속] 버튼을 띄우지 않는다.
const FUTURE_RESERVATION = buildReservation({
  id: 100,
  host_id: 1,
  starts_at: '2099-01-01T00:00:00+00:00',
  ends_at: '2099-01-01T02:30:00+00:00',
  status: 'CONFIRMED',
});

function useFutureReservation(): void {
  server.use(
    http.get('/api/v1/reservations', () =>
      HttpResponse.json([FUTURE_RESERVATION], { status: 200 }),
    ),
  );
}

function renderPage(): void {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter>
          <MyReservationsPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe('<MyReservationsPage /> 접속', () => {
  beforeEach(() => {
    setMockSession(TEST_USER);
    launchMoonlightMock.mockReset();
    launchMoonlightMock.mockResolvedValue(true);
  });

  it('진행 가능한 CONFIRMED 예약에 [접속] 버튼이 보이고, 클릭 시 moonlight 실행', async () => {
    useFutureReservation();
    const user = userEvent.setup();
    renderPage();
    const connectBtn = await screen.findByRole('button', { name: '접속' });
    await user.click(connectBtn);
    await waitFor(() => expect(launchMoonlightMock).toHaveBeenCalledTimes(1));
  });

  it('422 too_early → 친화 메시지 toast', async () => {
    useFutureReservation();
    server.use(connectTooEarlyHandler);
    const user = userEvent.setup();
    renderPage();
    const connectBtn = await screen.findByRole('button', { name: '접속' });
    await user.click(connectBtn);
    expect(
      await screen.findByText('예약 시작 직전부터 접속할 수 있어요'),
    ).toBeInTheDocument();
    expect(launchMoonlightMock).not.toHaveBeenCalled();
  });

  it('moonlight 핸들러 미등록 추정 시 설치 가이드 노출', async () => {
    useFutureReservation();
    launchMoonlightMock.mockResolvedValue(false);
    const user = userEvent.setup();
    renderPage();
    const connectBtn = await screen.findByRole('button', { name: '접속' });
    await user.click(connectBtn);
    expect(await screen.findByText('Moonlight 앱이 필요해요')).toBeInTheDocument();
  });
});
