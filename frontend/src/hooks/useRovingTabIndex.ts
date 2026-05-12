import { useCallback, useState, type KeyboardEvent } from 'react';

export interface RovingPosition {
  row: number;
  col: number;
}

interface RovingOptions {
  rowCount: number;
  colCount: number;
  initial?: RovingPosition;
  onActivate?: (pos: RovingPosition) => void;
  onEscape?: () => void;
}

export interface UseRovingTabIndexResult {
  focused: RovingPosition;
  setFocused: (pos: RovingPosition) => void;
  isFocused: (row: number, col: number) => boolean;
  onKeyDown: (event: KeyboardEvent<HTMLElement>, row: number, col: number) => void;
}

export function useRovingTabIndex({
  rowCount,
  colCount,
  initial,
  onActivate,
  onEscape,
}: RovingOptions): UseRovingTabIndexResult {
  const [focused, setFocused] = useState<RovingPosition>(initial ?? { row: 0, col: 0 });

  const clamp = useCallback(
    (pos: RovingPosition): RovingPosition => ({
      row: Math.max(0, Math.min(rowCount - 1, pos.row)),
      col: Math.max(0, Math.min(colCount - 1, pos.col)),
    }),
    [rowCount, colCount],
  );

  const isFocused = useCallback(
    (row: number, col: number) => focused.row === row && focused.col === col,
    [focused],
  );

  const onKeyDown = useCallback(
    (event: KeyboardEvent<HTMLElement>, row: number, col: number): void => {
      let next: RovingPosition | null = null;
      switch (event.key) {
        case 'ArrowRight':
          next = clamp({ row, col: col + 1 });
          break;
        case 'ArrowLeft':
          next = clamp({ row, col: col - 1 });
          break;
        case 'ArrowDown':
          next = clamp({ row: row + 1, col });
          break;
        case 'ArrowUp':
          next = clamp({ row: row - 1, col });
          break;
        case 'Home':
          next = clamp({ row, col: 0 });
          break;
        case 'End':
          next = clamp({ row, col: colCount - 1 });
          break;
        case 'PageUp':
          next = clamp({ row: 0, col });
          break;
        case 'PageDown':
          next = clamp({ row: rowCount - 1, col });
          break;
        case 'Enter':
        case ' ':
          event.preventDefault();
          onActivate?.({ row, col });
          return;
        case 'Escape':
          if (onEscape) {
            event.preventDefault();
            onEscape();
          }
          return;
        default:
          return;
      }
      if (next) {
        event.preventDefault();
        setFocused(next);
        // 다음 셀에 실제 포커스 이동 — DOM 쿼리로 [data-row][data-col] 셀 픽업.
        const container = event.currentTarget.closest('[role="grid"]');
        if (container) {
          const target = container.querySelector<HTMLElement>(
            `[data-row="${next.row}"][data-col="${next.col}"]`,
          );
          target?.focus();
        }
      }
    },
    [clamp, colCount, rowCount, onActivate, onEscape],
  );

  return { focused, setFocused, isFocused, onKeyDown };
}
