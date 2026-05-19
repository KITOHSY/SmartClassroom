import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { CalendarPage } from './CalendarPage';
import { ToastProvider } from '@/components/Toast';
import { setMockSession, TEST_USER } from '@/test/msw/handlers';
import { addDays, formatDateLabel } from '@/lib/time';

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
          <CalendarPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe('<CalendarPage /> 즉시 사용 통합 (T21)', () => {
  beforeEach(() => {
    setMockSession(TEST_USER);
    launchMoonlightMock.mockReset();
    launchMoonlightMock.mockResolvedValue(true);
    sessionStorage.clear(); // confirmedInstant 격리
    // jsdom은 scrollIntoView를 no-op으로만 두므로 스텁 — 자동 스크롤이 호출.
    Element.prototype.scrollIntoView = vi.fn();
  });

  it('오늘 뷰에서 IDLE 호스트 행에 [즉시 사용] 버튼이 노출된다', async () => {
    renderPage();
    const buttons = await screen.findAllByRole('button', { name: '즉시 사용' });
    expect(buttons.length).toBeGreaterThan(0);
  });

  it('다른 날짜를 선택하면 [즉시 사용] UI가 사라진다', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findAllByRole('button', { name: '즉시 사용' });
    const tomorrow = formatDateLabel(addDays(new Date(), 1));
    await user.selectOptions(screen.getByRole('combobox', { name: '날짜' }), tomorrow);
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: '즉시 사용' })).not.toBeInTheDocument(),
    );
  });

  it('[즉시 사용] 클릭 → instant 예약 후 moonlight 실행', async () => {
    const user = userEvent.setup();
    renderPage();
    const buttons = await screen.findAllByRole('button', { name: '즉시 사용' });
    const enabled = buttons.find((b) => !b.hasAttribute('disabled'));
    if (!enabled) throw new Error('활성 [즉시 사용] 버튼을 찾을 수 없음');
    await user.click(enabled);
    await waitFor(() => expect(launchMoonlightMock).toHaveBeenCalledTimes(1));
  });
});
