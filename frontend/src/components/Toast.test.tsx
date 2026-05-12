import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { ToastProvider, useToast } from './Toast';

function Trigger({
  message,
  variant = 'info' as const,
  ttlMs,
}: {
  message: string;
  variant?: 'info' | 'success' | 'error' | 'warning';
  ttlMs?: number;
}) {
  const { push } = useToast();
  return (
    <button
      type="button"
      onClick={() =>
        push({ variant, message, ...(ttlMs !== undefined ? { ttlMs } : {}) })
      }
    >
      push
    </button>
  );
}

describe('<ToastProvider />', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('push 호출 시 토스트 메시지 노출, ttl 후 자동 제거', () => {
    // user-event v14의 click은 내부 setTimeout 사용 → fake timer와 충돌.
    // toast push 트리거 검증에는 fireEvent.click(동기)가 충분.
    render(
      <ToastProvider>
        <Trigger message="안녕하세요" ttlMs={1500} />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'push' }));
    expect(screen.getByText('안녕하세요')).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(1600);
    });

    expect(screen.queryByText('안녕하세요')).not.toBeInTheDocument();
  });

  it('error variant는 role=alert로 렌더', () => {
    render(
      <ToastProvider>
        <Trigger message="실패!" variant="error" ttlMs={5000} />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'push' }));
    expect(screen.getByRole('alert')).toHaveTextContent('실패!');
  });
});
