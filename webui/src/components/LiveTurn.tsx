import { AlertTriangle, FileStack, Timer, Zap } from 'lucide-react';
import type { Citation, LiveAnswer } from '../types';
import { AnswerBody } from './Answer';
import { EvidenceList } from './EvidenceList';
import { Badge, Card, CardContent, CardHeader, CardTitle, Field, Stat } from './ui';

/**
 * One live answer: retrieval that just ran, and an API call that just happened.
 *
 * Everything on this card is new work, which is exactly why it is styled apart
 * from the replayed turns. A viewer who cannot tell a live answer from a
 * recorded one will quote the live one as a result, and no experiment scored it.
 */

function asCitations(live: LiveAnswer): Citation[] {
  return live.quotes.map((quote) => ({
    id: quote.localId,
    localId: quote.localId,
    evidenceId: quote.evidenceId,
    documentName: quote.docName,
    page: quote.page,
    type: quote.branch === 'visual' ? 'visual' : 'text',
    branch: quote.branch,
    retriever: quote.retriever,
    rank: quote.rank,
    isGold: quote.isGold,
    cited: quote.cited,
    snippet: (quote.text ?? quote.imgDescription ?? '').slice(0, 600),
    imageUrl: quote.imageUrl,
  }));
}

export function LiveTurn({ live, onRetryWithDocument }: { live: LiveAnswer; onRetryWithDocument?: (doc: string) => void }) {
  const citations = asCitations(live);
  const alternatives = live.document.candidates.filter((c) => c.docName !== live.document.name).slice(0, 3);

  return (
    <article className="space-y-4">
      <div className="ml-auto max-w-[76%] rounded-2xl rounded-tr-md bg-[#eff1f7] px-4 py-3 text-sm leading-6 whitespace-pre-wrap">
        {live.question}
      </div>

      <div className="rounded-xl border border-amber-300 bg-amber-50/70 px-4 py-3">
        <p className="flex items-center gap-2 text-xs font-semibold text-amber-900">
          <Zap className="size-4" /> Live answer — retrieval ran just now and this was a paid API call
        </p>
        <p className="mt-1 text-[11px] leading-5 text-amber-900/85">{live.provenance.warning}</p>
      </div>

      <Card>
        <CardHeader className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2">
            <FileStack className="size-4 text-violet-600" /> Document retrieved first
          </CardTitle>
          <Badge tone="outline">{live.document.method}</Badge>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm font-medium text-slate-800">{live.document.name}</p>
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Field label="Text units" value={live.document.poolText} />
            <Field label="Image units" value={live.document.poolVisual} />
            <Field label="Quota" value={`${live.config.quotaText} text / ${live.config.quotaVisual} image`} />
            <Field label="Encoder" value={live.config.denseModel.split('/').pop() ?? ''} />
          </dl>
          {alternatives.length && onRetryWithDocument ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[11px] text-slate-500">Wrong document? Ask again against:</span>
              {alternatives.map((alt) => (
                <button
                  key={alt.docName}
                  onClick={() => onRetryWithDocument(alt.docName)}
                  className="rounded-lg border border-slate-200 px-2 py-1 text-[11px] text-slate-600 hover:border-violet-300 hover:text-violet-700"
                >
                  {alt.docName}
                </button>
              ))}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <div className="min-w-0">
        <p className="mb-2 text-sm font-semibold">
          {live.config.model}
          <span className="ml-2 text-[11px] font-normal text-slate-400">
            generated now · {live.config.mode} · {live.config.promptTemplate}
          </span>
          {live.config.sendsImages ? (
            <Badge tone="accent" className="ml-2">
              the images themselves were sent
            </Badge>
          ) : (
            <Badge tone="neutral" className="ml-2">
              image descriptions were sent
            </Badge>
          )}
        </p>
        <AnswerBody text={live.answer} citations={citations} />
      </div>

      <div className="grid gap-3 sm:grid-cols-4">
        <Stat label="Input tokens" value={live.usage.input_tokens?.toLocaleString() ?? '—'} hint="measured" />
        <Stat label="Output tokens" value={live.usage.output_tokens?.toLocaleString() ?? '—'} hint="measured" />
        <Stat label="Retrieval" value={`${live.timings.retrievalSec}s`} hint="document + branches" />
        <Stat label="Generation" value={`${live.timings.generationSec}s`} hint={`${live.budget.callsLeft} calls left`} />
      </div>

      {live.scoring.scored ? (
        <Card className="ring-emerald-200">
          <CardHeader>
            <CardTitle className="text-emerald-800">
              This question is in the benchmark, so it can be scored — as a diagnostic
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat label="Citation F1" value={live.scoring.f1.toFixed(2)} tone="good" />
              <Stat label="Precision" value={live.scoring.precision.toFixed(2)} />
              <Stat label="Recall" value={live.scoring.recall.toFixed(2)} />
              <Stat
                label="Gold retrieved"
                value={`${live.scoring.goldRetrieved}/${live.scoring.goldTotal}`}
              />
            </div>
            <p className="flex gap-2 text-[11px] leading-5 text-amber-900">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
              {live.scoring.warning}
            </p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="flex gap-2 py-4 text-xs leading-5 text-slate-600">
            <Timer className="mt-0.5 size-4 shrink-0 text-slate-400" />
            {live.scoring.reason}
          </CardContent>
        </Card>
      )}

      <details className="rounded-xl border border-slate-200 bg-slate-50/60 p-4">
        <summary className="cursor-pointer text-xs font-medium text-slate-700">
          Candidate block this answer was given ({citations.length} quotes
          {live.benchmarkMatch ? `, ${citations.filter((c) => c.isGold).length} gold` : ''})
        </summary>
        <div className="mt-3">
          <EvidenceList citations={citations} compact />
        </div>
      </details>

      <p className="text-[10px] leading-4 text-slate-400">
        {live.provenance.retrieval} {live.provenance.generation} Logged to {live.provenance.logged}.{' '}
        {live.provenance.tokens}
      </p>
    </article>
  );
}
