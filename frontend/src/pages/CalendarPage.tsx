import { useMemo, useState, type ReactElement } from 'react';
import { useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { listHosts, type HostRead } from '@/api/hosts';
import {
  getCalendar,
  type CalendarMatrix,
  type CalendarSlot,
} from '@/api/reservations';
import { CalendarGrid, type CalendarCell } from '@/components/CalendarGrid';
import { ReservationModal } from '@/components/ReservationModal';
import { useMe } from '@/lib/auth';
import { addDays, formatDateLabel, kstEndOfDay, kstStartOfDay, LOOKAHEAD_DAYS, toIsoWithOffset } from '@/lib/time';

interface SelectedCell {
  host: HostRead;
  startsAt: string;
}

export function CalendarPage(): ReactElement {
  const { data: me } = useMe();
  const queryClient = useQueryClient();
  const [selectedDate, setSelectedDate] = useState<string>(() => formatDateLabel(new Date()));
  const [hostFilter, setHostFilter] = useState<'all' | number>('all');
  const [selectedCell, setSelectedCell] = useState<SelectedCell | null>(null);

  const dateOptions = useMemo(() => {
    const today = new Date();
    return Array.from({ length: LOOKAHEAD_DAYS + 1 }, (_, i) => formatDateLabel(addDays(today, i)));
  }, []);

  const { fromIso, toIso } = useMemo(() => {
    const [yearStr, monthStr, dayStr] = selectedDate.split('-');
    const year = Number(yearStr);
    const month = Number(monthStr);
    const day = Number(dayStr);
    const baseDate = new Date(Date.UTC(year, month - 1, day));
    return {
      fromIso: toIsoWithOffset(kstStartOfDay(baseDate)),
      toIso: toIsoWithOffset(kstEndOfDay(baseDate)),
    };
  }, [selectedDate]);

  const hostsQuery = useQuery({
    queryKey: ['hosts'],
    queryFn: listHosts,
    staleTime: 5 * 60_000,
  });

  const visibleHosts = useMemo<HostRead[]>(() => {
    if (!hostsQuery.data) return [];
    if (hostFilter === 'all') return hostsQuery.data;
    return hostsQuery.data.filter((h) => h.id === hostFilter);
  }, [hostsQuery.data, hostFilter]);

  const calendarQueries = useQueries({
    queries: visibleHosts.map((host) => ({
      queryKey: ['calendar', fromIso, toIso, host.id] as const,
      queryFn: () => getCalendar({ from: fromIso, to: toIso, host_id: host.id }),
      staleTime: 30_000,
    })),
  });

  const slotsByHost = useMemo(() => {
    const map = new Map<number, CalendarSlot[]>();
    visibleHosts.forEach((host, idx) => {
      const data = calendarQueries[idx]?.data as CalendarMatrix | undefined;
      map.set(host.id, data?.slots ?? []);
    });
    return map;
  }, [visibleHosts, calendarQueries]);

  const isLoading =
    hostsQuery.isLoading || calendarQueries.some((q) => q.isLoading && !q.data);
  const isError = hostsQuery.isError || calendarQueries.some((q) => q.isError);

  const onCellActivate = (cell: CalendarCell): void => {
    setSelectedCell({ host: cell.host, startsAt: cell.slot.starts_at });
  };

  const onModalClose = (): void => setSelectedCell(null);

  const onReservationCreated = async (): Promise<void> => {
    await queryClient.invalidateQueries({ queryKey: ['calendar'] });
    await queryClient.invalidateQueries({ queryKey: ['reservations'] });
  };

  const currentUserKey = me?.external_id ?? null;
  // /me 응답의 내부 PK로 본인 예약 셀 강조. 백엔드 calendar 응답이 user_id를 본인/admin에만
  // 노출하므로 일치 비교가 가능. admin은 모든 user_id 노출 → 본인 셀만 강조됨.
  const currentUserId: number | null = me?.id ?? null;

  return (
    <section aria-labelledby="calendar-title" className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 id="calendar-title" className="text-xl font-semibold text-slate-900">
            예약 캘린더
          </h1>
          <p className="text-xs text-slate-500" data-testid="current-user-key">
            {currentUserKey ? `로그인: ${currentUserKey}` : ''}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-slate-700">
            날짜
            <select
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="ml-2 rounded border border-slate-300 px-2 py-1 text-sm"
            >
              {dateOptions.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm text-slate-700">
            호스트
            <select
              value={hostFilter}
              onChange={(e) =>
                setHostFilter(e.target.value === 'all' ? 'all' : Number(e.target.value))
              }
              className="ml-2 rounded border border-slate-300 px-2 py-1 text-sm"
            >
              <option value="all">전체</option>
              {(hostsQuery.data ?? []).map((h) => (
                <option key={h.id} value={h.id}>
                  {h.display_name}
                </option>
              ))}
            </select>
          </label>
        </div>
      </header>

      {isLoading ? (
        <div role="status" className="rounded border border-slate-200 bg-white p-6 text-slate-500">
          캘린더 로딩 중…
        </div>
      ) : isError ? (
        <div role="alert" className="rounded border border-rose-300 bg-rose-50 p-4 text-rose-700">
          캘린더를 불러오지 못했습니다. 잠시 후 다시 시도하세요.
        </div>
      ) : (
        <CalendarGrid
          hosts={visibleHosts}
          slotsByHost={slotsByHost}
          currentUserId={currentUserId}
          onCellActivate={onCellActivate}
        />
      )}

      {selectedCell ? (
        <ReservationModal
          open
          host={selectedCell.host}
          startsAt={selectedCell.startsAt}
          onClose={onModalClose}
          onCreated={onReservationCreated}
        />
      ) : null}
    </section>
  );
}
