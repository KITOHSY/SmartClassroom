import { type ReactElement } from 'react';
import clsx from 'clsx';

/**
 * 호스트 status 배지 — T06 상태 머신의 4값에 한글 라벨 + 관례 색을 매핑.
 *
 * 색은 심각도 램프: 🟢 IDLE(사용 가능) → 🔵 IN_USE(정상이나 사용 중) →
 * 🟠 DEGRADED(경고) → 🔴 OFFLINE(다운). 미지의 값은 회색 fallback.
 */
const STATUS_META: Record<string, { label: string; dot: string; text: string }> = {
  IDLE: { label: '대기 중', dot: 'bg-emerald-500', text: 'text-emerald-700' },
  IN_USE: { label: '사용 중', dot: 'bg-blue-500', text: 'text-blue-700' },
  DEGRADED: { label: '성능 저하', dot: 'bg-amber-500', text: 'text-amber-700' },
  OFFLINE: { label: '오프라인', dot: 'bg-rose-500', text: 'text-rose-700' },
};

const UNKNOWN = { label: '알 수 없음', dot: 'bg-slate-400', text: 'text-slate-500' };

export function HostStatusBadge({ status }: { status: string }): ReactElement {
  const meta = STATUS_META[status] ?? UNKNOWN;
  return (
    <span className={clsx('inline-flex items-center gap-1 font-medium', meta.text)}>
      <span
        className={clsx('h-1.5 w-1.5 shrink-0 rounded-full', meta.dot)}
        aria-hidden="true"
      />
      <span>{meta.label}</span>
    </span>
  );
}
