"""RQ3: does evidence granularity buy retrieval quality at equal token cost?

Why the obvious experiment is the wrong one
-------------------------------------------
The tempting design is: build corpora at several chunk sizes, map the official
gold onto each, and compare recall@k. That design is rigged, twice over.

First, the gold definition moves with the granularity. `quote_corpus.map_gold`
assigns each official gold quote to the single chunk covering the most of it,
requiring >= 50% coverage. A 2,400-character chunk swallows a 280-character
quote whole and maps at coverage 1.0; a 100-character chunk can never cover
more than about a third of the same quote, so it is recorded as *unmapped*.
Coarse corpora would win before a single query was run.

Second, recall@k is not a fair axis across granularities. Ten 2,400-character
chunks are 24,000 characters of context; ten 100-character chunks are 1,000.
The coarse arm would be buying its recall with context the fine arm never got
to spend.

What this measures instead
--------------------------
A granularity-independent target and a granularity-independent budget.

    TARGET. For each official gold text quote g and a retrieved chunk set S,
    coverage is the fraction of g's character 8-grams present anywhere in the
    union of S. The gold never changes; only the retriever's ability to
    reassemble it does. Fine chunks may need several slots to cover one quote,
    which is exactly the cost the fine arm should pay. This reuses the same
    shingle matcher Gate 2 validated at 98.63%, so "covered" means here what it
    meant there.

    BUDGET. Chunks are taken in rank order until the next one would exceed a
    fixed token budget. That is the axis a real system controls: the generator
    prompt has a token budget, not a chunk-count budget.

Reporting both a fixed-k and a fixed-budget view is deliberate. If a granularity
wins on k but loses on tokens, it did not win -- it just spent more.

Scope, stated
-------------
Text evidence only. `quote_corpus` rebuilds the text side of the pool; image
quotes stay as the official 6,565 with their VLM descriptions and are identical
across every corpus here, so they cannot separate the arms and are excluded
rather than carried along as a constant. Gold is therefore the official gold
*text* evidence of the evaluation split.

Run:
    python -m retrieval.eval_granularity
    python -m retrieval.eval_granularity --corpora retrieval/quotes.sqlite:300
"""

import argparse
import collections
import os
import sqlite3
import sys

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from canonical.gate2 import normalize as g2_normalize, shingles   # noqa: E402
from retrieval.bm25 import BM25                                   # noqa: E402
from retrieval.corpus import tokenize                             # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO_ROOT, "canonical", "mmdocrag.sqlite")

KS = (1, 3, 5, 10, 20)
BUDGETS = (500, 1000, 2000, 4000, 8000)
TAUS = (0.5, 0.8)
MAX_PREFIX = 500          # hard cap on chunks examined per query
BOOTSTRAP = 2000
SEED = 20260825


def load_gold(db_path):
    """Official gold text evidence for the evaluation split, setting 20."""
    con = sqlite3.connect(db_path)
    rows = con.execute("""
        SELECT q.question_uid, q.doc_name, q.question, e.evidence_id, e.text
        FROM question_gold_evidence g
        JOIN canonical_evidence e ON e.evidence_id = g.evidence_id
        JOIN questions q          ON q.question_uid = g.question_uid
        WHERE q.split = 'evaluation' AND g.setting = '20'
          AND e.type = 'text' AND e.text IS NOT NULL AND e.text <> ''
    """).fetchall()
    con.close()

    by_q = collections.OrderedDict()
    for quid, doc, question, eid, text in rows:
        rec = by_q.setdefault(quid, {"doc": doc, "q": question or "", "gold": {}})
        rec["gold"][eid] = text
    return by_q


