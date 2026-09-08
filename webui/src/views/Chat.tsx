import { useEffect, useRef, useState } from 'react';
import { ArrowUp, Bot, Search, Sparkles } from 'lucide-react';
import { api } from '../api';
import type { Question, Turn } from '../types';
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Field, Stat, cx } from '../components/ui';
import { AnswerBody } from '../components/Answer';
import { EvidenceList } from '../components/EvidenceList';
import { pctString } from '../format';

/**
 * The replay console.
 *
 * A free-text question is matched to a benchmark question and that question's
 * recorded run is shown -- the answer the model produced, the candidate block it
 * saw, and what the scorer made of it. The match is stated in the transcript
 * rather than implied, because answering a *different* question than the one
 * typed would otherwise look like a live system.
 */

export function ChatView({
  turns,
  current,
  loading,
  onAsk,
}: {
  turns: Turn[];
  current: Turn | null;
  loading: boolean;
  onAsk: (question: string, questionUid?: string) => void;
}) {
  const [question, setQuestion] = useState('');
  const [search, setSearch] = useState('');
  const [hits, setHits] = useState<Question[]>([]);
  const [picking, setPicking] = useState(false);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [turns.length, loading]);

  useEffect(() => {
    let cancelled = false;
    if (!search.trim()) {
      setHits([]);
      return;
    }
    const timer = setTimeout(() => {
      api
        .questions(search, 8)
        .then((data) => {
          if (!cancelled) setHits(data.items);
        })
        .catch(() => {
          if (!cancelled) setHits([]);
        });
    }, 220);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [search]);

  const metrics = current?.metrics;
  const counts = metrics?.counts;
  const routing = current?.routing;

  return (
    <div className="mx-auto flex min-h-[calc(100vh-68px)] max-w-[1160px] flex-col px-5 py-8 md:px-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <Badge tone="accent" className="mb-3 px-2 py-1">
            <Sparkles className="size-3" /> Replay of a recorded run — no model is called
          </Badge>
          <h1 className="text-2xl font-semibold tracking-tight md:text-[28px]">Ask the benchmark corpus</h1>
          <p className="mt-1.5 max-w-2xl text-sm text-slate-500">
            600 of the 2,000 evaluation questions were answered end to end by gemini-3.6-flash under two retrieval
            configurations. Ask one of them and the console replays what happened: the evidence retrieved, the answer
            produced, and what the scorer made of it.
          </p>
        </div>
        <span className="hidden font-mono text-[10px] tracking-wider text-slate-400 uppercase md:block">
          {current?.queryId ?? 'no query sent'}
        </span>
      </div>

      <div className="grid flex-1 gap-5 xl:grid-cols-[minmax(0,1.6fr)_320px]">
        <div className="space-y-5">
          <Card>
            <CardContent className="p-0">
              <div className="max-h-[62vh] space-y-8 overflow-y-auto p-6 md:p-8" role="log" aria-label="Replayed turns">
                {turns.length === 0 && !loading ? (
                  <p className="text-sm text-slate-500">
                    Start by browsing the recorded questions below, or type one and the closest match is replayed.
                  </p>
                ) : null}

                {turns.map((turn) => (
                  <article key={turn.turnId} className="space-y-5">
                    <div className="ml-auto max-w-[76%] rounded-2xl rounded-tr-md bg-[#eff1f7] px-4 py-3 text-sm leading-6 whitespace-pre-wrap">
                      {turn.question}
                    </div>

                    {!turn.match.exact ? (
                      <div className="rounded-xl border border-sky-200 bg-sky-50/70 px-4 py-3 text-xs text-sky-900">
                        Matched to benchmark question{' '}
                        <span className="font-mono">{turn.match.questionUid}</span> by BM25 over the question texts
                        (score {turn.match.score?.toFixed(2)}). The replay below answers that question, not the exact
                        wording typed.
                        <p className="mt-1 font-medium">“{turn.match.question}”</p>
                      </div>
                    ) : null}

                    <div className="flex gap-3">
                      <div className="grid size-8 shrink-0 place-items-center rounded-lg bg-[#6d5dfc] text-white">
                        <Bot className="size-4" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="mb-2 text-sm font-semibold">
                          Recorded answer
                          <span className="ml-2 text-[11px] font-normal text-slate-400">
                            {turn.metrics.tokens?.model ?? 'gemini-3.6-flash'} · replayed from response/
                          </span>
                        </p>
                        <AnswerBody text={turn.answer} citations={turn.citations} />

                        <div className="mt-5 grid gap-3 sm:grid-cols-4">
                          <Stat
                            label="Citation F1"
                            value={turn.metrics.citationF1 === null ? '—' : turn.metrics.citationF1.toFixed(2)}
                            hint="quote selection, not correctness"
                          />
                          <Stat
                            label="Baseline arm"
                            value={
                              turn.metrics.baselineCitationF1 === null ? '—' : turn.metrics.baselineCitationF1.toFixed(2)
                            }
                            hint="paper-style config"
                          />
                          <Stat
                            label="Gold retrieved"
                            value={`${turn.metrics.counts.goldRetrieved}/${turn.metrics.counts.goldTotal}`}
                            hint="unmapped gold counts as a miss"
                          />
                          <Stat
                            label="Tokens"
                            value={turn.metrics.tokens?.totalTok?.toLocaleString() ?? '—'}
                            hint="measured, not estimated"
                          />
                        </div>
                      </div>
                    </div>

                    <details className="rounded-xl border border-slate-200 bg-slate-50/60 p-4">
                      <summary className="cursor-pointer text-xs font-medium text-slate-700">
                        Candidate block shown to the model ({turn.citations.length} quotes,{' '}
                        {turn.citations.filter((c) => c.isGold).length} gold)
                      </summary>
                      <div className="mt-3">
                        <EvidenceList citations={turn.citations} compact />
                      </div>
                    </details>
                  </article>
                ))}

                {loading ? (
                  <p role="status" className="text-sm text-slate-500">
                    Reading the recorded run…
                  </p>
                ) : null}
                <div ref={end} />
              </div>

              <div className="border-t border-slate-100 p-4 md:p-5">
                <details open={turns.length === 0} className="mb-3">
                  <summary className="cursor-pointer text-xs font-medium text-slate-600">
                    Browse the 600 recorded questions
                  </summary>
                  <div className="mt-2">
                    <QuestionPicker
                      search={search}
                      setSearch={setSearch}
                      hits={hits}
                      picking={picking}
                      setPicking={setPicking}
                      onPick={(hit) => {
                        setSearch('');
                        setHits([]);
                        onAsk(hit.question, hit.questionUid);
                      }}
                    />
                  </div>
                </details>
                <div className="relative rounded-2xl border border-slate-200 bg-white p-2 shadow-[0_8px_30px_rgba(30,41,59,0.07)] focus-within:border-violet-300 focus-within:ring-4 focus-within:ring-violet-50">
                  <textarea
                    disabled={loading}
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    maxLength={2000}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                        e.preventDefault();
                        onAsk(question);
                        setQuestion('');
                      }
                    }}
                    aria-label="Ask a question"
                    placeholder="Ask a question from the benchmark, or describe one…"
                    className="min-h-[72px] w-full resize-none border-0 bg-transparent px-3 py-2 pr-12 text-sm outline-none"
                  />
                  <Button
                    onClick={() => {
                      onAsk(question);
                      setQuestion('');
                    }}
                    disabled={loading || !question.trim()}
                    ariaLabel="Send question"
                    className="absolute right-3 bottom-3 rounded-xl px-2.5 py-2"
                  >
                    <ArrowUp className="size-4" />
                  </Button>
                </div>
                <p className="mt-2 text-center text-[10px] text-slate-400">
                  Replayed from recorded artifacts · Enter to send · Shift+Enter for a new line
                </p>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-5">
          <Card className="border-0 bg-[#17213a] text-white ring-0">
            <CardHeader className="border-white/10 pb-4">
              <div className="flex items-center justify-between">
                <CardTitle className="text-white">Retrieval configuration</CardTitle>
                <Badge tone="good" className="bg-emerald-400/10 text-emerald-300">
                  {loading ? 'loading' : current ? 'replayed' : 'ready'}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-3 px-4 py-4">
              {routing ? (
                <>
                  <dl className="grid grid-cols-2 gap-3">
                    <Dark label="Text branch" value={routing.static.textRetriever} />
                    <Dark
                      label="Visual branch"
                      value={
                        routing.static.visualRetriever === 'colqwen'
                          ? 'colqwen (pixels)'
                          : `${routing.static.visualRetriever} (descriptions)`
                      }
                    />
                    <Dark label="Quota" value={`${routing.static.quotaText} text / ${routing.static.quotaVisual} image`} />
                    <Dark label="Budget k" value={String(routing.static.topK)} />
                    <Dark label="Pool" value={routing.static.pool} />
                    <Dark label="Encoder" value={routing.static.denseModel.split('/').pop() ?? ''} />
                  </dl>
                  <p className="rounded-lg bg-white/5 p-3 text-[11px] leading-5 text-slate-300">
                    {routing.static.selectedBy}. This configuration is the same for every question — the per-question
                    decision this project measured is the GPU escalation below, and it is a cost result.
                  </p>
                </>
              ) : (
                <p className="text-xs text-slate-400">Ask a question to see the configuration that produced it.</p>
              )}
            </CardContent>
          </Card>

          {routing?.perQuestion ? (
            <Card>
              <CardHeader>
                <CardTitle>Per-question routing (E36)</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <dl className="grid grid-cols-2 gap-3">
                  <Field label="Predicted gain" value={routing.perQuestion.predictedGain?.toFixed(4) ?? '—'} />
                  <Field label="Actual gain" value={routing.perQuestion.trueGain?.toFixed(4) ?? '—'} />
                  <Field label="Cheap action recall" value={routing.perQuestion.recallCheap?.toFixed(3) ?? '—'} />
                  <Field label="Expensive action recall" value={routing.perQuestion.recallExpensive?.toFixed(3) ?? '—'} />
                </dl>
                <div className="space-y-1.5">
                  {Object.entries(routing.perQuestion.escalate).map(([budget, flag]) => (
                    <div key={budget} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
                      <span className="text-[11px] text-slate-600">
                        Budget B = {(Number(budget) / 1000).toFixed(2)} ·{' '}
                        {pctString(routing.perQuestion?.rates?.[budget])} of questions escalate
                      </span>
                      <Badge tone={flag ? 'accent' : 'neutral'}>{flag ? 'escalates to GPU' : 'stays on CPU'}</Badge>
                    </div>
                  ))}
                </div>
                <p className="text-[10px] leading-4 text-slate-500">
                  Read from the decision file the experiment wrote, not re-derived here.
                </p>
              </CardContent>
            </Card>
          ) : null}

          {counts ? (
            <Card>
              <CardHeader>
                <CardTitle>This question's denominators</CardTitle>
              </CardHeader>
              <CardContent className="grid grid-cols-2 gap-3">
                <Stat label="Gold total" value={counts.goldTotal} />
                <Stat label="Gold retrieved" value={counts.goldRetrieved} />
                <Stat label="Gold unmapped" value={counts.goldUnmapped} hint="counted as a miss" />
                <Stat label="Quotes shown" value={counts.quotesShown} />
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function Dark({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[10px] tracking-wider text-slate-500 uppercase">{label}</dt>
      <dd className="mt-0.5 font-mono text-xs text-slate-100">{value}</dd>
    </div>
  );
}

function QuestionPicker({
  search,
  setSearch,
  hits,
  picking,
  setPicking,
  onPick,
}: {
  search: string;
  setSearch: (v: string) => void;
  hits: Question[];
  picking: boolean;
  setPicking: (v: boolean) => void;
  onPick: (hit: Question) => void;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4">
      <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2">
        <Search className="size-4 text-slate-400" />
        <input
          value={search}
          onFocus={() => setPicking(true)}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search the 600 recorded questions (BM25 over question text)…"
          className="w-full border-0 bg-transparent text-xs outline-none"
        />
      </div>
      <div className={cx('mt-3 space-y-1.5', !picking && !hits.length && 'hidden')}>
        {hits.map((hit) => (
          <button
            key={hit.questionUid}
            onClick={() => onPick(hit)}
            className="block w-full rounded-lg border border-slate-200 bg-white p-3 text-left hover:border-violet-300"
          >
            <p className="text-xs font-medium text-slate-800">{hit.question}</p>
            <p className="mt-1 flex flex-wrap items-center gap-2 text-[10px] text-slate-500">
              <span className="font-mono">{hit.questionUid}</span>
              <span>{hit.docName}</span>
              {hit.questionType ? <Badge tone="outline">{hit.questionType}</Badge> : null}
              {hit.evidenceModality.map((m) => (
                <Badge key={m} tone="neutral">
                  {m}
                </Badge>
              ))}
              <span>{hit.goldCount} gold quotes</span>
            </p>
          </button>
        ))}
        {search && !hits.length ? <p className="text-[11px] text-slate-500">No question matched that text.</p> : null}
      </div>
    </div>
  );
}
