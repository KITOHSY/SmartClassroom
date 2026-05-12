import { apiClient } from '@/api/client';
import type { User } from '@/lib/auth';

export interface MockLoginPayload {
  external_id: string;
  display_name: string;
  role: 'user' | 'admin';
}

export async function getMe(): Promise<User> {
  const { data } = await apiClient.get<User>('/auth/me');
  return data;
}

interface MockCallbackResponse {
  user: User;
  expires_at: string;
}

export async function mockLogin(payload: MockLoginPayload): Promise<User> {
  const { data } = await apiClient.post<MockCallbackResponse>('/auth/mock/callback', payload);
  return data.user;
}

export async function logout(): Promise<void> {
  await apiClient.post('/auth/logout');
}
