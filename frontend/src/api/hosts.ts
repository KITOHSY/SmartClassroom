import { apiClient } from '@/api/client';

export interface HostRead {
  id: number;
  hostname: string;
  display_name: string;
  location: string | null;
  status: string;
  sunshine_port: number;
  ip_address: string | null;
}

/** GET /hosts/available 응답 — `status='IDLE'` 호스트만 (T06/T17). */
export interface HostAvailable {
  id: number;
  hostname: string;
  display_name: string;
  location: string | null;
  last_heartbeat_at: string | null;
  ip_address: string | null;
  /** 지금부터 즉시 사용 가능한 종료 시각 = min(다음 예약, 2.5h). 슬롯 모드면 null. */
  available_until: string | null;
}

export async function listHosts(): Promise<HostRead[]> {
  const { data } = await apiClient.get<HostRead[]>('/hosts');
  return data;
}

/** 지금 비어 있는(IDLE) 호스트 목록 — T17 가용 PC 현황. */
export async function listAvailableHosts(): Promise<HostAvailable[]> {
  const { data } = await apiClient.get<HostAvailable[]>('/hosts/available');
  return data;
}
