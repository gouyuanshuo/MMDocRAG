/**
 * Render the console's components against the live API and check what came out.
 *
 * There is no browser available in this environment, so "it looks right" cannot
 * be claimed. What can be checked is stronger than nothing and weaker than a
 * visual pass: every component is rendered to HTML with the *real* payloads the
 * Python server sends, and the output is asserted to contain the values the
 * artifacts hold. That catches a renamed field, a crash on a null interval, or a
 * table that silently drops its rows -- the failures that would otherwise be
 * discovered in front of an audience.
 *
 *     python -m demo.server --port 8000     # in one terminal
 *     npm run check:render                  # in another
 */

import { renderToStaticMarkup } from 'react-dom/server';
import { DataTable } from '../src/components/DataTable';
import { AnswerBody } from '../src/components/Answer';
import { EvidenceList } from '../src/components/EvidenceList';
import { LiveTurn } from '../src/components/LiveTurn';
import type { Group, LiveAnswer, Turn } from '../src/types';

const BASE = process.env.MMDOCRAG_API ?? 'http://127.0.0.1:8000';
const failures: string[] = [];
let checks = 0;

function check(label: string, condition: boolean, detail = '') {
  checks += 1;
  if (!condition) failures.push(`${label}${detail ? ` — ${detail}` : ''}`);
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`);
  if (!response.ok) throw new Error(`${path} -> ${response.status}`);
  return (await response.json()) as T;
}

async function main() {
  const groups = ['end-to-end', 'retrieval', 'visual', 'slices', 'routing'];
  for (const id of groups) {
    const group = await get<Group>(`/api/experiments/phase3/results?group=${id}`);
    check(`${id}: has tables`, group.tables.length > 0);
    for (const table of group.tables) {
      const html = renderToStaticMarkup(<DataTable table={table} />);
      check(`${id}/${table.id}: renders rows`, table.rows.length === 0 || html.includes('<tr'), `${html.length} chars`);
      check(`${id}/${table.id}: no literal undefined`, !html.includes('>undefined<'));
      check(`${id}/${table.id}: no NaN`, !html.includes('NaN'));
      const rowCount = (html.match(/<tr/g) ?? []).length - 1; // minus the header row
      check(
        `${id}/${table.id}: every row rendered`,
        rowCount === table.rows.length,
        `${rowCount} rendered vs ${table.rows.length} sent`,
      );
    }
  }

  // A cell that carries an interval must print it; the end-to-end delta is the
  // one the project reports, so it is checked by value rather than by shape.
  const endToEnd = await get<Group>('/api/experiments/phase3/results?group=end-to-end');
  const armsHtml = renderToStaticMarkup(<DataTable table={endToEnd.tables[0]} />);
  check('end-to-end: prints the paired delta', armsHtml.includes('+2.90'), armsHtml.slice(0, 200));
  check('end-to-end: prints its interval', armsHtml.includes('[+1.01, +4.77]'));

  const turn = await (
    await fetch(`${BASE}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: 'How many goblets appear in the figure showing Skyskraoeren?' }),
    })
  ).json() as Turn;

  check('chat: matched a question', Boolean(turn.match.questionUid));
  check('chat: has a recorded answer', Boolean(turn.answer));
  check('chat: has a candidate block', turn.citations.length > 0);

  const answerHtml = renderToStaticMarkup(<AnswerBody text={turn.answer} citations={turn.citations} />);
  check('answer: renders text', answerHtml.length > 200);
  const images = (answerHtml.match(/<img/g) ?? []).length;
  const imageMarkup = (turn.answer?.match(/!\[[^\]]*\]\(image\d+\)/g) ?? []).length;
  const unresolved = (answerHtml.match(/unresolved citation/g) ?? []).length;
  check(
    'answer: every image markup became an image or a labelled miss',
    images + unresolved === imageMarkup,
    `${images} images + ${unresolved} unresolved vs ${imageMarkup} markups`,
  );

  const evidenceHtml = renderToStaticMarkup(<EvidenceList citations={turn.citations} />);
  check('evidence: one entry per quote', (evidenceHtml.match(/<li/g) ?? []).length === turn.citations.length);
  check(
    'evidence: gold flags survive',
    turn.citations.every((c) => !c.isGold) || evidenceHtml.includes('>gold<'),
  );

  // Live mode is opt-in because rendering its component means making a paid API
  // call. MMDOCRAG_RENDER_CHECK_LIVE=1 turns it on; the server must have been
  // started with --live.
  if (process.env.MMDOCRAG_RENDER_CHECK_LIVE === '1') {
    const live = (await (
      await fetch(`${BASE}/api/live`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: 'What does the report say about venture capital deal sizes in Europe?' }),
      })
    ).json()) as LiveAnswer;
    check('live: answered', Boolean(live.answer), JSON.stringify(live).slice(0, 160));
    check('live: retrieved a full candidate block', live.quotes.length === live.config.quotaText + live.config.quotaVisual);
    check('live: reports measured tokens', (live.usage?.total_tokens ?? 0) > 0);
    const liveHtml = renderToStaticMarkup(<LiveTurn live={live} />);
    check('live: renders', liveHtml.includes('Live answer'), `${liveHtml.length} chars`);
    check('live: says it is not recorded', liveHtml.includes('not part of any recorded run'));
    check('live: shows the document it chose', liveHtml.includes(live.document.name));
    check('live: no literal undefined', !liveHtml.includes('>undefined<'));
  } else {
    console.log('render-check: live section skipped (MMDOCRAG_RENDER_CHECK_LIVE=1 to include; it spends)');
  }

  console.log(`render-check: ${checks - failures.length}/${checks} passed`);
  for (const failure of failures) console.error(`  FAIL ${failure}`);
  if (failures.length) process.exit(1);
}

main().catch((error) => {
  console.error('render-check could not run:', error.message);
  console.error('Is demo/server.py running on', BASE, '?');
  process.exit(2);
});
