import { useEffect, type ReactElement } from 'react';
import { RouterProvider } from 'react-router-dom';
import { router } from '@/routes';
import { AUTH_UNAUTHENTICATED_EVENT } from '@/api/client';

export function App(): ReactElement {
  useEffect(() => {
    // 401 → /login 라우팅. axios interceptor / queryCache가 발행하는 커스텀 이벤트를
    // React Router navigate로 변환 (interceptor는 Hook 컨텍스트 밖이라 직접 호출 불가).
    function handler(): void {
      const path = window.location.pathname;
      if (path === '/login') return;
      void router.navigate('/login', { replace: true });
    }
    window.addEventListener(AUTH_UNAUTHENTICATED_EVENT, handler);
    return () => window.removeEventListener(AUTH_UNAUTHENTICATED_EVENT, handler);
  }, []);

  return <RouterProvider router={router} />;
}
