import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { AvailableHostsPage } from './AvailableHostsPage';
import { ToastProvider } from '@/components/Toast';
import { server } from '@/test/msw/server';
import { instantHostNotAvailableHandler } from '@/test/msw/handlers';

const { launchMoonlightMock } = vi.hoisted(() => ({ launchMoonlightMock: vi.fn() }));

vi.mock('@/lib/moonlight', () => ({
  buildMoonlightUrl: vi.fn(() => 'moonlight://connect?token=x'),
  launchMoonlight: launchMoonlightMock,
  detectOS: () => 'windows' as const,
}));

function renderPage(): void {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter>
          <AvailableHostsPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

/** ip_address가 있어 활성 상태인 [즉시 사용] 버튼 (TEST_AVAILABLE_HOSTS의 첫 호스트). */
function getEnabledInstantButton(): HTMLElement {
  const enabled = screen
    .getAllByRole('button', { name: '즉시 사용' })
    .find((b) => !b.hasAttribute('disabled'));
  if (!enabled) throw new Error('활성 [즉시 사용] 버튼을 찾을 수 없음');
  return enabled;
}

describe('<AvailableHostsPage />', () => {
  beforeEach(() => {
    launchMoonlightMock.mockReset();
    launchMoonlightMock.mockResolvedValue(true);
  });

  it('가용 PC 목록을 렌더한다', async () => {
    renderPage();
    expect(await screen.findByText('강의실 A-101')).toBeInTheDocument();
    expect(screen.getByText('강의실 A-102')).toBeInTheDocument();
  });

  it('ip_address가 없는 호스트의 [즉시 사용] 버튼은 비활성', async () => {
    renderPage();
    await screen.findByText('강의실 A-101');
    const buttons = screen.getAllByRole('button', { name: '즉시 사용' });
    // TEST_AVAILABLE_HOSTS — idx0: ip 있음(활성), idx1: ip 없음(비활성).
    expect(buttons[0]).toBeEnabled();
    expect(buttons[1]).toBeDisabled();
  });

  it('[즉시 사용] 클릭 → instant 예약 후 moonlight 실행', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('강의실 A-101');
    await user.click(getEnabledInstantButton());
    await waitFor(() => expect(launchMoonlightMock).toHaveBeenCalledTimes(1));
  });

  it('moonlight 핸들러 미등록 추정 시 설치 가이드 노출', async () => {
    launchMoonlightMock.mockResolvedValue(false);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('강의실 A-101');
    await user.click(getEnabledInstantButton());
    expect(await screen.findByText('Moonlight 앱이 필요해요')).toBeInTheDocument();
  });

  it('available_until 기준 남은 사용 가능 시간을 표시한다', async () => {
    const until = new Date(Date.now() + 15 * 60_000).toISOString();
    server.use(
      http.get('/api/v1/hosts/available', () =>
        HttpResponse.json(
          [
            {
              id: 9,
              hostname: 'pc-9',
              display_name: '곧 예약 있는 PC',
              location: null,
              last_heartbeat_at: null,
              ip_address: '10.0.0.9',
              available_until: until,
            },
          ],
          { status: 200 },
        ),
      ),
    );
    renderPage();
    expect(await screen.findByText(/15분 사용 가능/)).toBeInTheDocument();
  });

  it('409 host_not_available → 에러 toast', async () => {
    server.use(instantHostNotAvailableHandler);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('강의실 A-101');
    await user.click(getEnabledInstantButton());
    expect(await screen.findByText('이 PC는 지금 즉시 사용할 수 없어요')).toBeInTheDocument();
    expect(launchMoonlightMock).not.toHaveBeenCalled();
  });
});
