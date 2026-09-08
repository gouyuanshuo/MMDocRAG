/**
 * The shapes demo/server.py sends.
 *
 * Two of these deserve a note, because the names in the original UI implied
 * something this project did not measure.
 *
 * `Routing.static` is one configuration for every question -- nested CV chose
 * it once, not per query. The per-question decision this project has is
 * `Routing.perQuestion`, and it is a *cost* decision: whether a question is
 * worth escalating to the GPU visual retriever.
 *
 * `citationF1` is quote-selection F1 -- which evidence the answer cited. It is
 * not answer correctness and not faithfulness; neither was measured.
 */

export type Cell = {
  value: number | null;
  ciLow: number | null;
  ciHigh: number | null;
  pRaw: number | null;
  pHolm: number | null;
  significant: boolean | null;
  missing: boolean;
};

export type Counts = {
  questions?: number | null;
  documents?: number | null;
  sampleUnit?: string | null;
  bootstrap?: number | null;
};

export type Question = {
  questionUid: string;
  qId: number;
  docName: string;
  domain: string | null;
  question: string;
  questionType: string | null;
  evidenceModality: string[];
  answerShort: string | null;
  goldCount: number;
  matchScore?: number | null;
};

export type Quote = {
  localId: string;
  rank: number;
  branch: 'text' | 'visual';
  retriever: string;
  evidenceId: string;
  docName: string | null;
  page: number | null;
  layoutId: number | null;
  type: string | null;
  isGold: boolean;
  cited: boolean | null;
  text: string | null;
  imgDescription: string | null;
  imgPath: string | null;
  imageUrl: string | null;
};

export type Citation = {
  id: string;
  localId: string;
  evidenceId: string;
  documentName: string | null;
  page: number | null;
  type: 'text' | 'visual';
  branch: 'text' | 'visual';
  retriever: string;
  rank: number;
  isGold: boolean;
  cited: boolean | null;
  snippet: string;
  imageUrl: string | null;
};

export type ArmCounts = {
  goldTotal: number;
  goldMapped: number;
  goldUnmapped: number;
  goldRetrieved: number;
  quotesShown: number;
  quotaText: number;
  quotaVisual: number;
};

export type Arm = {
  label: string;
  description: string;
  config: {
    textRetriever: string;
    visualRetriever: string;
    quotaText: number;
    quotaVisual: number;
    k: number;
    pool: string;
    denseModel: string;
  };
  answer: string | null;
  answerAvailable: boolean;
  tokens: { inTok: number; outTok: number; totalTok: number; model: string } | null;
  citedLocalIds: string[] | null;
  quotes: Quote[];
  counts: ArmCounts;
  citationF1: number | null;
};

export type PerQuestionRouting = {
  recallCheap: number | null;
  recallExpensive: number | null;
  trueGain: number | null;
  predictedGain: number | null;
  escalate: Record<string, boolean>;
  config: Record<string, string | number | null>;
  rates: Record<string, number>;
};

export type Routing = {
  static: {
    textRetriever: string;
    visualRetriever: string;
    quotaText: number;
    quotaVisual: number;
    topK: number;
    pool: string;
    denseModel: string;
    selectedBy: string;
    perQuestion: false;
  };
  perQuestion: PerQuestionRouting | null;
  note: string;
};

export type Replay = Question & {
  replayable: boolean;
  arms: Record<string, Arm>;
  routing: PerQuestionRouting | null;
  retrieval?: {
    poolText: number;
    poolVisual: number;
    goldTotal: number;
    goldUnmapped: number;
    goldText: number;
    goldVisual: number;
    hasColqwen: boolean;
  };
  paired?: { deltaF1: number | null; metric: string; notAnswerCorrectness: boolean };
  provenance: Record<string, unknown>;
};

export type Turn = {
  queryId: string;
  turnId: string;
  status: string;
  question: string;
  match: { questionUid: string; method: string; score: number | null; exact: boolean; question: string; docName: string };
  answer: string | null;
  answerAvailable: boolean;
  citations: Citation[];
  routing: Routing;
  replay: Replay;
  baseline: {
    label: string;
    answer: string | null;
    citations: Citation[];
    citationF1: number | null;
    config: Arm['config'];
  };
  metrics: {
    citationF1: number | null;
    baselineCitationF1: number | null;
    deltaF1: number | null;
    counts: ArmCounts;
    tokens: Arm['tokens'];
    metric: string;
  };
};

export type Conversation = { queryId: string; title: string; created: number; turns: Turn[] };
export type RecentRun = { queryId: string; question: string; turns: number };

export type Column = {
  key: string;
  label: string;
  format: 'text' | 'recall' | 'f1' | 'delta' | 'deltaF1' | 'pct' | 'int' | 'p';
  variant?: string;
};

export type Table = {
  id: string;
  title: string;
  subtitle?: string;
  columns: Column[];
  rows: Record<string, unknown>[];
  chart:
    | null
    | {
        kind: 'bar' | 'line';
        valueKey?: string;
        labelKey?: string;
        unit?: string;
        groupKey?: string;
        filterKey?: string;
        filterValue?: string;
        xKey?: string;
        seriesKeys?: string[];
      };
};

export type Group = {
  id: string;
  title: string;
  subtitle: string;
  source: { experiments: string[]; run: string; model?: string };
  notes: string[];
  tables: Table[];
  caveats: string[];
};

export type RegistryEntry = {
  id: string;
  phase: string;
  status: string;
  statusLabel: string;
  lifecycle: string;
  title: string;
  asks: string | null;
  suites: string[];
  hasCorrections: boolean;
  result: string | null;
  limits: string | null;
};

export type Provenance = {
  mode: string;
  claim: string;
  generation: Record<string, unknown> & { model: string; k: number; pool: string; dense_model: string; n_questions: number; n_documents: number; note: string };
  retrieval: { actionTable: Record<string, unknown>; note: string };
  router: Record<string, unknown>;
  metricsRun: Record<string, unknown>;
  counts: { questions: number; documents: number; replayable: number; metrics: number };
  imageRoot: { path: string; available: boolean; note: string | null };
  caveats: string[];
  errors: string[];
};

export type Health = {
  status: string;
  mode: string;
  questions: number;
  replayable: number;
  metricsRun: string;
  errors: string[];
};

export type RetrieverBranch = {
  pool: number;
  goldTotal: number;
  retrievers: {
    retriever: string;
    readsPixels: boolean;
    representation: string;
    goldInTopK: number;
    topK: { evidenceId: string; isGold: boolean }[];
  }[];
};

export type RetrieverComparison = {
  questionUid: string;
  k: number;
  branches: Record<string, RetrieverBranch>;
  source: Record<string, unknown>;
};
