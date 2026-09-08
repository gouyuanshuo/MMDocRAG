import { useState } from 'react';
import { FileText, Image as ImageIcon } from 'lucide-react';
import type { Citation } from '../types';
import { Badge } from './ui';
import { short } from '../format';

/**
 * The candidate block, in the order the retriever ranked it.
 *
 * Two flags carry the research content: `gold` marks a quote the benchmark
 * counts as correct evidence, and `cited` marks one the model actually used.
 * Together they are the citation F1 the recorded run scored, made visible per
 * quote instead of summarised into one number.
 */

export function EvidenceList({
  citations,
  compact = false,
}: {
  citations: Citation[];
  compact?: boolean;
}) {
  const [open, setOpen] = useState<string | null>(null);
  if (!citations.length) return <p className="text-xs text-slate-500">No candidate block recorded.</p>;
  return (
    <ol className="space-y-2">
      {citations.map((citation) => {
        const isOpen = open === citation.id;
        return (
          <li key={citation.id} className="rounded-xl border border-slate-200 bg-white">
            <button
              type="button"
              onClick={() => setOpen(isOpen ? null : citation.id)}
              className="flex w-full items-start gap-3 p-3 text-left"
            >
              <span className="mt-0.5 font-mono text-[10px] text-slate-400">{String(citation.rank).padStart(2, '0')}</span>
              <span
                className={`grid size-8 shrink-0 place-items-center rounded-lg ${
                  citation.branch === 'visual' ? 'bg-violet-50 text-violet-600' : 'bg-slate-100 text-slate-500'
                }`}
              >
                {citation.branch === 'visual' ? <ImageIcon className="size-4" /> : <FileText className="size-4" />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-1.5">
                  <Badge tone="outline">{citation.localId}</Badge>
                  {citation.isGold ? <Badge tone="good">gold</Badge> : null}
                  {citation.cited ? <Badge tone="accent">cited by the model</Badge> : null}
                  <span className="font-mono text-[10px] text-slate-400">{citation.retriever}</span>
                  <span className="text-[11px] font-medium text-slate-700">
                    {citation.documentName} · page {citation.page}
                  </span>
                </span>
                <span className="mt-1 block text-[11px] leading-5 text-slate-500">
                  {short(citation.snippet, compact ? 130 : 240)}
                </span>
              </span>
            </button>
            {isOpen ? (
              <div className="border-t border-slate-100 p-3">
                {citation.imageUrl ? (
                  <img
                    src={citation.imageUrl}
                    alt={`Evidence ${citation.localId}`}
                    className="mb-3 max-h-[320px] w-full rounded-lg border border-slate-200 bg-white object-contain"
                    loading="lazy"
                  />
                ) : null}
                <p className="text-[11px] leading-5 whitespace-pre-wrap text-slate-600">{citation.snippet}</p>
                <p className="mt-2 font-mono text-[10px] text-slate-400">
                  evidence_id {citation.evidenceId} · branch {citation.branch} · retriever {citation.retriever}
                </p>
              </div>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
