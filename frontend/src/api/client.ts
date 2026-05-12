import axios, { AxiosError, type AxiosInstance } from 'axios';

export const AUTH_UNAUTHENTICATED_EVENT = 'auth:unauthenticated';

export interface UnauthenticatedDetail {
  loginUrl?: string;
}

function dispatchUnauthenticated(loginUrl?: string): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(
    new CustomEvent<UnauthenticatedDetail>(AUTH_UNAUTHENTICATED_EVENT, {
      detail: loginUrl ? { loginUrl } : {},
    }),
  );
}

function isAbsoluteUrl(value: unknown): value is string {
  return typeof value === 'string' && /^https?:\/\//i.test(value);
}

export const apiClient: AxiosInstance = axios.create({
  baseURL: '/api/v1',
  withCredentials: true,
  headers: {
    Accept: 'application/json',
  },
});

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ detail?: { login_url?: string } }>) => {
    if (error.response?.status === 401) {
      const loginUrl = error.response.data?.detail?.login_url;
      // T04b: 외부 SSO 시나리오 — 백엔드가 절대 URL을 주면 그쪽으로 강제 이동.
      if (isAbsoluteUrl(loginUrl) && typeof window !== 'undefined') {
        window.location.assign(loginUrl);
      } else {
        dispatchUnauthenticated(typeof loginUrl === 'string' ? loginUrl : undefined);
      }
    }
    return Promise.reject(error);
  },
);
