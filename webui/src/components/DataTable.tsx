import type { Cell, Column, Table } from '../types';
import { asCell, ci as ciText, fmt, verdict } from '../format';
import { Badge } from './ui';
import { Bars, Lines, type BarRow } from './charts';

/**
 * One renderer for every dashboard table.
 *
 * The server sends columns, rows and an optional chart spec, so a table added on
 * the Python side needs no change here. Whatever the artifact recorded is what
 * shows: a cell with no interval prints no interval, and a cell the run never
 * measured prints "not measured in this run" instead of an empty-looking dash
 * that could be mistaken for zero.
 */

function CellValue({ cell, format }: { cell: Cell; format: Column['format'] }) {
  if (cell.missing) {
    return <span className="text-[10px] text-slate-400 italic">not measured in this run</span>;
  }
  const interval = ciText(cell, format);
  const v = verdict(cell);
  return (
    <div className="space-y-0.5">
      <div className="font-mono text-xs tabular-nums text-slate-800">{fmt(cell.value, format)}</div>
      {interval ? (
        <div className="flex items-center gap-1.5">
          <span className="font-mono text-[10px] text-slate-500">{interval}</span>
          {v.tone === 'touches-zero' ? (
            <Badge tone="warn" title="A CI whose lower bound touches zero is not significant.">
              CI includes 0
            </Badge>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function PValue({ cell }: { cell: Cell }) {
  if (cell.missing || (cell.pHolm === null && cell.pRaw === null)) {
    return <span className="text-[10px] text-slate-400">—</span>;
  }
  const holm = cell.pHolm;
  return (
    <div className="space-y-0.5">
      <div className="font-mono text-xs tabular-nums text-slate-700">
        {fmt(holm ?? cell.pRaw, 'p')}
        <span className="ml-1 text-[10px] text-slate-400">{holm !== null ? 'Holm' : 'raw'}</span>
      </div>
      {cell.significant === false ? <Badge tone="neutral">not significant</Badge> : null}
    </div>
  );
}

function renderCell(row: Record<string, unknown>, column: Column) {
  const raw = row[column.key];
  if (column.format === 'text') {
    const text = raw === null || raw === undefined ? '—' : String(raw);
    return <span className="text-xs text-slate-700">{text}</span>;
  }
  const cell = asCell(raw);
  if (!cell) {
    return <span className="text-xs text-slate-500">{raw === null || raw === undefined ? '—' : String(raw)}</span>;
  }
  return column.variant === 'p' ? <PValue cell={cell} /> : <CellValue cell={cell} format={column.format} />;
}

function chartFor(table: Table) {
  const spec = table.chart;
  if (!spec) return null;
  if (spec.kind === 'line' && spec.xKey && spec.seriesKeys) {
    const points = table.rows.map((row) => ({
      x: Number(row[spec.xKey as string] ?? 0),
      values: (spec.seriesKeys as string[]).map((key) => asCell(row[key])?.value ?? null),
    }));
    return <Lines points={points} seriesLabels={spec.seriesKeys as string[]} xLabel="GPU budget B" yLabel={spec.unit ?? 'recall'} />;
  }
  if (spec.kind === 'bar' && spec.valueKey && spec.labelKey) {
    const rows = table.rows.filter((row) =>
      spec.filterKey ? String(row[spec.filterKey]) === spec.filterValue : true,
    );
    const bars: BarRow[] = rows.map((row) => ({
      label: String(row[spec.labelKey as string] ?? ''),
      sublabel: spec.groupKey ? String(row[spec.groupKey] ?? '') : undefined,
      cell: asCell(row[spec.valueKey as string]),
    }));
    const column = table.columns.find((c) => c.key === spec.valueKey);
    const format = (column?.format ?? 'recall') as 'recall' | 'f1' | 'delta' | 'deltaF1' | 'pct';
    return (
      <Bars
        rows={bars}
        format={format}
        signed={format === 'delta' || format === 'deltaF1'}
        unit={spec.unit ?? undefined}
      />
    );
  }
  return null;
}

export function DataTable({ table }: { table: Table }) {
  const chart = chartFor(table);
  return (
    <section className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-slate-900">{table.title}</h3>
        {table.subtitle ? <p className="mt-1 max-w-3xl text-xs leading-5 text-slate-500">{table.subtitle}</p> : null}
      </div>
      {chart ? <div className="rounded-xl bg-[#f8f9fc] p-4">{chart}</div> : null}
      {table.rows.length === 0 ? (
        <p className="text-xs text-slate-500">This run recorded no rows for this table.</p>
      ) : (
        <div className="scroll-x">
          <table className="w-full min-w-[640px] text-left">
            <thead>
              <tr className="border-b border-slate-200 text-[10px] tracking-wider text-slate-400 uppercase">
                {table.columns.map((column, i) => (
                  <th key={`${column.key}-${i}`} className="px-3 py-2 font-medium">
                    {column.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row, r) => (
                <tr key={r} className="border-b border-slate-100 align-top last:border-0">
                  {table.columns.map((column, c) => (
                    <td key={`${column.key}-${c}`} className="px-3 py-2.5">
                      {renderCell(row, column)}
                      {c === 0 && row.n ? <NRow n={row.n as Record<string, unknown>} /> : null}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function NRow({ n }: { n: Record<string, unknown> }) {
  const questions = n.questions as number | null;
  const documents = n.documents as number | null;
  const unit = n.sampleUnit as string | null;
  if (!questions && !documents) return null;
  return (
    <p className="mt-1 text-[10px] text-slate-400">
      {questions ? `${questions.toLocaleString()} questions` : ''}
      {questions && documents ? ' · ' : ''}
      {documents ? `${documents} documents` : ''}
      {unit ? ` · resampled by ${unit}` : ''}
    </p>
  );
}
