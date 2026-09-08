import type {
  Conversation,
  LiveAnswer,
  Group,
  Health,
  Provenance,
  Question,
  RecentRun,
  RegistryEntry,
  Replay,
  RetrieverComparison,
  Turn,
} from './types';

// Same-origin by default: in dev Vite proxies /api to the Python server, and in
// a build demo/server.py serves both. VITE_API_BASE_URL only matters when the
// two are deliberately split across hosts.
const base = import.meta.env.VITE_API_BASE_URL ?? '';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    signal: AbortSignal.timeout(30000),
    ...init,
  });
  if (!response.ok) {
    const data = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(data.detail ?? `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<Health>('/api/health'),
  provenance: () => request<Provenance>('/api/provenance'),
  questions: (search: string, limit = 25) =>
    request<{ items: Question[]; total: number; replayableOnly: boolean }>(
      `/api/questions?search=${encodeURIComponent(search)}&limit=${limit}`,
    ),
  ask: (question: string, queryId?: string, questionUid?: string) =>
    request<Turn>('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ question, queryId, questionUid }),
    }),
  recentRuns: () => request<{ runs: RecentRun[] }>('/api/queries'),
  conversation: (queryId: string) =>
    request<Conversation>(`/api/queries/${encodeURIComponent(queryId)}`),
  analysis: (queryId: string) =>
    request<Turn>(`/api/queries/${encodeURIComponent(queryId)}/analysis`),
  replay: (uid: string) => request<Replay>(`/api/replay/${encodeURIComponent(uid)}`),
  documents: (search: string, limit = 30) =>
    request<{ items: { docName: string; questions: number }[]; total: number }>(
      `/api/documents?search=${encodeURIComponent(search)}&limit=${limit}`,
    ),
  // A live answer runs retrieval and calls the API, so it is slower than every
  // other route here and gets its own timeout.
  live: (question: string, docName?: string) =>
    request<LiveAnswer>('/api/live', {
      method: 'POST',
      body: JSON.stringify({ question, docName }),
      signal: AbortSignal.timeout(180000),
    }),
  retrievers: (uid: string, k = 10) =>
    request<RetrieverComparison>(`/api/retrievers/${encodeURIComponent(uid)}?k=${k}`),
  experiments: () =>
    request<{ groups: { id: string; title: string }[]; registry: RegistryEntry[]; run: Record<string, unknown> }>(
      '/api/experiments',
    ),
  results: (group: string) =>
    request<Group>(`/api/experiments/phase3/results?group=${encodeURIComponent(group)}`),
};
