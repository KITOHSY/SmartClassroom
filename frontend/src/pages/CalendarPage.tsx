import { useCallback, useEffect, useMemo, useState, type ReactElement } from 'react';
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { listAvailableHosts, listHosts, type HostRead } from '@/api/hosts';
import {
  createInstantReservation,
  getCalendar,
  type CalendarMatrix,
  type CalendarSlot,
} from '@/api/reservations';
import { CalendarGrid, type CalendarCell } from '@/components/CalendarGrid';
import { MoonlightInstallGuide } from '@/components/MoonlightInstallGuide';
import { ReservationModal } from '@/components/ReservationModal';
import { useToast } from '@/components/Toast';
import { useMoonlightConnect } from '@/hooks/useMoonlightConnect';
import { useMe } from '@/lib/auth';
import { parseApiError } from '@/lib/errors';
import {
  addDays,
  formatDateLabel,
  kstStartOfDay,
  kstWindowEnd,
  LOOKAHEAD_DAYS,
  SLOT_MINUTES,
  toIsoWithOffset,
} from '@/lib/time';

interface SelectedCell {
  host: HostRead;
  startsAt: string;
  /** 드래그로 선택한 길이(분) — 모달에 프리필. 단일 클릭/키보드는 미지정. */
  durationMinutes?: number;
}

interface ConfirmedInstant {
  hostId: number;
  untilIso: string;
  /** 예약 ID — onSuccess(캘린더 refetch 후)에 기록. 예약이 취소되면 정합성 검증으로 바를 해제. */
  reservationId?: number;
}

const CONFIRMED_INSTANT_KEY = 'sc.confirmedInstant';

/** sessionStorage에 확정 바 목록을 기록 — 빈 배열이면 키 제거. */
function writeConfirmedInstants(list: ConfirmedInstant[]): void {
  if (list.length === 0) {
    sessionStorage.removeItem(CONFIRMED_INSTANT_KEY);
  } else {
    sessionStorage.setItem(CONFIRMED_INSTANT_KEY, JSON.stringify(list));
  }
}

/** sessionStorage의 즉시 사용 확정 바 목록 — 새로고침 후에도 윈도우가 끝날 때까지 유지.
 *  만료 항목은 걸러내고, 구버전 단일-객체 값은 파싱/`.filter` 실패로 빈 배열 처리(자동 마이그레이션). */
function readConfirmedInstants(): ConfirmedInstant[] {
  try {
    const raw = sessionStorage.getItem(CONFIRMED_INSTANT_KEY);
    if (raw === null) return [];
    const parsed = JSON.parse(raw) as ConfirmedInstant[];
    const now = Date.now();
    const alive = parsed.filter((c) => new Date(c.untilIso).getTime() > now);
    if (alive.length !== parsed.length) writeConfirmedInstants(alive);
    return alive;
  } catch {
    sessionStorage.removeItem(CONFIRMED_INSTANT_KEY);
    return [];
  }
}

