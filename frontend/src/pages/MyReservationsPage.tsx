import { useMutation, useQueries, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState, type ReactElement } from 'react';
import clsx from 'clsx';
import {
  cancelReservation,
  listReservations,
  type Reservation,
  type ReservationStatus,
} from '@/api/reservations';
import { listHosts, type HostRead } from '@/api/hosts';
import { ReservationModal } from '@/components/ReservationModal';
import { useToast } from '@/components/Toast';
import { useMe } from '@/lib/auth';
import { formatDateTimeLabel } from '@/lib/time';
import { parseApiError } from '@/lib/errors';

const STATUS_LABEL: Record<ReservationStatus, string> = {
  CONFIRMED: '확정',
  CANCELED: '취소됨',
  COMPLETED: '완료',
};

const STATUS_BADGE: Record<ReservationStatus, string> = {
  CONFIRMED: 'bg-blue-100 text-blue-800',
  CANCELED: 'bg-slate-100 text-slate-600',
  COMPLETED: 'bg-emerald-100 text-emerald-800',
};

interface ReschedulingState {
  host: HostRead;
  startsAt: string;
}

export function MyReservationsPage(): ReactElement {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { data: me } = useMe();
  const [pendingCancelId, setPendingCancelId] = useState<number | null>(null);
  const [rescheduling, setRescheduling] = useState<ReschedulingState | null>(null);

  // admin은 user_id 미필터 시 전체 반환 — "내 예약" 화면이라 본인 user_id로 명시 강제.
  // (일반 user는 백엔드가 자동 본인 한정이라 필터 무관, admin만 의미.)
  const myUserId = me?.id;

  const [reservationsQuery, hostsQuery] = useQueries({
    queries: [
      {
        queryKey: ['reservations', 'mine', myUserId] as const,
        queryFn: () =>
          listReservations(myUserId !== undefined ? { user_id: myUserId } : {}),
        staleTime: 30_000,
        enabled: myUserId !== undefined,
      },
      {
        queryKey: ['hosts'] as const,
        queryFn: listHosts,
        staleTime: 5 * 60_000,
      },
    ],
  });

  const sorted = useMemo<Reservation[]>(() => {
    if (!reservationsQuery.data) return [];
    return [...reservationsQuery.data].sort((a, b) => b.starts_at.localeCompare(a.starts_at));
  }, [reservationsQuery.data]);

  const hostsById = useMemo(() => {
    const map = new Map<number, HostRead>();
    (hostsQuery.data ?? []).forEach((h) => map.set(h.id, h));
    return map;
  }, [hostsQuery.data]);

  const cancelMutation = useMutation({
    mutationFn: (id: number) => cancelReservation(id),
    onSuccess: async () => {
      toast.push({ variant: 'success', message: '예약이 취소되었습니다' });
      await queryClient.invalidateQueries({ queryKey: ['reservations'] });
      await queryClient.invalidateQueries({ queryKey: ['calendar'] });
    },
    onError: (err) => {
      const parsed = parseApiError(err);
      toast.push({ variant: 'error', message: parsed.message });
    },
    onSettled: () => setPendingCancelId(null),
  });

  const onCancel = (reservation: Reservation): void => {
    if (reservation.status !== 'CONFIRMED') return;
    const ok = window.confirm(
      `${formatDateTimeLabel(reservation.starts_at)} 예약을 취소할까요? (취소 시 즉시 해당 슬롯이 다른 사용자에게 열립니다)`,
    );
    if (!ok) return;
    setPendingCancelId(reservation.id);
    cancelMutation.mutate(reservation.id);
  };

  const onReschedule = async (reservation: Reservation): Promise<void> => {
    const host = hostsById.get(reservation.host_id);
    if (!host) {
      toast.push({ variant: 'error', message: '호스트 정보를 찾을 수 없습니다' });
      return;
    }
    toast.push({
      variant: 'info',
      message:
        '변경은 두 단계입니다 — 1) 기존 예약 취소 → 2) 새 시간으로 예약. 모달이 열립니다.',
      ttlMs: 6000,
    });
    try {
      await cancelReservation(reservation.id);
      await queryClient.invalidateQueries({ queryKey: ['reservations'] });
      await queryClient.invalidateQueries({ queryKey: ['calendar'] });
      setRescheduling({ host, startsAt: reservation.starts_at });
    } catch (err) {
      const parsed = parseApiError(err);
      toast.push({ variant: 'error', message: `취소 실패: ${parsed.message}` });
    }
  };

  if (reservationsQuery.isLoading || hostsQuery.isLoading) {
    return (
      <div role="status" className="rounded border border-slate-200 bg-white p-6 text-slate-500">
        불러오는 중…
      </div>
    );
  }

  if (reservationsQuery.isError) {
    return (
      <div role="alert" className="rounded border border-rose-300 bg-rose-50 p-4 text-rose-700">
        예약 목록을 불러오지 못했습니다.
      </div>
    );
  }

  return (
    <section aria-labelledby="my-reservations-title" className="space-y-4">
      <header>
        <h1 id="my-reservations-title" className="text-xl font-semibold text-slate-900">
          내 예약
        </h1>
        <p className="text-sm text-slate-500">최근 시작 시간 순으로 표시합니다.</p>
      </header>

      {sorted.length === 0 ? (
        <div className="rounded border border-dashed border-slate-300 p-8 text-center text-slate-500">
          예약 내역이 없습니다.
        </div>
      ) : (
        <ul className="space-y-2">
          {sorted.map((r) => {
            const host = hostsById.get(r.host_id);
            const isCanceling = pendingCancelId === r.id;
            return (
              <li
                key={r.id}
                className="flex items-center justify-between rounded border border-slate-200 bg-white p-4"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-slate-900">
                      {host?.display_name ?? `호스트 #${r.host_id}`}
                    </span>
                    <span
                      className={clsx(
                        'rounded px-2 py-0.5 text-xs font-medium',
                        STATUS_BADGE[r.status],
                      )}
                    >
                      {STATUS_LABEL[r.status]}
                    </span>
                  </div>
                  <p className="text-sm text-slate-600">
                    {formatDateTimeLabel(r.starts_at)} ~ {formatDateTimeLabel(r.ends_at)}
                  </p>
                </div>
                <div className="flex gap-2">
                  {r.status === 'CONFIRMED' ? (
                    <>
                      <button
                        type="button"
                        onClick={() => void onReschedule(r)}
                        className="rounded border border-slate-300 px-3 py-1 text-sm text-slate-700 hover:bg-slate-100"
                      >
                        변경
                      </button>
                      <button
                        type="button"
                        onClick={() => onCancel(r)}
                        disabled={isCanceling}
                        className="rounded border border-rose-300 px-3 py-1 text-sm text-rose-700 hover:bg-rose-50 disabled:opacity-60"
                      >
                        {isCanceling ? '취소 중…' : '취소'}
                      </button>
                    </>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {rescheduling ? (
        <ReservationModal
          open
          host={rescheduling.host}
          startsAt={rescheduling.startsAt}
          onClose={() => setRescheduling(null)}
          onCreated={async () => {
            await queryClient.invalidateQueries({ queryKey: ['reservations'] });
            await queryClient.invalidateQueries({ queryKey: ['calendar'] });
          }}
        />
      ) : null}
    </section>
  );
}
