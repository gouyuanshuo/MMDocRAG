import { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, Database } from 'lucide-react';
import { api } from '../api';
import type { Provenance } from '../types';
import { Badge, Card, CardContent, CardHeader, CardTitle, Field, Stat } from '../components/ui';

/**
 * Where every number on this page came from, and what it is not.
 *
 * A demo is the easiest place for a claim to drift: a page that shows an answer
 * next to a metric implies the metric scored that answer. Here it does -- but
 * only because the console replays one recorded run and says which. This view
 * exists so an audience can check that rather than take it on trust.
 */

export function ProvenanceView() {
  const [data, setData] = useState<Provenance | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api
      .provenance()
      .then(setData)
      .catch((err) => setError(String(err)));
  }, []);

  if (error) {
    return (
      <div className="mx-auto max-w-[1160px] px-5 py-8 md:px-8">
        <p className="text-sm text-rose-700">{error}</p>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="mx-auto max-w-[1160px] px-5 py-8 md:px-8">
        <p className="text-sm text-slate-500">Loading provenance…</p>
      </div>
    );
  }

  const generation = data.generation as Record<string, unknown>;
  const router = data.router as Record<string, unknown>;
  const action = data.retrieval.actionTable as Record<string, unknown>;

  return (
    <div className="mx-auto max-w-[1160px] space-y-5 px-5 py-8 md:px-8">
      <header>
        <Badge tone="accent" className="mb-3 px-2 py-1">
          <Database className="size-3" /> mode: {data.mode}
        </Badge>
        <h1 className="text-[28px] font-semibold tracking-tight">Provenance</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-500">{data.claim}</p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Questions" value={data.counts.questions.toLocaleString()} hint={`${data.counts.documents} documents`} />
        <Stat label="With a recorded answer" value={data.counts.replayable} hint="the E29 frozen subset" />
        <Stat label="Metrics loaded" value={data.counts.metrics} hint={String(data.metricsRun.run_id ?? '')} />
        <Stat
          label="Image files"
          value={data.imageRoot.available ? 'found' : 'missing'}
          tone={data.imageRoot.available ? 'good' : 'warn'}
          hint={data.imageRoot.available ? undefined : 'see images/README.md'}
        />
      </div>

      {data.errors.length ? (
        <Card className="ring-amber-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-amber-800">
              <AlertTriangle className="size-4" /> Artifacts this console could not read
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1">
              {data.errors.map((err) => (
                <li key={err} className="font-mono text-[11px] text-amber-900">
                  {err}
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-slate-600">
              The affected panels show nothing rather than a substitute value.
            </p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="flex items-center gap-2 py-4 text-sm text-emerald-700">
            <CheckCircle2 className="size-4" /> Every artifact this console needs was read successfully.
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Generation — the answers being replayed</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <dl className="grid gap-4 sm:grid-cols-3 lg:grid-cols-4">
            <Field label="Model" value={String(generation.model)} />
            <Field label="Mode" value={String(generation.mode)} />
            <Field label="Budget k" value={String(generation.k)} />
            <Field label="Pool" value={String(generation.pool)} />
            <Field label="Dense encoder" value={String(generation.dense_model)} />
            <Field label="Questions" value={String(generation.n_questions)} />
            <Field label="Documents" value={String(generation.n_documents)} />
            <Field label="API calls made now" value="0" />
          </dl>
          <p className="rounded-lg bg-slate-50 p-3 text-xs leading-5 text-slate-600">{String(generation.note)}</p>
          <div className="grid gap-3 sm:grid-cols-2">
            {Object.entries((generation.arms ?? {}) as Record<string, Record<string, unknown>>).map(([key, arm]) => (
              <div key={key} className="rounded-lg border border-slate-200 p-3">
                <p className="text-xs font-semibold text-slate-800">{String(arm.label)}</p>
                <p className="mt-1 text-[11px] leading-5 text-slate-500">{String(arm.description)}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Retrieval — where the rankings come from</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <dl className="grid gap-4 sm:grid-cols-3">
            <Field label="Action table" value={<span className="font-mono">{String(action.source ?? '—')}</span>} />
            <Field label="Pool" value={String(action.pool ?? '—')} />
            <Field label="Encoder" value={String(action.denseModel ?? '—')} />
            <Field label="Ranking depth" value={String(action.top ?? '—')} />
            <Field label="Questions" value={String(action.nQuestions ?? '—')} />
          </dl>
          <p className="rounded-lg bg-slate-50 p-3 text-xs leading-5 text-slate-600">{data.retrieval.note}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Routing — the decision file</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-4 sm:grid-cols-3 lg:grid-cols-4">
            <Field label="Source" value={<span className="font-mono break-all">{String(router.source ?? '—')}</span>} />
            <Field label="Experiment" value={String(router.experiment ?? '—')} />
            <Field label="Cheap action" value={String(router.cheap_action ?? '—')} />
            <Field label="Expensive action" value={String(router.expensive_action ?? '—')} />
            <Field label="Features" value={String(router.features ?? '—')} />
            <Field label="Folds" value={`${router.folds ?? '—'} outer / ${router.inner_folds ?? '—'} inner`} />
            <Field label="Questions" value={String(router.n_questions ?? '—')} />
            <Field
              label="Escalation rates"
              value={Object.entries((router.escalationRates ?? {}) as Record<string, number>)
                .map(([b, rate]) => `B=${(Number(b) / 1000).toFixed(2)}: ${(rate * 100).toFixed(0)}%`)
                .join(' · ')}
            />
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>What this console does not show</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-2">
            {data.caveats.map((caveat) => (
              <li key={caveat} className="flex gap-2 text-xs leading-5 text-slate-600">
                <span aria-hidden className="mt-[7px] size-1 shrink-0 rounded-full bg-slate-400" />
                <span>{caveat}</span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