def score_corpus(path, by_q, label, pack="prefix"):
    """Per-gold-quote coverage at every checkpoint, for one granularity."""
    con = sqlite3.connect(path)
    chunk_rows = con.execute(
        "SELECT doc_name, chunk_id, text, n_tok FROM chunks "
        "ORDER BY doc_name, page_id, idx").fetchall()
    con.close()

    by_doc = collections.OrderedDict()
    for doc, cid, text, ntok in chunk_rows:
        by_doc.setdefault(doc, []).append((cid, text or "", ntok or 0))
    del chunk_rows

    q_by_doc = collections.defaultdict(list)
    for quid, rec in by_q.items():
        q_by_doc[rec["doc"]].append(quid)

    # cov[checkpoint][gold_key] -> coverage in [0,1]; cost[checkpoint] -> n chunks
    cov = {c: {} for c in list(KS) + list(BUDGETS)}
    used = {c: [] for c in list(KS) + list(BUDGETS)}
    spent = {c: [] for c in list(KS) + list(BUDGETS)}
    n_q = 0
    missing_docs = set()

    for doc, quids in q_by_doc.items():
        if doc not in by_doc:
            missing_docs.add(doc)
            continue
        items = by_doc[doc]
        texts = [t for _, t, _ in items]
        toks = [n for _, _, n in items]
        bm = BM25([tokenize(t.lower()) for t in texts])
        # shingles are computed once per document and dropped with it
        sh = [shingles(g2_normalize(t)) for t in texts]

        for quid in quids:
            rec = by_q[quid]
            gsh = {eid: shingles(g2_normalize(t)) for eid, t in rec["gold"].items()}
            gsh = {k: v for k, v in gsh.items() if v}
            if not gsh:
                continue
            n_q += 1
            order, _ = bm.rank(tokenize(rec["q"].lower()))

            # one walk down the ranking, snapshotting at every checkpoint
            budget_left = {b: b for b in BUDGETS}
            budget_open = {b: True for b in BUDGETS}
            union = set()
            b_union = {b: set() for b in BUDGETS}
            b_n = {b: 0 for b in BUDGETS}
            b_spent = {b: 0 for b in BUDGETS}

            limit = min(len(order), MAX_PREFIX)
            for r in range(limit):
                i = int(order[r])
                union |= sh[i]
                if r + 1 in cov:
                    for eid, g in gsh.items():
                        cov[r + 1][(quid, eid)] = len(g & union) / len(g)
                    used[r + 1].append(r + 1)
                    spent[r + 1].append(sum(toks[int(order[j])] for j in range(r + 1)))
                for b in BUDGETS:
                    if not budget_open[b]:
                        continue
                    if toks[i] <= budget_left[b]:
                        budget_left[b] -= toks[i]
                        b_union[b] |= sh[i]
                        b_n[b] += 1
                        b_spent[b] += toks[i]
                    elif pack == "prefix":
                        # Stop at the first chunk that overflows, so the arms are
                        # compared on prefix quality rather than on cherry-picking
                        # small chunks from deep in the ranking. This charges the
                        # coarse arms a quantisation loss: a 400-token chunk
                        # cannot enter a budget with 300 tokens left, and the
                        # remainder is forfeited.
                        budget_open[b] = False
                    # "greedy": skip the overflowing chunk and keep packing. This
                    # removes the quantisation loss, so comparing the two modes
                    # separates a granularity's ranking quality from how tightly
                    # its units happen to tile the budget.
                if not any(budget_open.values()) and r + 1 >= max(KS):
                    break

            # A short document can hold fewer chunks than the largest k. Leaving
            # those checkpoints unrecorded would silently drop the question from
            # the scored set; top-20 over a 12-chunk document simply *is* all 12.
            for k in KS:
                if (quid, next(iter(gsh))) in cov[k]:
                    continue
                for eid, g in gsh.items():
                    cov[k][(quid, eid)] = len(g & union) / len(g)
                used[k].append(limit)
                spent[k].append(sum(toks[int(order[j])] for j in range(limit)))

            for b in BUDGETS:
                for eid, g in gsh.items():
                    cov[b][(quid, eid)] = len(g & b_union[b]) / len(g)
                used[b].append(b_n[b])
                spent[b].append(b_spent[b])

    if missing_docs:
        print(f"  [{label}] documents absent from corpus: {len(missing_docs)}")
    return cov, used, spent, n_q


def summarise(label, cov, used, spent, keys):
    print()
    print(f"corpus {label}")
    header = f"{'checkpoint':<14}{'n chunks':>10}{'tokens':>9}"
    for t in TAUS:
        header += f"{'cov>=' + str(t):>10}"
    header += f"{'mean cov':>10}"
    print(header)
    print("-" * len(header))
    for c in list(KS) + list(BUDGETS):
        v = np.array([cov[c][k] for k in keys])
        name = f"top-{c}" if c in KS else f"{c} tok"
        line = (f"{name:<14}{np.mean(used[c]):>10.1f}"
                f"{np.mean(spent[c]):>9.0f}")
        for t in TAUS:
            line += f"{np.mean(v >= t):>10.3f}"
        line += f"{v.mean():>10.3f}"
        print(line)


