import { useState } from 'react';
import type { Cell } from '../types';
import { ci as ciText, fmt } from '../format';

/**
 * Two chart forms, because the dashboard has exactly two jobs.
 *
 * `Bars` compares magnitudes across a handful of named rows -- horizontal, so a
 * label like "canonical pool, k=10" stays readable. `Lines` shows recall against
 * a budget, where the whole point is the shape of three curves against each
 * other.
 *
 * Colors come from the validated categorical palette (blue / orange / aqua) and
 * the blue-red diverging pair for signed values; the violet in the chrome is UI,
 * never a data color. Every chart sits directly above the table holding the same
 * numbers, which is the relief the aqua series needs on a white surface.
 */

const SERIES = ['#2a78d6', '#eb6834', '#1baf7a'];
const POSITIVE = '#2a78d6';
const NEGATIVE = '#d03b3b';
const GRID = '#e5e9f0';
const AXIS = '#94a3b8';

export type BarRow = { label: string; cell: Cell | null; sublabel?: string };

export function Bars({
  rows,
  format = 'recall',
  unit,
  signed = false,
}: {
  rows: BarRow[];
  format?: 'recall' | 'f1' | 'delta' | 'deltaF1' | 'pct';
  unit?: string;
  signed?: boolean;
}) {
  const values = rows
    .map((r) => r.cell?.value)
    .filter((v): v is number => typeof v === 'number' && !Number.isNaN(v));
  const bounds = rows.flatMap((r) =>
    r.cell ? [r.cell.value, r.cell.ciLow, r.cell.ciHigh].filter((v): v is number => typeof v === 'number') : [],
  );
  if (!values.length) {
    return <p className="text-xs text-slate-500">No value in this run to plot.</p>;
  }
  const max = Math.max(...bounds, signed ? 0 : 0);
  const min = Math.min(...bounds, 0);
  const span = max - min || 1;
  const zero = ((0 - min) / span) * 100;

  return (
    <div className="space-y-2">
      {rows.map((row) => {
        const cell = row.cell;
        const value = cell?.value ?? null;
        const width = value === null ? 0 : (Math.abs(value) / span) * 100;
        const left = value === null ? zero : value >= 0 ? zero : zero - width;
        const color = signed && value !== null && value < 0 ? NEGATIVE : POSITIVE;
        const lo = cell?.ciLow ?? null;
        const hi = cell?.ciHigh ?? null;
        return (
          <div key={`${row.label}-${row.sublabel ?? ''}`} className="grid grid-cols-[minmax(96px,1.1fr)_minmax(0,2.4fr)_auto] items-center gap-3">
            <div className="min-w-0">
              <p className="truncate text-[11px] font-medium text-slate-700" title={row.label}>
                {row.label}
              </p>
              {row.sublabel ? <p className="truncate text-[10px] text-slate-400">{row.sublabel}</p> : null}
            </div>
            <div className="relative h-6">
              <div className="absolute inset-y-0 w-px" style={{ left: `${zero}%`, background: GRID }} />
              {value !== null ? (
                <div
                  className="absolute top-1.5 h-3 rounded-[4px]"
                  style={{ left: `${left}%`, width: `${Math.max(width, 0.4)}%`, background: color }}
                  title={`${fmt(value, format)}${unit ? ` ${unit}` : ''}`}
                />
              ) : null}
              {lo !== null && hi !== null ? (
                <div
                  className="absolute top-[11px] h-0.5"
                  style={{
                    left: `${((lo - min) / span) * 100}%`,
                    width: `${Math.max(((hi - lo) / span) * 100, 0.3)}%`,
                    background: '#0f172a',
                    opacity: 0.35,
                  }}
                />
              ) : null}
            </div>
            <div className="text-right">
              <span className="font-mono text-[11px] tabular-nums text-slate-800">{fmt(value, format)}</span>
              {lo !== null && hi !== null ? (
                <span className="ml-1.5 font-mono text-[10px] text-slate-400">{ciText(cell, format)}</span>
              ) : null}
            </div>
          </div>
        );
      })}
      {unit ? <p className="pt-1 text-[10px] text-slate-400">Bars show {unit}; the thin rule is the 95% CI.</p> : null}
    </div>
  );
}

export type LinePoint = { x: number; values: (number | null)[] };

