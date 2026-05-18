import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type ReactElement } from 'react';
import { Link } from 'react-router-dom';
import { listAvailableHosts, type HostAvailable } from '@/api/hosts';
import { createInstantReservation } from '@/api/reservations';
import { MoonlightInstallGuide } from '@/components/MoonlightInstallGuide';
import { useToast } from '@/components/Toast';
import { useMoonlightConnect } from '@/hooks/useMoonlightConnect';
import { parseApiError } from '@/lib/errors';
import { formatSlotLabel } from '@/lib/time';

/** available_until(ISO)까지 남은 시간을 사람이 읽는 문자열로 — "15분", "2시간 30분". */
function formatAvailableWindow(untilIso: string): string {
  const mins = Math.round((new Date(untilIso).getTime() - Date.now()) / 60_000);
  if (mins <= 0) return '곧 다음 예약 시작';
  if (mins < 60) return `${mins}분`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return m === 0 ? `${h}시간` : `${h}시간 ${m}분`;
}

/**
 * T17 Section B — 가용 PC 현황 + 즉시 사용.
 *
 * `GET /hosts/available`(IDLE 호스트)을 15초 주기로 폴링한다. [즉시 사용]은 지금부터
 * 약 2시간 30분 윈도우로 즉시 예약 + connect 토큰을 한 번에 받아 moonlight://를 실행한다.
 */
export function AvailableHostsPage(): ReactElement {
  const toast = useToast();
  const queryClient = useQueryClient();
  const { launch, guideOpen, closeGuide } = useMoonlightConnect();
  const [pendingHostId, setPendingHostId] = useState<number | null>(null);

  const hostsQuery = useQuery({
    queryKey: ['hosts', 'available'],
    queryFn: listAvailableHosts,
    refetchInterval: 15_000,
    staleTime: 10_000,
  });

  const instantMutation = useMutation({
    mutationFn: (hostId: number) => createInstantReservation(hostId),
    onSuccess: async (data) => {
      await queryClient.invalidateQueries({ queryKey: ['hosts', 'available'] });
      await queryClient.invalidateQueries({ queryKey: ['reservations'] });
      await launch(data);
    },
    onError: (err) => {
      toast.push({ variant: 'error', message: parseApiError(err).message });
    },
    onSettled: () => setPendingHostId(null),
  });

  const onInstantUse = (host: HostAvailable): void => {
    if (host.ip_address === null) return;
    setPendingHostId(host.id);
    instantMutation.mutate(host.id);
  };

  if (hostsQuery.isLoading) {
    return (
      <div role="status" className="rounded border border-slate-200 bg-white p-6 text-slate-500">
        불러오는 중…
      </div>
    );
  }

  if (hostsQuery.isError) {
    return (
      <div role="alert" className="rounded border border-rose-300 bg-rose-50 p-4 text-rose-700">
        가용 PC 목록을 불러오지 못했습니다.
      </div>
    );
  }

  const hosts = hostsQuery.data ?? [];

  return (
    <section aria-labelledby="available-hosts-title" className="space-y-4">
      <header>
        <h1 id="available-hosts-title" className="text-xl font-semibold text-slate-900">
          지금 비어 있는 PC
        </h1>
        <p className="text-sm text-slate-500">
          예약 없이 바로 사용할 수 있는 PC입니다 — [즉시 사용]을 누르면 약 2시간 30분 동안
          사용할 수 있어요. 목록은 15초마다 자동 갱신됩니다.
        </p>
      </header>

      {hosts.length === 0 ? (
        <div className="rounded border border-dashed border-slate-300 p-8 text-center text-slate-500">
          지금 바로 쓸 수 있는 PC가 없습니다. 잠시 후 다시 확인하거나 캘린더에서 예약해 주세요.
        </div>
      ) : (
        <ul className="space-y-2">
          {hosts.map((host) => {
            const noIp = host.ip_address === null;
            const isPending = pendingHostId === host.id;
            return (
              <li
                key={host.id}
                className="flex items-center justify-between rounded border border-slate-200 bg-white p-4"
              >
                <div className="space-y-1">
                  <span className="font-medium text-slate-900">{host.display_name}</span>
                  {host.location ? (
                    <p className="text-sm text-slate-600">{host.location}</p>
                  ) : null}
                  {host.available_until ? (
                    <p className="text-sm font-medium text-emerald-700">
                      지금부터 약 {formatAvailableWindow(host.available_until)} 사용 가능 (~
                      {formatSlotLabel(host.available_until)})
                    </p>
                  ) : null}
                  {noIp ? (
                    <p className="text-xs text-amber-700">접속 정보가 등록되지 않은 PC입니다.</p>
                  ) : null}
                </div>
                <button
                  type="button"
                  onClick={() => onInstantUse(host)}
                  disabled={noIp || isPending}
                  className="rounded bg-brand px-3 py-1.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
                >
                  {isPending ? '연결 중…' : '즉시 사용'}
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <p className="text-sm text-slate-500">
        특정 시간대를 예약하려면{' '}
        <Link to="/" className="text-brand underline">
          캘린더
        </Link>
        로 이동하세요.
      </p>

      <MoonlightInstallGuide open={guideOpen} onClose={closeGuide} />
    </section>
  );
}