def paired(base, other, keys, quids, tau, rng):
    """Question-clustered paired bootstrap on the coverage>=tau indicator."""
    a = np.array([other[k] >= tau for k in keys], dtype=float)
    b = np.array([base[k] >= tau for k in keys], dtype=float)
    d = a - b
    obs = d.mean()

    # Resampling questions, not quotes: several gold quotes share a question and
    # their outcomes are correlated, so quote-level resampling would understate
    # the interval. Summing d per question first turns the whole bootstrap into
    # two gathers, which matters -- this is called 80 times.
    pos = {q: i for i, q in enumerate(quids)}
    sd = np.zeros(len(quids))
    sn = np.zeros(len(quids))
    for i, (quid, _) in enumerate(keys):
        sd[pos[quid]] += d[i]
        sn[pos[quid]] += 1.0

    pick = rng.integers(0, len(quids), size=(BOOTSTRAP, len(quids)))
    means = sd[pick].sum(axis=1) / sn[pick].sum(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return obs, lo, hi


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--corpora", nargs="*", default=None,
                    help="path:label pairs; default is the built sweep")
    ap.add_argument("--pack", default="prefix", choices=("prefix", "greedy"),
                    help="prefix: stop at the first chunk that overflows the "
                         "budget. greedy: skip it and keep packing")
    ap.add_argument("--baseline", default="300",
                    help="label to test the others against")
    args = ap.parse_args()

    if args.corpora:
        specs = [(s.rsplit(":", 1)[0], s.rsplit(":", 1)[1]) for s in args.corpora]
    else:
        specs = [(os.path.join(REPO_ROOT, "retrieval", "quotes_t100.sqlite"), "100"),
                 (os.path.join(REPO_ROOT, "retrieval", "quotes.sqlite"), "300"),
                 (os.path.join(REPO_ROOT, "retrieval", "quotes_t600.sqlite"), "600"),
                 (os.path.join(REPO_ROOT, "retrieval", "quotes_t1200.sqlite"), "1200"),
                 (os.path.join(REPO_ROOT, "retrieval", "quotes_t2400.sqlite"), "2400")]
    specs = [(p, l) for p, l in specs if os.path.exists(p)]
    print(f"packing rule: {args.pack}")
    print("corpora: " + ", ".join(f"{l} ({os.path.basename(p)})" for p, l in specs))

    by_q = load_gold(args.db)
    print(f"evaluation questions with text gold: {len(by_q)}, "
          f"gold text quotes: {sum(len(r['gold']) for r in by_q.values())}")

    results = {}
    for path, label in specs:
        print(f"scoring {label} ...", flush=True)
        results[label] = score_corpus(path, by_q, label, args.pack)

    # score only gold quotes every arm produced a number for
    common = None
    for label, (cov, _, _, _) in results.items():
        for c in list(KS) + list(BUDGETS):
            s = set(cov[c].keys())
            common = s if common is None else (common & s)
    keys = sorted(common)
    quids = sorted({q for q, _ in keys})
    print()
    print(f"scored on {len(keys)} gold text quotes over {len(quids)} questions "
          f"(intersection of all arms)")

    for path, label in specs:
        cov, used, spent, _ = results[label]
        summarise(label, cov, used, spent, keys)

    if args.baseline not in results:
        return
    base_cov = results[args.baseline][0]
    rng = np.random.default_rng(SEED)
    for tau in TAUS:
        print()
        print("=" * 78)
        print(f"PAIRED BOOTSTRAP vs granularity {args.baseline}   "
              f"(coverage >= {tau}, B={BOOTSTRAP}, clustered by question)")
        print("=" * 78)
        print(f"{'checkpoint':<14}" + "".join(
            f"{l:>24}" for _, l in specs if l != args.baseline))
        for c in list(KS) + list(BUDGETS):
            name = f"top-{c}" if c in KS else f"{c} tok"
            line = f"{name:<14}"
            for _, label in specs:
                if label == args.baseline:
                    continue
                obs, lo, hi = paired(base_cov[c], results[label][0][c],
                                     keys, quids, tau, rng)
                star = "*" if (lo > 0 or hi < 0) else " "
                line += f"  {obs:>+.3f} [{lo:>+.3f},{hi:>+.3f}]{star}"
            print(line)
        print("* = 95% CI excludes zero")


if __name__ == "__main__":
    main()
