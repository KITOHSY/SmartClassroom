import { apiClient } from '@/api/client';

export interface HostRead {
  id: number;
  hostname: string;
  display_name: string;
  location: string | null;
  status: string;
  sunshine_port: number;
}

export async function listHosts(): Promise<HostRead[]> {
  const { data } = await apiClient.get<HostRead[]>('/hosts');
  return data;
}
