import type { ReactNode } from 'react';
import type { Citation } from '../types';
import { Badge } from './ui';

/**
 * Renders one recorded answer the way the benchmark defines an answer: text
 * interleaved with images, citing quotes by their local id.
 *
 * `![alt](image3)` and `[6]` are resolved against the candidate block that was
 * actually shown to the generator. A citation that resolves to nothing is not
 * hidden -- it is labelled, because "the model cited a quote it was never given"
 * is a finding, not a rendering bug.
 */

const IMAGE = /!\[([^\]]*)\]\((image\d+)\)/g;
const INLINE = /(\[\d+\]|\*\*[^*]+\*\*)/g;

function inline(text: string, byLocalId: Map<string, Citation>, key: string): ReactNode[] {
  return text.split(INLINE).map((part, i) => {
    const id = `${key}-${i}`;
    if (/^\[\d+\]$/.test(part)) {
      const local = `text${part.slice(1, -1)}`;
      const citation = byLocalId.get(local);
      return (
        <sup
          key={id}
          title={
            citation
              ? `${local} · ${citation.documentName} p.${citation.page}${citation.isGold ? ' · gold' : ''}`
              : `${local} was not in the candidate block shown to the model`
          }
          className={
            citation
              ? citation.isGold
                ? 'mx-0.5 rounded bg-emerald-100 px-1 py-0.5 font-mono text-[10px] text-emerald-800'
                : 'mx-0.5 rounded bg-violet-100 px-1 py-0.5 font-mono text-[10px] text-violet-700'
              : 'mx-0.5 rounded bg-rose-100 px-1 py-0.5 font-mono text-[10px] text-rose-700'
          }
        >
          {part}
        </sup>
      );
    }
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={id}>{part.slice(2, -2)}</strong>;
    }
    return <span key={id}>{part}</span>;
  });
}

export function AnswerBody({ text, citations }: { text: string | null; citations: Citation[] }) {
  if (!text) {
    return (
      <p className="text-sm text-slate-500">
        The recorded end-to-end run did not cover this question, so there is no answer to replay. The retrieval and
        routing panels below are still real.
      </p>
    );
  }
  const byLocalId = new Map(citations.map((c) => [c.localId, c]));
  const nodes: ReactNode[] = [];
  let cursor = 0;
  let match: RegExpExecArray | null;
  IMAGE.lastIndex = 0;
  while ((match = IMAGE.exec(text)) !== null) {
    if (match.index > cursor) {
      nodes.push(
        <p key={`t-${cursor}`} className="whitespace-pre-wrap">
          {inline(text.slice(cursor, match.index), byLocalId, `t-${cursor}`)}
        </p>,
      );
    }
    const [, alt, local] = match;
    const citation = byLocalId.get(local);
    nodes.push(
      <figure key={`i-${match.index}`} className="my-4 overflow-hidden rounded-xl border border-slate-200 bg-slate-50">
        {citation?.imageUrl ? (
          <img src={citation.imageUrl} alt={alt} className="max-h-[340px] w-full bg-white object-contain" loading="lazy" />
        ) : (
          <div className="p-4 text-xs text-rose-700">
            The answer cited <code className="font-mono">{local}</code>, which was not in the candidate block it was
            given.
          </div>
        )}
        <figcaption className="flex flex-wrap items-center gap-2 border-t border-slate-200 bg-white px-3 py-2 text-[11px] text-slate-500">
          <Badge tone="accent">{local}</Badge>
          {citation ? (
            <>
              <span>
                {citation.documentName} · page {citation.page}
              </span>
              {citation.isGold ? <Badge tone="good">gold evidence</Badge> : <Badge tone="neutral">not gold</Badge>}
            </>
          ) : (
            <Badge tone="bad">unresolved citation</Badge>
          )}
          <span className="truncate">{alt}</span>
        </figcaption>
      </figure>,
    );
    cursor = match.index + match[0].length;
  }
  if (cursor < text.length) {
    nodes.push(
      <p key={`t-${cursor}`} className="whitespace-pre-wrap">
        {inline(text.slice(cursor), byLocalId, `t-${cursor}`)}
      </p>,
    );
  }
  return <div className="answer-body text-[15px] leading-7 text-slate-700">{nodes}</div>;
}
