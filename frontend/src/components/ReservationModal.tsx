import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState, type ReactElement } from 'react';
import clsx from 'clsx';
import { addMinutes } from 'date-fns';
import { createReservation, type CreateReservationPayload } from '@/api/reservations';
import type { HostRead } from '@/api/hosts';
import { useToast } from '@/components/Toast';
import { useFocusTrap } from '@/hooks/useFocusTrap';
import {
  extractValidationErrors,
  isInvalidReservationWindow,
  isReservationConflict,
  isReservationQuotaExceeded,
  parseApiError,
} from '@/lib/errors';
import { formatDateTimeLabel, formatSlotLabel, SLOT_MINUTES, toIsoWithOffset } from '@/lib/time';

const MAX_DURATION_MINUTES = 240; // 백엔드 max_reservation_duration_minutes 기본값

interface ReservationModalProps {
  open: boolean;
  host: HostRead;
  startsAt: string;
  onClose: () => void;
  onCreated?: () => void | Promise<void>;
  /** 드래그/클릭으로 정한 예약 길이(분). 미지정 시 30분. 모달에서 수정하지 않는다. */
  durationMinutes?: number;
}

const WINDOW_REASON_LABEL: Record<string, string> = {
  too_early: '시작 시간은 현재 이후여야 합니다',
  expired_window: '예약 가능 시간이 지났습니다',
  duration: '예약 길이 한도를 초과했습니다',
  lookahead: '예약 가능 기간을 초과했습니다',
  past: '과거 시간으로 예약할 수 없습니다',
  grid: '30분 그리드에 정렬되어야 합니다',
};

function describeQuota(detail: Record<string, unknown> | null): string {
  if (!detail) return '예약 한도를 초과했습니다';
  const limit = detail.limit;
  const current = typeof detail.current === 'number' ? detail.current : null;
  const max = typeof detail.max === 'number' ? detail.max : null;
  if (limit === 'daily_minutes') {
    return `오늘 누적 ${current ?? '?'}분 / 한도 ${max ?? '?'}분을 초과합니다`;
  }
  if (limit === 'concurrent') {
    return `현재 활성 예약 ${current ?? '?'}건 / 한도 ${max ?? '?'}건을 초과합니다`;
  }
  return '예약 한도를 초과했습니다';
}

export function ReservationModal({
  open,
  host,
  startsAt,
  onClose,
  onCreated,
  durationMinutes: durationProp,
}: ReservationModalProps): ReactElement | null {
  const containerRef = useRef<HTMLDivElement>(null);
  const initialFocusRef = useRef<HTMLButtonElement>(null);
  const queryClient = useQueryClient();
  const toast = useToast();
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [windowReason, setWindowReason] = useState<string | null>(null);

  // 길이는 드래그/클릭으로 정해진 고정값 — 30분 그리드·30~240분으로 클램프(방어).
  const durationMinutes = useMemo(() => {
    const grid = Math.round((durationProp ?? SLOT_MINUTES) / SLOT_MINUTES) * SLOT_MINUTES;
    return Math.min(Math.max(grid, SLOT_MINUTES), MAX_DURATION_MINUTES);
  }, [durationProp]);

  const endsAtIso = useMemo(
    () => toIsoWithOffset(addMinutes(new Date(startsAt), durationMinutes)),
    [startsAt, durationMinutes],
  );

  useFocusTrap(containerRef, {
    active: open,
    onEscape: onClose,
    initialFocusRef,
  });

  useEffect(() => {
    if (!open) return;
    setFieldError(null);
    setWindowReason(null);
  }, [open, startsAt, host.id]);

  const mutation = useMutation({
    mutationFn: (payload: CreateReservationPayload) => createReservation(payload),
    onSuccess: async () => {
      toast.push({ variant: 'success', message: '예약이 생성되었습니다' });
      await onCreated?.();
      onClose();
    },
    onError: async (err) => {
      const parsed = parseApiError(err);
      if (isReservationConflict(parsed)) {
        await queryClient.invalidateQueries({ queryKey: ['calendar'] });
        toast.push({
          variant: 'warning',
          message: '이미 예약된 슬롯입니다. 캘린더를 새로고침했습니다.',
        });
        onClose();
        return;
      }
      if (isReservationQuotaExceeded(parsed)) {
        toast.push({ variant: 'error', message: describeQuota(parsed.detail) });
        onClose();
        return;
      }
      if (isInvalidReservationWindow(parsed)) {
        const reason =
          (parsed.detail?.reason as string | undefined) ??
          (parsed.detail?.field as string | undefined) ??
          null;
        setWindowReason(reason ? (WINDOW_REASON_LABEL[reason] ?? parsed.message) : parsed.message);
        return;
      }
      const validation = extractValidationErrors(parsed);
      if (validation.length > 0) {
        setFieldError(validation.map((v) => `${v.loc.join('.')}: ${v.msg}`).join('\n'));
        return;
      }
      toast.push({ variant: 'error', message: parsed.message });
    },
  });

  if (!open) return null;

  const onSubmit = (event: React.FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setFieldError(null);
    setWindowReason(null);
    mutation.mutate({
      host_id: host.id,
      starts_at: toIsoWithOffset(new Date(startsAt)),
      ends_at: endsAtIso,
    });
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="reservation-modal-title"
      className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/50 p-4"
    >
      <div
        ref={containerRef}
        tabIndex={-1}
        className="w-full max-w-md rounded-lg bg-white p-6 shadow-lg focus:outline-none"
      >
        <header className="mb-4 flex items-start justify-between">
          <div>
            <h2 id="reservation-modal-title" className="text-lg font-semibold text-slate-900">
              예약 생성
            </h2>
            <p className="text-xs text-slate-500">{host.display_name}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="모달 닫기"
            className="rounded p-1 text-slate-500 hover:bg-slate-100"
          >
            ×
          </button>
        </header>

        <form onSubmit={onSubmit} className="space-y-4">
          <dl className="grid grid-cols-3 gap-2 text-sm">
            <dt className="col-span-1 text-slate-500">호스트</dt>
            <dd className="col-span-2 text-slate-900">
              {host.display_name}{' '}
              <span className="text-xs text-slate-400">({host.hostname})</span>
            </dd>
            <dt className="col-span-1 text-slate-500">시작</dt>
            <dd className="col-span-2 text-slate-900">{formatDateTimeLabel(startsAt)}</dd>
            <dt className="col-span-1 text-slate-500">종료</dt>
            <dd className="col-span-2 text-slate-900">
              {formatDateTimeLabel(endsAtIso)} ({formatSlotLabel(endsAtIso)})
            </dd>
            <dt className="col-span-1 text-slate-500">길이</dt>
            <dd className="col-span-2 font-medium text-slate-900">
              {durationMinutes}분 ({(durationMinutes / 60).toFixed(1)}시간)
            </dd>
          </dl>

          {windowReason ? (
            <div role="alert" className="rounded border border-amber-300 bg-amber-50 p-2 text-xs text-amber-800">
              {windowReason}
            </div>
          ) : null}

          {fieldError ? (
            <div role="alert" className="whitespace-pre-line rounded border border-rose-300 bg-rose-50 p-2 text-xs text-rose-700">
              {fieldError}
            </div>
          ) : null}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              ref={initialFocusRef}
              onClick={onClose}
              className="rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100"
            >
              취소
            </button>
            <button
              type="submit"
              disabled={mutation.isPending}
              className={clsx(
                'rounded bg-brand px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700',
                mutation.isPending && 'opacity-60',
              )}
            >
              {mutation.isPending ? '예약 중…' : '예약'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
