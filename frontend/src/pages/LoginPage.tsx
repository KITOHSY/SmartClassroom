import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent, type ReactElement } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { z } from 'zod';
import { mockLogin, type MockLoginPayload } from '@/api/auth';
import { ME_QUERY_KEY } from '@/lib/auth';
import { parseApiError } from '@/lib/errors';

const loginSchema = z.object({
  external_id: z.string().min(1, 'external_id를 입력하세요').max(64),
  display_name: z.string().min(1, 'display_name을 입력하세요').max(64),
  role: z.enum(['user', 'admin']),
});

interface LocationState {
  from?: string;
}

export function LoginPage(): ReactElement {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const [externalId, setExternalId] = useState('202012345');
  const [displayName, setDisplayName] = useState('홍길동');
  const [role, setRole] = useState<'user' | 'admin'>('user');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const mutation = useMutation({
    mutationFn: (payload: MockLoginPayload) => mockLogin(payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY });
      const from = (location.state as LocationState | null)?.from ?? '/';
      navigate(from, { replace: true });
    },
  });

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    setFieldErrors({});
    const parsed = loginSchema.safeParse({
      external_id: externalId.trim(),
      display_name: displayName.trim(),
      role,
    });
    if (!parsed.success) {
      const errs: Record<string, string> = {};
      for (const issue of parsed.error.issues) {
        const key = issue.path[0];
        if (typeof key === 'string') errs[key] = issue.message;
      }
      setFieldErrors(errs);
      return;
    }
    mutation.mutate(parsed.data);
  }

  const apiError = mutation.isError ? parseApiError(mutation.error) : null;

  // TODO(T04b): VITE_AUTH_PROVIDER === 'cnu_sso' 인 경우 본 폼을 SSO 리다이렉트 버튼으로 교체.
  // window.location.assign('/api/v1/auth/cnu-sso/login') 정도로 진입.
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm space-y-4 rounded-lg border border-slate-200 bg-white p-6 shadow-sm"
        aria-labelledby="login-title"
      >
        <h1 id="login-title" className="text-xl font-semibold text-slate-900">
          Mock 로그인
        </h1>
        <p className="text-sm text-slate-500">
          개발/스테이징 한정. 운영에서는 CNU SSO로 자동 진입합니다.
        </p>

        <div className="space-y-1">
          <label htmlFor="external_id" className="text-sm font-medium text-slate-700">
            external_id
          </label>
          <input
            id="external_id"
            name="external_id"
            type="text"
            autoComplete="username"
            required
            value={externalId}
            onChange={(e) => setExternalId(e.target.value)}
            className="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none"
            aria-invalid={Boolean(fieldErrors.external_id)}
            aria-describedby={fieldErrors.external_id ? 'external_id-error' : undefined}
          />
          {fieldErrors.external_id ? (
            <p id="external_id-error" className="text-xs text-rose-600">
              {fieldErrors.external_id}
            </p>
          ) : null}
        </div>

        <div className="space-y-1">
          <label htmlFor="display_name" className="text-sm font-medium text-slate-700">
            display_name
          </label>
          <input
            id="display_name"
            name="display_name"
            type="text"
            required
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none"
            aria-invalid={Boolean(fieldErrors.display_name)}
            aria-describedby={fieldErrors.display_name ? 'display_name-error' : undefined}
          />
          {fieldErrors.display_name ? (
            <p id="display_name-error" className="text-xs text-rose-600">
              {fieldErrors.display_name}
            </p>
          ) : null}
        </div>

        <div className="space-y-1">
          <label htmlFor="role" className="text-sm font-medium text-slate-700">
            role
          </label>
          <select
            id="role"
            name="role"
            value={role}
            onChange={(e) => setRole(e.target.value as 'user' | 'admin')}
            className="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-brand focus:outline-none"
          >
            <option value="user">user</option>
            <option value="admin">admin</option>
          </select>
        </div>

        {apiError ? (
          <div role="alert" className="rounded border border-rose-300 bg-rose-50 p-3 text-sm text-rose-700">
            {apiError.message}
          </div>
        ) : null}

        <button
          type="submit"
          disabled={mutation.isPending}
          className="w-full rounded bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
        >
          {mutation.isPending ? '로그인 중…' : '로그인'}
        </button>
      </form>
    </div>
  );
}