export function CalendarPage(): ReactElement {
  const { data: me } = useMe();
  const queryClient = useQueryClient();
  const toast = useToast();
  const { launch, guideOpen, closeGuide } = useMoonlightConnect();
  const [selectedDate, setSelectedDate] = useState<string>(() => formatDateLabel(new Date()));
  const [hostFilter, setHostFilter] = useState<'all' | number>('all');
  const [selectedCell, setSelectedCell] = useState<SelectedCell | null>(null);
  const [pendingInstantHostId, setPendingInstantHostId] = useState<number | null>(null);
  // 방금 즉시 사용한 호스트들 — 클릭 즉시(낙관적) 파란 확정 바를 그린다. 호스트별 1건.
  // sessionStorage에서 복원 — 새로고침해도 윈도우가 끝날 때까지 파란 바가 유지된다.
  const [confirmedInstants, setConfirmedInstants] = useState<ConfirmedInstant[]>(
    () => readConfirmedInstants(),
  );

  const isToday = selectedDate === formatDateLabel(new Date());

  const dateOptions = useMemo(() => {
    const today = new Date();
    return Array.from({ length: LOOKAHEAD_DAYS + 1 }, (_, i) => formatDateLabel(addDays(today, i)));
  }, []);

  // 2일(48시간, 96칸) 윈도우 — 드래그가 자정 경계를 넘어 다음 날 칸까지 이어진다.
  const { fromIso, toIso } = useMemo(() => {
    const [yearStr, monthStr, dayStr] = selectedDate.split('-');
    const year = Number(yearStr);
    const month = Number(monthStr);
    const day = Number(dayStr);
    const baseDate = new Date(Date.UTC(year, month - 1, day));
    return {
      fromIso: toIsoWithOffset(kstStartOfDay(baseDate)),
      toIso: toIsoWithOffset(kstWindowEnd(baseDate)),
    };
  }, [selectedDate]);

  // 15초 폴링 — 타 사용자의 점유/취소로 인한 호스트 상태 변화를 배지에 신선하게 반영.
  // (즉시 사용 버튼 목록 availableHostsQuery와 동일 주기.)
  // refetchOnMount:'always' — 캘린더 탭 복귀(remount)마다 staleTime 무관 1회 강제 갱신.
  const hostsQuery = useQuery({
    queryKey: ['hosts'],
    queryFn: listHosts,
    refetchInterval: 15_000,
    staleTime: 10_000,
    refetchOnMount: 'always',
  });

  // 즉시 사용 가능 호스트 — 오늘 뷰에서만 15초 폴링.
  const availableHostsQuery = useQuery({
    queryKey: ['hosts', 'available'],
    queryFn: listAvailableHosts,
    refetchInterval: 15_000,
    staleTime: 10_000,
    refetchOnMount: 'always',
    enabled: isToday,
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
      // 탭 복귀(remount)마다 강제 갱신 — 타 사용자 예약 반영.
      refetchOnMount: 'always' as const,
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

  // 확정 바 정합성 — 예약이 취소/소멸돼 캘린더 슬롯에서 사라진 항목을 해제한다.
  // reservationId는 onSuccess(캘린더 refetch 후)에만 채워지므로 낙관적 표시 중엔 검증 skip.
  useEffect(() => {
    setConfirmedInstants((prev) => {
      const next = prev.filter((c) => {
        if (c.reservationId === undefined) return true; // 낙관적 표시 중
        const slots = slotsByHost.get(c.hostId);
        if (slots === undefined || slots.length === 0) return true; // 캘린더 미로딩
        return slots.some((s) => s.reservation_id === c.reservationId);
      });
      if (next.length === prev.length) return prev; // 변경 없음 — 재렌더 회피
      writeConfirmedInstants(next);
      return next;
    });
  }, [slotsByHost]);

  // 즉시 사용 가능 host id → available_until ISO (오늘 뷰에서만).
  const instantByHost = useMemo(() => {
    const map = new Map<number, string>();
    if (isToday) {
      for (const h of availableHostsQuery.data ?? []) {
        if (h.available_until) map.set(h.id, h.available_until);
      }
    }
    return map;
  }, [isToday, availableHostsQuery.data]);

  // 현재 시각이 속한 컬럼 인덱스 — 자동 스크롤 / 즉시 사용 호버 포커스 대상.
  const nowColIndex = useMemo<number | null>(() => {
    if (!isToday) return null;
    const firstHost = visibleHosts[0];
    if (!firstHost) return null;
    const slots = slotsByHost.get(firstHost.id) ?? [];
    const nowMs = Date.now();
    const idx = slots.findIndex(
      (s) => new Date(s.starts_at).getTime() <= nowMs && nowMs < new Date(s.ends_at).getTime(),
    );
    return idx >= 0 ? idx : null;
  }, [isToday, visibleHosts, slotsByHost]);

  const isLoading =
    hostsQuery.isLoading || calendarQueries.some((q) => q.isLoading && !q.data);
  const isError = hostsQuery.isError || calendarQueries.some((q) => q.isError);

  const onCellActivate = useCallback((cell: CalendarCell): void => {
    setSelectedCell({
      host: cell.host,
      startsAt: cell.slot.starts_at,
      ...(cell.spanMinutes !== undefined ? { durationMinutes: cell.spanMinutes } : {}),
    });
  }, []);

  // 예약 불가 셀(과거 시각 / 점검 중·오프라인 / 접속 정보 미등록 호스트) 클릭·드래그·Enter 시 안내.
  const onBlockedAttempt = useCallback(
    (reason: 'past' | 'host-unreservable' | 'host-no-ip'): void => {
      const message =
        reason === 'past'
          ? '과거 시간으로는 예약할 수 없습니다'
          : reason === 'host-no-ip'
            ? '접속 정보가 등록되지 않은 PC는 예약할 수 없습니다'
            : '점검 중·오프라인 상태의 PC는 예약할 수 없습니다';
      toast.push({ variant: 'warning', message });
    },
    [toast],
  );

  const instantMutation = useMutation({
    mutationFn: (hostId: number) => createInstantReservation(hostId),
    onSuccess: async (data, hostId) => {
      // `['hosts']` 무효화는 `['hosts','available']`까지 prefix로 함께 갱신 —
      // 즉시 사용으로 IN_USE가 된 호스트의 상태 배지가 바로 반영된다.
      await queryClient.invalidateQueries({ queryKey: ['hosts'] });
      await queryClient.invalidateQueries({ queryKey: ['reservations'] });
      await queryClient.invalidateQueries({ queryKey: ['calendar'] });
      // 캘린더가 새 예약을 반영한 뒤 해당 호스트 항목에 reservationId를 기록 — 이후 예약이
      // 취소되면 검증 effect가 캘린더 슬롯에서 사라진 걸 보고 확정 바를 자동 해제한다.
      setConfirmedInstants((prev) => {
        const next = prev.map((c) =>
          c.hostId === hostId ? { ...c, reservationId: data.reservation_id } : c,
        );
        writeConfirmedInstants(next);
        return next;
      });
      await launch(data);
    },
    onError: (err, hostId) => {
      setConfirmedInstants((prev) => {
        const next = prev.filter((c) => c.hostId !== hostId); // 낙관적 하이라이트 롤백
        writeConfirmedInstants(next);
        return next;
      });
      const parsed = parseApiError(err);
      // 409 = 호스트가 이미 점유됨 — stale 화면(상태 배지·즉시 사용 버튼·캘린더)을 즉시 보정.
      if (parsed.status === 409) {
        void queryClient.invalidateQueries({ queryKey: ['hosts'] });
        void queryClient.invalidateQueries({ queryKey: ['calendar'] });
      }
      toast.push({ variant: 'error', message: parsed.message });
    },
    onSettled: () => setPendingInstantHostId(null),
  });

  const onInstantUse = (host: HostRead): void => {
    if (host.ip_address === null) return;
    // 클릭 즉시 파란 확정 바를 띄운다(낙관적) — 네트워크/refetch 대기 중 회색 깜빡임 방지.
    // 같은 호스트 기존 항목은 교체. sessionStorage에도 저장 — 새로고침 후에도 유지된다.
    const untilIso = instantByHost.get(host.id);
    if (untilIso) {
      setConfirmedInstants((prev) => {
        const next = [...prev.filter((c) => c.hostId !== host.id), { hostId: host.id, untilIso }];
        writeConfirmedInstants(next);
        return next;
      });
    }
    setPendingInstantHostId(host.id);
    instantMutation.mutate(host.id);
  };

  const onModalClose = (): void => setSelectedCell(null);

  const onReservationCreated = async (): Promise<void> => {
    await queryClient.invalidateQueries({ queryKey: ['calendar'] });
    await queryClient.invalidateQueries({ queryKey: ['reservations'] });
    // 새 예약은 그 호스트의 즉시 사용 윈도우(available_until)를 줄인다 — `['hosts']`를
    // 무효화(prefix로 `['hosts','available']`까지)해 즉시 사용 호버의 초록 미리보기 바가
    // stale하게 새 예약 셀을 덮지 않도록 한다.
    await queryClient.invalidateQueries({ queryKey: ['hosts'] });
  };

  // 예약 모달이 열린 동안 캘린더에 파랗게 유지할 범위 — 모달이 닫히면 selectedCell이 null이 돼
  // 강조가 자동 해제된다. 단일 클릭/키보드는 durationMinutes 미지정 → 기본 30분.
  const selectedRange = useMemo(
    () =>
      selectedCell
        ? {
            hostId: selectedCell.host.id,
            startsAt: selectedCell.startsAt,
            minutes: selectedCell.durationMinutes ?? SLOT_MINUTES,
          }
        : null,
    [selectedCell],
  );

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
          <p className="text-xs text-slate-500">
            셀을 드래그하면 시간 범위를 한 번에 선택할 수 있어요. 빈 PC는 행 머리의 [즉시 사용]으로
            바로 접속하세요.
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
          isToday={isToday}
          nowColIndex={nowColIndex}
          instantByHost={instantByHost}
          pendingInstantHostId={pendingInstantHostId}
          confirmedInstants={confirmedInstants}
          selectedRange={selectedRange}
          onInstantUse={onInstantUse}
          onBlockedAttempt={onBlockedAttempt}
        />
      )}

      {selectedCell ? (
        <ReservationModal
          open
          host={selectedCell.host}
          startsAt={selectedCell.startsAt}
          onClose={onModalClose}
          onCreated={onReservationCreated}
          {...(selectedCell.durationMinutes !== undefined
            ? { durationMinutes: selectedCell.durationMinutes }
            : {})}
        />
      ) : null}

      <MoonlightInstallGuide open={guideOpen} onClose={closeGuide} />
    </section>
  );
}
