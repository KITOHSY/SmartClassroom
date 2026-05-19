import { useMutation, useQueryClient } from '@tanstack/react-query';
import { type ReactElement } from 'react';
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';
import clsx from 'clsx';
import { logout } from '@/api/auth';
import { ME_QUERY_KEY, useMe } from '@/lib/auth';

export function Layout(): ReactElement {
  const { data: user } = useMe();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const logoutMutation = useMutation({
    mutationFn: logout,
    onSettled: async () => {
      await queryClient.resetQueries({ queryKey: ME_QUERY_KEY });
      navigate('/login', { replace: true });
    },
  });

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <Link to="/" className="text-lg font-semibold text-brand">
            SmartClassroom
          </Link>
          <nav aria-label="주요 메뉴" className="flex items-center gap-4 text-sm">
            <NavLink
              to="/"
              end
              className={({ isActive }) =>
                clsx(
                  'rounded px-2 py-1',
                  isActive ? 'bg-slate-100 font-medium text-slate-900' : 'text-slate-600',
                )
              }
            >
              캘린더
            </NavLink>
            <NavLink
              to="/reservations"
              className={({ isActive }) =>
                clsx(
                  'rounded px-2 py-1',
                  isActive ? 'bg-slate-100 font-medium text-slate-900' : 'text-slate-600',
                )
              }
            >
              내 예약
            </NavLink>
            {user ? (
              <>
                <span className="text-slate-700" data-testid="current-user">
                  {user.display_name}
                  <span className="ml-1 text-xs text-slate-400">({user.role})</span>
                </span>
                <button
                  type="button"
                  onClick={() => logoutMutation.mutate()}
                  disabled={logoutMutation.isPending}
                  className="rounded border border-slate-300 px-3 py-1 text-slate-700 hover:bg-slate-100 disabled:opacity-60"
                >
                  로그아웃
                </button>
              </>
            ) : null}
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
