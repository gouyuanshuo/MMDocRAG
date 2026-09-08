import { useCallback, useEffect, useRef, useState } from 'react';
import { BarChart3, Braces, FileSearch, Layers3, MessageSquareText, Plus, SearchCheck, ShieldCheck } from 'lucide-react';
import { api } from './api';
import type { Health, RecentRun, Turn } from './types';
import { Button, cx } from './components/ui';
import { ChatView } from './views/Chat';
import { AnalysisView } from './views/Analysis';
import { ExperimentsView } from './views/Experiments';
import { ProvenanceView } from './views/Provenance';

const ROUTES = [
  { id: 'chat', label: 'RAG Replay', icon: MessageSquareText, blurb: 'Ask a benchmark question and see the recorded run' },
  { id: 'analysis', label: 'Query Analysis', icon: SearchCheck, blurb: 'Both arms, every retriever, and the routing decision' },
  { id: 'experiments', label: 'Experiments', icon: BarChart3, blurb: 'What each experiment measured, with its interval' },
  { id: 'provenance', label: 'Provenance', icon: ShieldCheck, blurb: 'Which artifact every number on this page came from' },
] as const;

type RouteId = (typeof ROUTES)[number]['id'];

export default function App() {
  const [active, setActive] = useState<RouteId>('chat');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [current, setCurrent] = useState<Turn | null>(null);
  const [runs, setRuns] = useState<RecentRun[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const busy = useRef(false);

  const refreshRuns = useCallback(async () => {
    try {
      const data = await api.recentRuns();
      setRuns(data.runs);
    } catch {
      /* the sidebar list is a convenience; a failure here must not block asking */
    }
  }, []);

  useEffect(() => {
    void refreshRuns();
    api.health().then(setHealth).catch(() => setHealth(null));
  }, [refreshRuns]);

  const ask = useCallback(
    async (question: string, questionUid?: string) => {
      if (busy.current || !question.trim()) return;
      busy.current = true;
      setLoading(true);
      setError('');
      try {
        const turn = await api.ask(question.trim(), current?.queryId, questionUid);
        setCurrent(turn);
        setTurns((previous) => [...previous, turn]);
        void refreshRuns();
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Request failed');
      } finally {
        busy.current = false;
        setLoading(false);
      }
    },
    [current?.queryId, refreshRuns],
  );

  const openRun = useCallback(async (queryId: string) => {
    if (busy.current) return;
    busy.current = true;
    setLoading(true);
    setError('');
    try {
      const conversation = await api.conversation(queryId);
      setTurns(conversation.turns);
      setCurrent(conversation.turns[conversation.turns.length - 1] ?? null);
      setActive('chat');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not open this run');
    } finally {
      busy.current = false;
      setLoading(false);
    }
  }, []);

  const route = ROUTES.find((r) => r.id === active)!;

  return (
    <main className="min-h-screen bg-[#f5f7fb] text-[#172033]">
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-[252px] flex-col bg-[#111c35] px-4 py-5 text-white lg:flex">
        <div className="flex items-center gap-3 px-2">
          <div className="grid size-10 place-items-center rounded-xl bg-[#6d5dfc] shadow-lg shadow-violet-950/30">
            <Layers3 className="size-5" />
          </div>
          <div>
            <p className="text-sm font-semibold tracking-tight">Hierarchical RAG</p>
            <p className="text-[11px] text-slate-400">MMDocRAG research console</p>
          </div>
        </div>

        <Button
          variant="ghost"
          className="mt-7 h-10 justify-start px-3"
          disabled={loading}
          onClick={() => {
            setActive('chat');
            setTurns([]);
            setCurrent(null);
            setError('');
          }}
        >
          <Plus className="size-4" /> New query
        </Button>

        <nav className="mt-6 space-y-1" aria-label="Primary navigation">
          {ROUTES.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActive(id)}
              className={cx(
                'flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition',
                active === id ? 'bg-[#6d5dfc] text-white' : 'text-slate-300 hover:bg-white/10 hover:text-white',
              )}
            >
              <Icon className="size-4" />
              {label}
            </button>
          ))}
        </nav>

        <div className="mt-7 border-t border-white/10 pt-5">
          <div className="flex items-center justify-between px-3">
            <p className="text-[10px] font-semibold tracking-[0.18em] text-slate-500 uppercase">Recent replays</p>
            <button
              onClick={() => void refreshRuns()}
              disabled={loading}
              className="text-xs text-slate-400 hover:text-white disabled:opacity-50"
            >
              Refresh
            </button>
          </div>
          {runs.length === 0 ? (
            <p className="px-3 py-2 text-xs text-slate-400">No replays yet. Ask your first question.</p>
          ) : null}
          <div className="mt-3 max-h-[32vh] space-y-1 overflow-y-auto">
            {runs.map((run, index) => (
              <button
                key={run.queryId}
                onClick={() => void openRun(run.queryId)}
                disabled={loading}
                title={run.question}
                aria-current={current?.queryId === run.queryId ? 'true' : undefined}
                className={cx(
                  'w-full truncate rounded-lg px-3 py-2 text-left text-xs disabled:opacity-50',
                  current?.queryId === run.queryId
                    ? 'bg-white/10 text-white'
                    : 'text-slate-400 hover:bg-white/5 hover:text-slate-200',
                )}
              >
                <span className="mr-2 font-mono text-[10px] text-slate-500">{String(index + 1).padStart(2, '0')}</span>
                {run.question}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-auto rounded-xl border border-white/10 bg-white/5 p-3">
          <div className="flex items-center gap-2 text-xs font-medium">
            <Braces className="size-4 text-violet-300" /> Data source
          </div>
          <div className="mt-2 flex items-center gap-2 text-[11px] text-slate-400">
            <span className={cx('size-1.5 rounded-full', health?.status === 'ok' ? 'bg-emerald-400' : 'bg-amber-400')} />
            {health ? `replay · ${health.replayable} recorded questions` : 'connecting…'}
          </div>
          {health?.metricsRun ? (
            <p className="mt-1 font-mono text-[10px] break-all text-slate-500">{health.metricsRun}</p>
          ) : null}
        </div>
      </aside>

      <section className="min-h-screen lg:pl-[252px]">
        <header className="sticky top-0 z-10 flex h-[68px] items-center justify-between border-b border-slate-200/80 bg-white/90 px-5 backdrop-blur md:px-8">
          <div>
            <p className="text-sm font-semibold">{route.label}</p>
            <p className="text-xs text-slate-500">{route.blurb}</p>
          </div>
          <div className="hidden items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium md:flex">
            <FileSearch className="size-4 text-violet-600" />
            MMDocRAG · 2,000 questions · 220 documents
          </div>
        </header>

        {error ? (
          <p role="alert" className="mx-auto mt-4 max-w-[1160px] rounded-lg bg-rose-50 px-4 py-2 text-sm text-rose-700">
            {error}
          </p>
        ) : null}

        {active === 'chat' ? (
          <ChatView turns={turns} current={current} loading={loading} onAsk={ask} />
        ) : active === 'analysis' ? (
          <AnalysisView turn={current} />
        ) : active === 'experiments' ? (
          <ExperimentsView />
        ) : (
          <ProvenanceView />
        )}
      </section>
    </main>
  );
}
