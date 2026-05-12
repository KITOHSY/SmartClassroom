import '@testing-library/jest-dom/vitest';
import { afterAll, afterEach, beforeAll, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import { server } from './msw/server';
import { setMockSession } from './msw/handlers';

// Asia/Seoul TZ 강제 — date-fns-tz 출력과 toIsoWithOffset의 +09:00 검증을 안정화.
// vitest는 워커 프로세스를 띄우기 전에 process.env.TZ를 읽어야 효과가 있지만,
// jsdom의 Intl/Date는 모듈 로드 시 system TZ를 결정하므로 setupFiles에서 설정해도
// 대부분의 케이스(특히 date-fns-tz는 IANA DB를 직접 참조)에는 충분하다.
process.env.TZ = 'Asia/Seoul';

// Tailwind/headless 라이브러리가 useMediaQuery를 검사하면 jsdom이 폭발 — 안전한 stub.
if (typeof window !== 'undefined' && !window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(), // deprecated
      removeListener: vi.fn(), // deprecated
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

// MSW 라이프사이클 — 모든 테스트가 공유.
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  server.resetHandlers();
  setMockSession(null);
  cleanup();
});
afterAll(() => server.close());
