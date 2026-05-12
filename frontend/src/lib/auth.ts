import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import { getMe } from '@/api/auth';

export type UserRole = 'user' | 'admin';

export interface User {
  id: number;
  external_id: string;
  display_name: string;
  email: string | null;
  role: UserRole;
  provider: string;
}

export const ME_QUERY_KEY = ['me'] as const;

export function useMe(): UseQueryResult<User, AxiosError> {
  return useQuery<User, AxiosError>({
    queryKey: ME_QUERY_KEY,
    queryFn: getMe,
    retry: (failureCount, error) => {
      // 401은 재시도하지 않음 — RequireAuth가 redirect 처리.
      if (error instanceof AxiosError && error.response?.status === 401) return false;
      return failureCount < 2;
    },
    staleTime: 60_000,
  });
}
