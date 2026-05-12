import { type ReactElement } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useMe } from '@/lib/auth';

export function RequireAuth(): ReactElement {
  const { data, isLoading, isError, error } = useMe();
  const location = useLocation();

  if (isLoading) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="flex min-h-screen items-center justify-center text-slate-500"
      >
        세션 확인 중…
      </div>
    );
  }

  const unauthorized =
    (isError && (error as { response?: { status?: number } }).response?.status === 401) ||
    data === null ||
    data === undefined;

  if (unauthorized) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }

  return <Outlet />;
}
