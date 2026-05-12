import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  type ReactElement,
  type ReactNode,
} from 'react';
import clsx from 'clsx';

export type ToastVariant = 'info' | 'success' | 'error' | 'warning';

export interface ToastItem {
  id: string;
  variant: ToastVariant;
  message: string;
  ttlMs: number;
}

interface ToastState {
  items: ToastItem[];
}

type Action = { type: 'add'; toast: ToastItem } | { type: 'remove'; id: string };

function reducer(state: ToastState, action: Action): ToastState {
  switch (action.type) {
    case 'add':
      return { items: [...state.items, action.toast] };
    case 'remove':
      return { items: state.items.filter((t) => t.id !== action.id) };
    default:
      return state;
  }
}

interface ToastContextValue {
  push: (toast: Omit<ToastItem, 'id' | 'ttlMs'> & { ttlMs?: number }) => string;
  remove: (id: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }): ReactElement {
  const [state, dispatch] = useReducer(reducer, { items: [] });

  const remove = useCallback((id: string) => dispatch({ type: 'remove', id }), []);

  const push = useCallback(
    (toast: Omit<ToastItem, 'id' | 'ttlMs'> & { ttlMs?: number }) => {
      const id = `t-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const ttlMs = toast.ttlMs ?? 4000;
      dispatch({ type: 'add', toast: { ...toast, id, ttlMs } });
      return id;
    },
    [],
  );

  useEffect(() => {
    const timers = state.items.map((t) =>
      window.setTimeout(() => dispatch({ type: 'remove', id: t.id }), t.ttlMs),
    );
    return () => {
      timers.forEach((handle) => window.clearTimeout(handle));
    };
  }, [state.items]);

  const value = useMemo<ToastContextValue>(() => ({ push, remove }), [push, remove]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="pointer-events-none fixed right-4 top-4 z-50 flex w-80 flex-col gap-2"
      >
        {state.items.map((toast) => (
          <div
            key={toast.id}
            role={toast.variant === 'error' ? 'alert' : 'status'}
            className={clsx(
              'pointer-events-auto rounded border px-3 py-2 text-sm shadow-sm',
              toast.variant === 'success' && 'border-emerald-300 bg-emerald-50 text-emerald-800',
              toast.variant === 'error' && 'border-rose-300 bg-rose-50 text-rose-800',
              toast.variant === 'warning' && 'border-amber-300 bg-amber-50 text-amber-800',
              toast.variant === 'info' && 'border-slate-300 bg-white text-slate-800',
            )}
          >
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast는 ToastProvider 내부에서만 호출');
  return ctx;
}
