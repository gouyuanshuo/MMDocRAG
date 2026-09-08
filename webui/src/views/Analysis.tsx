import { useEffect, useState } from 'react';
import { Layers, Scale } from 'lucide-react';
import { api } from '../api';
import type { RetrieverComparison, Turn } from '../types';
import { Badge, Card, CardContent, CardHeader, CardTitle, Empty, Field, Stat } from '../components/ui';
import { AnswerBody } from '../components/Answer';
import { EvidenceList } from '../components/EvidenceList';

/**
 * The paired view: the same question, two retrieval configurations, one model.
 *
 * This is E29's design made visible. Both columns share the question, the gold
 * set, the model and the prompt; the only difference is the candidate block, so
 * the F1 difference between them is attributable to retrieval and nothing else.
 */

export function AnalysisView({ turn }: { turn: Turn | null }) {
  const [retrievers, setRetrievers] = useState<RetrieverComparison | null>(null);
  const uid = turn?.match.questionUid;

  useEffect(() => {
    let cancelled = false;
    setRetrievers(null);
    if (!uid) return;
    api
      .retrievers(uid, 10)
      .then((data) => {
        if (!cancelled) setRetrievers(data);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [uid]);

  if (!turn) {
    return (
      <div className="mx-auto max-w-[1160px] px-5 py-10 md:px-8">
        <Empty>Replay a question in RAG Replay first — this view analyses the most recent one.</Empty>
      </div>
    );
  }

  const replay = turn.replay;
  const ours = replay.arms.ours;
  const paper = replay.arms.paper;

  return (
    <div className="mx-auto max-w-[1160px] space-y-6 px-5 py-8 md:px-8">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="accent">{replay.questionUid}</Badge>
          {replay.questionType ? <Badge tone="outline">{replay.questionType}</Badge> : null}
          {replay.evidenceModality.map((m) => (
            <Badge key={m} tone="neutral">
              {m}
            </Badge>
          ))}
          <span className="text-[11px] text-slate-500">{replay.docName}</span>
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">{replay.question}</h1>
        {replay.answerShort ? (
          <p className="text-sm text-slate-500">
            Reference short answer: <span className="font-medium text-slate-700">{replay.answerShort}</span>
          </p>
        ) : null}
      </header>

      {replay.retrieval ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Text pool" value={replay.retrieval.poolText} hint="chunks in this document" />
          <Stat label="Image pool" value={replay.retrieval.poolVisual} hint="candidate images" />
          <Stat
            label="Gold evidence"
            value={`${replay.retrieval.goldText} text / ${replay.retrieval.goldVisual} image`}
            hint={`${replay.retrieval.goldUnmapped} unmapped, counted as misses`}
          />
          <Stat
            label="ColQwen ranking"
            value={replay.retrieval.hasColqwen ? 'available' : 'absent'}
            hint="GPU visual retriever"
          />
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Scale className="size-4 text-violet-600" /> Paired comparison — same question, same model, same prompt
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-6 lg:grid-cols-2">
          {[ours, paper].map((arm, index) =>
            arm ? (
              <section key={arm.label} className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold text-slate-900">{arm.label}</p>
                    <p className="text-[11px] text-slate-500">{arm.description}</p>
                  </div>
                  <Badge tone={index === 0 ? 'accent' : 'neutral'}>
                    citation F1 {arm.citationF1 === null ? '—' : arm.citationF1.toFixed(2)}
                  </Badge>
                </div>
                <dl className="grid grid-cols-3 gap-2 rounded-lg bg-slate-50 p-3">
                  <Field label="Text" value={arm.config.textRetriever} />
                  <Field
                    label="Visual"
                    value={
                      arm.config.visualRetriever === 'colqwen'
                        ? 'colqwen (pixels)'
                        : `${arm.config.visualRetriever} (descriptions)`
                    }
                  />
                  <Field label="Quota" value={`${arm.config.quotaText}/${arm.config.quotaVisual}`} />
                </dl>
                <div className="max-h-[420px] overflow-y-auto rounded-xl border border-slate-200 p-4">
                  <AnswerBody
                    text={arm.answer}
                    citations={index === 0 ? turn.citations : turn.baseline.citations}
                  />
                </div>
                <p className="text-[11px] text-slate-500">
                  {arm.counts.goldRetrieved}/{arm.counts.goldTotal} gold quotes retrieved ·{' '}
                  {arm.counts.quotesShown} quotes shown · {arm.tokens?.totalTok?.toLocaleString() ?? '—'} tokens
                </p>
              </section>
            ) : null,
          )}
        </CardContent>
      </Card>

      {replay.paired ? (
        <div className="rounded-xl border border-slate-200 bg-white p-4 text-xs text-slate-600">
          Paired difference on this question:{' '}
          <span className="font-mono font-semibold text-slate-900">
            {replay.paired.deltaF1 === null
              ? '—'
              : `${replay.paired.deltaF1 >= 0 ? '+' : '−'}${Math.abs(replay.paired.deltaF1).toFixed(3)}`}
          </span>{' '}
          — {replay.paired.metric}. One question is an anecdote; the interval that matters is over 220 documents and
          lives in the Experiments tab.
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Layers className="size-4 text-violet-600" /> What each retriever would have surfaced (top 10)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          {!retrievers ? (
            <p className="text-xs text-slate-500">Loading rankings…</p>
          ) : (
            Object.entries(retrievers.branches).map(([branch, data]) => (
              <div key={branch} className="space-y-2">
                <p className="text-xs font-semibold text-slate-700">
                  {branch === 'visual' ? 'Visual branch' : 'Text branch'}{' '}
                  <span className="font-normal text-slate-400">
                    · pool {data.pool} · {data.goldTotal} gold
                  </span>
                </p>
                <div className="space-y-1.5">
                  {data.retrievers.map((entry) => (
                    <div
                      key={entry.retriever}
                      className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 px-3 py-2"
                    >
                      <Badge tone={entry.readsPixels ? 'accent' : 'outline'}>{entry.retriever}</Badge>
                      <span className="text-[11px] text-slate-500">{entry.representation}</span>
                      <span className="ml-auto font-mono text-[11px] text-slate-700">
                        {entry.goldInTopK}/{data.goldTotal} gold in top 10
                      </span>
                      <div className="flex w-full gap-0.5">
                        {entry.topK.map((item, i) => (
                          <span
                            key={`${item.evidenceId}-${i}`}
                            title={`${i + 1}. ${item.evidenceId}${item.isGold ? ' (gold)' : ''}`}
                            className={`h-1.5 flex-1 rounded-full ${item.isGold ? 'bg-emerald-500' : 'bg-slate-200'}`}
                          />
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))
          )}
          <p className="text-[10px] text-slate-400">
            Rankings come from the cached action table built by the same code E27 reports. ColQwen is listed on the
            visual branch only — it never ranks text.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Candidate block, in rank order</CardTitle>
        </CardHeader>
        <CardContent>
          <EvidenceList citations={turn.citations} />
        </CardContent>
      </Card>
    </div>
  );
}
