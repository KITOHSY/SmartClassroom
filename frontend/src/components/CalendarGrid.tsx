import { useMemo, type ReactElement } from 'react';
import clsx from 'clsx';
import { useRovingTabIndex } from '@/hooks/useRovingTabIndex';
import { HostStatusBadge } from '@/components/HostStatusBadge';
import type { CalendarSlot } from '@/api/reservations';
import type { HostRead } from '@/api/hosts';
import { formatSlotLabel } from '@/lib/time';

export interface CalendarCell {
  host: HostRead;
  slot: CalendarSlot;
  isMine: boolean;
}

export interface CalendarGridProps {
  hosts: HostRead[];
  slotsByHost: Map<number, CalendarSlot[]>;
  currentUserId: number | null;
  onCellActivate: (cell: CalendarCell) => void;
}

interface ColumnHeader {
  startsAt: string;
  endsAt: string;
}

export function CalendarGrid({
  hosts,
  slotsByHost,
  currentUserId,
  onCellActivate,
}: CalendarGridProps): ReactElement {
  const columns = useMemo<ColumnHeader[]>(() => {
    const firstHost = hosts[0];
    if (!firstHost) return [];
    const slots = slotsByHost.get(firstHost.id) ?? [];
    return slots.map((s) => ({ startsAt: s.starts_at, endsAt: s.ends_at }));
  }, [hosts, slotsByHost]);

  const colCount = columns.length;
  const rowCount = hosts.length;

  const onActivate = ({ row, col }: { row: number; col: number }): void => {
    const host = hosts[row];
    if (!host) return;
    const slot = slotsByHost.get(host.id)?.[col];
    if (!slot) return;
    if (slot.status !== 'OPEN') return;
    onCellActivate({ host, slot, isMine: slot.user_id === currentUserId });
  };

  const { isFocused, onKeyDown } = useRovingTabIndex({
    rowCount: Math.max(rowCount, 1),
    colCount: Math.max(colCount, 1),
    onActivate,
  });

  if (hosts.length === 0) {
    return (
      <div className="rounded border border-dashed border-slate-300 p-8 text-center text-slate-500">
        등록된 호스트가 없습니다. 관리자에게 문의하세요.
      </div>
    );
  }

  if (colCount === 0) {
    return (
      <div className="rounded border border-dashed border-slate-300 p-8 text-center text-slate-500">
        선택한 날짜에 표시할 슬롯이 없습니다.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <div
        role="grid"
        aria-label="예약 캘린더"
        aria-rowcount={rowCount + 1}
        aria-colcount={colCount + 1}
        className="inline-grid border border-slate-200 bg-white text-xs"
        style={{
          gridTemplateColumns: `200px repeat(${colCount}, 60px)`,
          gridTemplateRows: `32px repeat(${rowCount}, 36px)`,
        }}
      >
        <div
          role="columnheader"
          aria-rowindex={1}
          aria-colindex={1}
          className="sticky left-0 z-10 flex items-center justify-center border-b border-r border-slate-200 bg-slate-50 font-medium text-slate-600"
        >
          호스트 / 시간
        </div>
        {columns.map((col, c) => (
          <div
            key={col.startsAt}
            role="columnheader"
            aria-rowindex={1}
            aria-colindex={c + 2}
            className="flex items-center justify-center border-b border-r border-slate-200 bg-slate-50 font-medium text-slate-600"
          >
            {formatSlotLabel(col.startsAt)}
          </div>
        ))}

        {hosts.map((host, r) => {
          const slots = slotsByHost.get(host.id) ?? [];
          return (
            <Row
              key={host.id}
              host={host}
              rowIndex={r}
              slots={slots}
              currentUserId={currentUserId}
              isFocused={isFocused}
              onKeyDown={onKeyDown}
              onActivate={onCellActivate}
            />
          );
        })}
      </div>
    </div>
  );
}

interface RowProps {
  host: HostRead;
  rowIndex: number;
  slots: CalendarSlot[];
  currentUserId: number | null;
  isFocused: (row: number, col: number) => boolean;
  onKeyDown: ReturnType<typeof useRovingTabIndex>['onKeyDown'];
  onActivate: (cell: CalendarCell) => void;
}

function Row({
  host,
  rowIndex,
  slots,
  currentUserId,
  isFocused,
  onKeyDown,
  onActivate,
}: RowProps): ReactElement {
  return (
    <>
      <div
        role="rowheader"
        aria-rowindex={rowIndex + 2}
        aria-colindex={1}
        className="sticky left-0 z-10 flex flex-col justify-center gap-0.5 border-b border-r border-slate-200 bg-white px-2 text-slate-700"
      >
        <span className="truncate font-medium leading-tight" title={host.display_name}>
          {host.display_name}
        </span>
        <span className="flex items-center gap-1.5 text-[10px] leading-tight">
          <HostStatusBadge status={host.status} />
          <span className="truncate text-slate-400">{host.hostname}</span>
        </span>
      </div>
      {slots.map((slot, c) => {
        const isMine = slot.user_id !== null && slot.user_id === currentUserId;
        const isOpen = slot.status === 'OPEN';
        const otherUser = slot.status === 'OCCUPIED' && !isMine;
        const focused = isFocused(rowIndex, c);
        const stateLabel = isOpen ? '예약 가능' : isMine ? '내 예약' : '다른 사용자 예약';
        return (
          <button
            key={slot.starts_at}
            type="button"
            role="gridcell"
            aria-rowindex={rowIndex + 2}
            aria-colindex={c + 2}
            aria-label={`${host.display_name} ${formatSlotLabel(slot.starts_at)}~${formatSlotLabel(slot.ends_at)} ${stateLabel}`}
            data-row={rowIndex}
            data-col={c}
            data-state={slot.status}
            tabIndex={focused ? 0 : -1}
            disabled={otherUser}
            onClick={() => isOpen && onActivate({ host, slot, isMine })}
            onKeyDown={(event) => onKeyDown(event, rowIndex, c)}
            className={clsx(
              'border-b border-r border-slate-200 text-[11px] transition-colors',
              isOpen && 'bg-slate-100 hover:bg-slate-200',
              isMine && 'bg-blue-500 text-white hover:bg-blue-600',
              otherUser && 'cursor-not-allowed bg-rose-200 text-rose-900',
            )}
          >
            <span className="sr-only">{stateLabel}</span>
          </button>
        );
      })}
    </>
  );
}
