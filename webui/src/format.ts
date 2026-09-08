import type { Cell, Column } from './types';

const DASH = '—';

export function fmt(value: number | null | undefined, format: Column['format']): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  switch (format) {
    case 'recall':
      return value.toFixed(3);
    case 'f1':
      return value.toFixed(2);
    case 'delta':
      return `${value >= 0 ? '+' : '−'}${Math.abs(value).toFixed(3)}`;
    case 'deltaF1':
      // F1 points, so two decimals -- the same precision the arms above print.
      return `${value >= 0 ? '+' : '−'}${Math.abs(value).toFixed(2)}`;
    case 'pct':
      return `${(value * 100).toFixed(1)}%`;
    case 'int':
      return Math.round(value).toLocaleString();
    case 'p':
      return value < 0.0001 ? '<0.0001' : value.toFixed(4);
    default:
      return String(value);
  }
}

/** An interval is shown only when the artifact carried one. */
export function ci(cell: Cell | null | undefined, format: Column['format'] = 'recall'): string | null {
  if (!cell || cell.ciLow === null || cell.ciHigh === null) return null;
  const digits = format === 'f1' || format === 'deltaF1' ? 2 : 3;
  const signed = format === 'delta' || format === 'deltaF1';
  const sign = (x: number) => (signed && x >= 0 ? '+' : x < 0 ? '−' : '');
  return `[${sign(cell.ciLow)}${Math.abs(cell.ciLow).toFixed(digits)}, ${sign(cell.ciHigh)}${Math.abs(
    cell.ciHigh,
  ).toFixed(digits)}]`;
}

/**
 * A CI whose lower bound touches zero is not significant, and this project has
 * had to correct that claim before -- so the label reads off the interval and
 * the recorded flag together rather than off the point estimate.
 */
export function verdict(cell: Cell | null | undefined): {
  label: string;
  tone: 'clear' | 'touches-zero' | 'none';
} {
  if (!cell || cell.value === null) return { label: '', tone: 'none' };
  if (cell.ciLow === null || cell.ciHigh === null) return { label: 'no interval recorded', tone: 'none' };
  if (cell.ciLow <= 0 && cell.ciHigh >= 0) return { label: 'CI includes 0', tone: 'touches-zero' };
  return { label: cell.pHolm !== null ? 'survives Holm' : 'CI excludes 0', tone: 'clear' };
}

export function asCell(raw: unknown): Cell | null {
  if (raw && typeof raw === 'object' && 'value' in (raw as Record<string, unknown>)) {
    return raw as Cell;
  }
  return null;
}

export function short(text: string | null | undefined, n = 180): string {
  if (!text) return '';
  return text.length > n ? `${text.slice(0, n - 1)}…` : text;
}

export function pctString(x: number | null | undefined): string {
  return x === null || x === undefined ? DASH : `${(x * 100).toFixed(0)}%`;
}
