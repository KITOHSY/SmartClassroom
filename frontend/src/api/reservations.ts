import { apiClient } from '@/api/client';

export type ReservationStatus = 'CONFIRMED' | 'CANCELED' | 'COMPLETED';

export interface Reservation {
  id: number;
  user_id: number;
  host_id: number;
  starts_at: string;
  ends_at: string;
  status: ReservationStatus;
  created_at: string;
  canceled_at: string | null;
}

export type CalendarSlotStatus = 'OPEN' | 'OCCUPIED';

export interface CalendarSlot {
  starts_at: string;
  ends_at: string;
  host_id: number;
  reservation_id: number | null;
  user_id: number | null;
  status: CalendarSlotStatus;
}

export interface CalendarMatrix {
  from_: string;
  to_: string;
  slot_minutes: number;
  slots: CalendarSlot[];
}

export interface CalendarParams {
  from: string;
  to: string;
  host_id?: number;
}

export async function getCalendar(params: CalendarParams): Promise<CalendarMatrix> {
  const { data } = await apiClient.get<CalendarMatrix>('/reservations/calendar', {
    params: {
      from: params.from,
      to: params.to,
      ...(params.host_id !== undefined ? { host_id: params.host_id } : {}),
    },
  });
  return data;
}

export interface CreateReservationPayload {
  host_id: number;
  starts_at: string;
  ends_at: string;
}

export async function createReservation(payload: CreateReservationPayload): Promise<Reservation> {
  const { data } = await apiClient.post<Reservation>('/reservations', payload);
  return data;
}

export async function cancelReservation(id: number): Promise<void> {
  await apiClient.delete(`/reservations/${id}`);
}

export interface ListReservationsFilters {
  from?: string;
  to?: string;
  host_id?: number;
  user_id?: number;
}

export async function listReservations(
  filters: ListReservationsFilters = {},
): Promise<Reservation[]> {
  const params: Record<string, string | number> = {};
  if (filters.from) params.from = filters.from;
  if (filters.to) params.to = filters.to;
  if (filters.host_id !== undefined) params.host_id = filters.host_id;
  if (filters.user_id !== undefined) params.user_id = filters.user_id;
  const { data } = await apiClient.get<Reservation[]>('/reservations', { params });
  return data;
}