export function Lines({
  points,
  seriesLabels,
  xLabel,
  yLabel,
}: {
  points: LinePoint[];
  seriesLabels: string[];
  xLabel: string;
  yLabel: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const width = 720;
  const height = 260;
  const pad = { top: 16, right: 96, bottom: 34, left: 46 };
  const xs = points.map((p) => p.x);
  const ys = points.flatMap((p) => p.values.filter((v): v is number => typeof v === 'number'));
  if (!points.length || !ys.length) return <p className="text-xs text-slate-500">No curve in this run to plot.</p>;
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const yMin = Math.min(...ys);
  const yMax = Math.max(...ys);
  const yLo = yMin - (yMax - yMin) * 0.12;
  const yHi = yMax + (yMax - yMin) * 0.12;
  const px = (x: number) => pad.left + ((x - xMin) / (xMax - xMin || 1)) * (width - pad.left - pad.right);
  const py = (y: number) => pad.top + (1 - (y - yLo) / (yHi - yLo || 1)) * (height - pad.top - pad.bottom);
  const ticks = [yLo, (yLo + yHi) / 2, yHi];

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-4">
        {seriesLabels.map((label, i) => (
          <span key={label} className="inline-flex items-center gap-1.5 text-[11px] text-slate-600">
            <span aria-hidden className="h-0.5 w-4 rounded-full" style={{ background: SERIES[i % SERIES.length] }} />
            {label}
          </span>
        ))}
      </div>
      <div className="scroll-x">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="h-[260px] w-full min-w-[560px]"
          role="img"
          aria-label={`${yLabel} against ${xLabel}`}
          onMouseLeave={() => setHover(null)}
        >
          {ticks.map((t) => (
            <g key={t}>
              <line x1={pad.left} x2={width - pad.right} y1={py(t)} y2={py(t)} stroke={GRID} strokeWidth={1} />
              <text x={pad.left - 8} y={py(t) + 3} textAnchor="end" fontSize={10} fill={AXIS} fontFamily="ui-monospace, monospace">
                {t.toFixed(2)}
              </text>
            </g>
          ))}
          {points.map((p, i) =>
            i % 4 === 0 ? (
              <text key={p.x} x={px(p.x)} y={height - 12} textAnchor="middle" fontSize={10} fill={AXIS} fontFamily="ui-monospace, monospace">
                {p.x.toFixed(2)}
              </text>
            ) : null,
          )}
          <text x={pad.left} y={height - 1} fontSize={10} fill={AXIS}>
            {xLabel}
          </text>
          {seriesLabels.map((label, s) => {
            const path = points
              .map((p, i) => {
                const v = p.values[s];
                if (v === null || v === undefined) return '';
                return `${i === 0 ? 'M' : 'L'}${px(p.x).toFixed(1)},${py(v).toFixed(1)}`;
              })
              .filter(Boolean)
              .join(' ');
            const last = [...points].reverse().find((p) => typeof p.values[s] === 'number');
            return (
              <g key={label}>
                <path d={path} fill="none" stroke={SERIES[s % SERIES.length]} strokeWidth={2} strokeLinecap="round" />
                {last ? (
                  <text
                    x={px(last.x) + 8}
                    y={py(last.values[s] as number) + 3}
                    fontSize={10}
                    fill={SERIES[s % SERIES.length]}
                    fontWeight={600}
                  >
                    {label}
                  </text>
                ) : null}
              </g>
            );
          })}
          {points.map((p, i) => (
            <rect
              key={p.x}
              x={px(p.x) - (width - pad.left - pad.right) / (points.length * 2)}
              y={pad.top}
              width={(width - pad.left - pad.right) / points.length}
              height={height - pad.top - pad.bottom}
              fill="transparent"
              onMouseEnter={() => setHover(i)}
            />
          ))}
          {hover !== null ? (
            <g>
              <line
                x1={px(points[hover].x)}
                x2={px(points[hover].x)}
                y1={pad.top}
                y2={height - pad.bottom}
                stroke={AXIS}
                strokeWidth={1}
                strokeDasharray="3 3"
              />
              {points[hover].values.map((v, s) =>
                typeof v === 'number' ? (
                  <circle key={s} cx={px(points[hover].x)} cy={py(v)} r={4} fill={SERIES[s % SERIES.length]} stroke="#fff" strokeWidth={2} />
                ) : null,
              )}
            </g>
          ) : null}
        </svg>
      </div>
      {hover !== null ? (
        <p className="font-mono text-[11px] text-slate-600">
          {xLabel} {points[hover].x.toFixed(2)} ·{' '}
          {seriesLabels
            .map((label, s) => `${label} ${points[hover].values[s]?.toFixed(4) ?? '—'}`)
            .join('  ·  ')}
        </p>
      ) : (
        <p className="text-[10px] text-slate-400">Hover the curve to read every series at one budget.</p>
      )}
    </div>
  );
}
