import { useEffect, useState } from 'react';
import { api } from '../api';
import type { Group, RegistryEntry } from '../types';
import { Badge, Card, CardContent, CardHeader, CardTitle, Notes, cx } from '../components/ui';
import { DataTable } from '../components/DataTable';

/**
 * The dashboard: five groups of recorded comparisons, then the registry.
 *
 * The groups replace the original UI's fixture tabs (overview / modality /
 * retriever / granularity / top-k) with the comparisons this project actually
 * ran. Two of those fixture tabs had no experiment behind them here, and
 * inventing rows to fill a tab is exactly how a demo starts lying.
 */

const GROUP_LABELS: Record<string, string> = {
  'end-to-end': 'End-to-end (E29)',
  retrieval: 'Retrieval stack (E27/E40/E41)',
  visual: 'Visual branch (E24/E34)',
  slices: 'Question slices (E37)',
  routing: 'Routing budget (E35/E36)',
};

export function ExperimentsView() {
  const [groups, setGroups] = useState<{ id: string; title: string }[]>([]);
  const [registry, setRegistry] = useState<RegistryEntry[]>([]);
  const [active, setActive] = useState('end-to-end');
  const [group, setGroup] = useState<Group | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [showRegistry, setShowRegistry] = useState(false);

  useEffect(() => {
    api
      .experiments()
      .then((data) => {
        setGroups(data.groups);
        setRegistry(data.registry);
      })
      .catch((err) => setError(String(err)));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    setGroup(null);
    api
      .results(active)
      .then((data) => {
        if (!cancelled) setGroup(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [active]);

  return (
    <div className="mx-auto max-w-[1160px] space-y-5 px-5 py-8 md:px-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <Badge tone="accent" className="mb-3 px-2 py-1">
            Recorded metrics · run {String(group?.source.run ?? '…')}
          </Badge>
          <h1 className="text-[28px] font-semibold tracking-tight">Experiment dashboard</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-500">
            Every row is a number a recorded run wrote, with the interval, the sample unit and the n it was measured
            with. Rows the run did not measure say so rather than showing a blank.
          </p>
        </div>
        <button
          onClick={() => setShowRegistry((v) => !v)}
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium"
        >
          {showRegistry ? 'Hide' : 'Show'} all {registry.length} experiments
        </button>
      </div>

      {showRegistry ? <Registry entries={registry} /> : null}

      <Card>
        <CardHeader className="pb-0">
          <div className="flex gap-1 overflow-x-auto">
            {(groups.length ? groups : Object.keys(GROUP_LABELS).map((id) => ({ id, title: id }))).map((g) => (
              <button
                key={g.id}
                onClick={() => setActive(g.id)}
                className={cx(
                  'border-b-2 px-4 pb-3 text-xs font-medium whitespace-nowrap',
                  active === g.id ? 'border-violet-600 text-violet-700' : 'border-transparent text-slate-500 hover:text-slate-800',
                )}
              >
                {GROUP_LABELS[g.id] ?? g.title}
              </button>
            ))}
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {loading ? <p className="text-sm text-slate-500">Reading the recorded metrics…</p> : null}
          {error ? (
            <p role="alert" className="text-sm text-rose-700">
              {error}
            </p>
          ) : null}
          {group ? (
            <>
              <div>
                <h2 className="text-lg font-semibold tracking-tight">{group.title}</h2>
                <p className="mt-1 max-w-3xl text-xs leading-5 text-slate-500">{group.subtitle}</p>
                <p className="mt-2 flex flex-wrap gap-1.5">
                  {group.source.experiments.map((id) => (
                    <Badge key={id} tone="outline">
                      {id}
                    </Badge>
                  ))}
                </p>
              </div>
              <Notes title="How to read this" items={group.notes} />
              {group.tables.map((table) => (
                <DataTable key={table.id} table={table} />
              ))}
            </>
          ) : null}
        </CardContent>
      </Card>

      {group ? (
        <Card>
          <CardHeader>
            <CardTitle>Standing caveats</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {group.caveats.map((caveat) => (
                <li key={caveat} className="flex gap-2 text-xs leading-5 text-slate-600">
                  <span aria-hidden className="mt-[7px] size-1 shrink-0 rounded-full bg-slate-400" />
                  <span>{caveat}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

const STATUS_TONE: Record<string, 'good' | 'bad' | 'warn' | 'neutral' | 'accent'> = {
  pos: 'good',
  neg: 'bad',
  correct: 'warn',
  fix: 'accent',
  pass: 'neutral',
  pending: 'neutral',
};

function Registry({ entries }: { entries: RegistryEntry[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Every experiment in the registry</CardTitle>
      </CardHeader>
      <CardContent className="scroll-x">
        <table className="w-full min-w-[720px] text-left">
          <thead>
            <tr className="border-b border-slate-200 text-[10px] tracking-wider text-slate-400 uppercase">
              {['ID', 'Phase', 'Status', 'Title', 'Current conclusion'].map((h) => (
                <th key={h} className="px-3 py-2 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.id} className="border-b border-slate-100 align-top last:border-0">
                <td className="px-3 py-2 font-mono text-xs text-slate-700">{entry.id}</td>
                <td className="px-3 py-2 text-xs text-slate-500">{entry.phase}</td>
                <td className="px-3 py-2">
                  <Badge tone={STATUS_TONE[entry.status] ?? 'neutral'}>{entry.statusLabel}</Badge>
                  {entry.hasCorrections ? (
                    <Badge tone="warn" className="ml-1" title="This entry carries superseded numbers.">
                      corrected
                    </Badge>
                  ) : null}
                </td>
                <td className="max-w-[280px] px-3 py-2 text-xs text-slate-700">{entry.title}</td>
                <td className="max-w-[420px] px-3 py-2 text-[11px] leading-5 text-slate-500">
                  {entry.result ? entry.result.replace(/\s+/g, ' ').slice(0, 260) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
