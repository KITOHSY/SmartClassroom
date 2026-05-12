import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { RequireAuth } from './RequireAuth';
import { server } from '@/test/msw/server';
import { setMockSession, TEST_USER } from '@/test/msw/handlers';

function renderWithRouter(initial: string = '/calendar') {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initial]}>
        <Routes>
          <Route element={<RequireAuth />}>
            <Route path="/calendar" element={<div data-testid="protected">PROTECTED</div>} />
          </Route>
          <Route path="/login" element={<div data-testid="login">LOGIN</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('<RequireAuth />', () => {
  it('로딩 중에는 spinner를 표시', () => {
    // /auth/me가 응답하기 전 초기 상태 — react-query는 isLoading=true.
    server.use(
      http.get('/api/v1/auth/me', async () => {
        await new Promise((r) => setTimeout(r, 100));
        return HttpResponse.json(TEST_USER, { status: 200 });
      }),
    );
    renderWithRouter();
    expect(screen.getByRole('status')).toHaveTextContent(/세션 확인 중/);
  });

  it('401이면 /login으로 리다이렉트', async () => {
    setMockSession(null); // 기본 401
    renderWithRouter('/calendar');
    await waitFor(() => {
      expect(screen.getByTestId('login')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('protected')).not.toBeInTheDocument();
  });

  it('200이면 children을 렌더', async () => {
    setMockSession(TEST_USER);
    renderWithRouter('/calendar');
    await waitFor(() => {
      expect(screen.getByTestId('protected')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('login')).not.toBeInTheDocument();
  });
});
