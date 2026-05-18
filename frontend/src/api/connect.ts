import { apiClient } from '@/api/client';

/** ConnectTokenResponse.host — moonlight URL 조립에 필요한 호스트 접속 정보 (T07). */
export interface HostConnectionInfo {
  id: number;
  hostname: string;
  ip_address: string | null;
  sunshine_port: number;
}

/** POST /reservations/{id}/connect · POST /reservations/instant 응답. */
export interface ConnectTokenResponse {
  token: string;
  expires_at: string;
  reservation_id: number;
  host: HostConnectionInfo;
}

/** connect 호출 출처 — KPI "사용자 입력 0개" 집계용 (audit detail.client). */
export type ConnectClient = 'connect_page' | 'instant_use';

/** 기존 예약에 대한 접속 토큰 발급 (T17 Section A — 예약 카드 [접속]). */
export async function issueConnectToken(
  reservationId: number,
  client: ConnectClient,
): Promise<ConnectTokenResponse> {
  const { data } = await apiClient.post<ConnectTokenResponse>(
    `/reservations/${reservationId}/connect`,
    { client },
  );
  return data;
}
