import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import { AUTH_UNAUTHENTICATED_EVENT } from '@/api/client';

function emitUnauthenticatedIfNeeded(error: unknown): void {
  if (error instanceof AxiosError && error.response?.status === 401) {
    if (typeof window === 'undefined') return;
    // axios interceptor가 이미 dispatch하지만 fallback. 중복은 navigate idempotent.
    window.dispatchEvent(new CustomEvent(AUTH_UNAUTHENTICATED_EVENT, { detail: {} }));
  }
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: (failureCount, error) => {
          if (error instanceof AxiosError && error.response?.status === 401) return false;
          return failureCount < 2;
        },
        refetchOnWindowFocus: false,
        staleTime: 30_000,
      },
      mutations: {
        retry: false,
      },
    },
    queryCache: new QueryCache({
      onError: emitUnauthenticatedIfNeeded,
    }),
    mutationCache: new MutationCache({
      onError: emitUnauthenticatedIfNeeded,
    }),
  });
}
