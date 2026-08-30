"""ColQwen absolute image recall over the FULL document pool.

Why this is separate from eval_colqwen
--------------------------------------
`eval_colqwen.py` compares ColQwen against BM25 and BGE running over VLM
descriptions. That comparison requires one pool: those two retrievers have no
representation at all for an image the official candidate list never contained,
and 63.9% of the images in these documents are in exactly that position. So that
script is pinned to the candidate pool and refuses a full-disk index.

This script answers the other question, and only that one: **does this project's
ColQwen implementation land in the same place as the paper's?** That comparison
needs the paper's pool, not a fair one -- 63.6 images per document here against
the paper's 63, where the candidate pool holds 29.8.

The prediction is falsifiable and worth stating before running. On the candidate
pool this project measured Recall@10 = 0.820 where the paper reports 0.708.
Halving the pool is the obvious explanation, so restoring the pool should pull
the number DOWN toward the paper's. If it stays at 0.82, the gap was never about
the pool and something in this implementation differs from theirs. If it drops
far below 0.708, the full pool has distractors the paper's did not.

What cannot be compared
-----------------------
Table 6 gives each retriever BOTH a text and an image recall, including the
visual ones. The paper never explains how a visual retriever ranks text quotes,
and its quota sentence ("top 10: 3 images and 7 texts from visual and text
retriever respectively") is stated for HYBRID retrieval only. So:

  * ColQwen's IMAGE recall is reproducible -- rank the document's images, take
    the top k, count gold image quotes. That is what this script computes.
  * ColQwen's TEXT recall (28.5 / 33.7 / 36.0) is NOT reproducible from the
    paper's description, and no number here should be set beside it.

Whether the paper's single-retriever columns use the full k over one modality or
the hybrid quota is also unstated. This uses the full k, which is the reading
the column header supports; the quota reading is reported alongside so a reader
can see both rather than trusting one.

Run:
    python -m retrieval.eval_fullpool --scores retrieval/colqwen_scores_fullpool.sqlite
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

from expkit.results import ExperimentResult, add_output_args     # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO_ROOT, "canonical", "mmdocrag.sqlite")
DEFAULT_SCORES = os.path.join(REPO_ROOT, "retrieval",
                              "colqwen_scores_fullpool.sqlite")
KS = (10, 15, 20)
# Table 6, ColQwen row, image column. Text column deliberately absent: see above.
PAPER_IMG_RECALL = {10: 0.708, 15: 0.792, 20: 0.843}
# Visual slots at each total budget, for the alternative quota reading.
PAPER_QUOTA_IMG = {10: 3, 15: 5, 20: 8}
BOOTSTRAP = 4000
SEED = 20260830


def cluster_ci(per_doc_num, per_doc_den, n_boot=BOOTSTRAP, seed=SEED):
    """Document-cluster bootstrap for a ratio. Questions nest inside documents."""
    rng = np.random.default_rng(seed)
    num = np.asarray(per_doc_num, dtype=float)
    den = np.asarray(per_doc_den, dtype=float)
    idx = rng.integers(0, len(num), size=(n_boot, len(num)))
    boot = num[idx].sum(axis=1) / np.maximum(den[idx].sum(axis=1), 1e-9)
    return tuple(np.percentile(boot, [2.5, 97.5]))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--scores", default=DEFAULT_SCORES)
    add_output_args(ap)
    args = ap.parse_args()

    if not os.path.exists(args.scores):
        raise SystemExit(
            f"no full-pool rankings at {args.scores}. Build them with:\n"
            f"  .venv-colpali/Scripts/python.exe -m retrieval.colqwen_index "
            f"--image-source fulldisk --out {args.scores}")

    con = sqlite3.connect(args.db)
    qs = con.execute(
        "SELECT question_uid, doc_name FROM questions "
        "WHERE split = 'evaluation' ORDER BY question_uid").fetchall()
    gold_rows = con.execute("""
        SELECT g.question_uid, g.evidence_id
        FROM question_gold_evidence g
        JOIN canonical_evidence e ON e.evidence_id = g.evidence_id
        JOIN questions q          ON q.question_uid = g.question_uid
        WHERE q.split = 'evaluation' AND g.setting = '20' AND e.type <> 'text'
    """).fetchall()
    con.close()
    gold = collections.defaultdict(set)
    for quid, eid in gold_rows:
        gold[quid].add(eid)
    doc_of = {str(u): str(d) for u, d in qs}

    cq = sqlite3.connect(args.scores)
    rank_of = collections.defaultdict(dict)
    pool = collections.Counter()
    n_unpooled = 0
    for quid, eid, rank in cq.execute(
            "SELECT question_uid, evidence_id, rank FROM ranking"):
        rank_of[quid][eid] = rank
        pool[quid] += 1
        if eid.startswith("unpooled:"):
            n_unpooled += 1
    cq.close()

    if not n_unpooled:
        raise SystemExit(
            f"{args.scores} contains no images outside the candidate pool, so "
            f"it is a candidate-pool index, not a full-disk one. Comparing it "
            f"to the paper's Table 6 would compare different pools. Use "
            f"eval_colqwen.py for a candidate-pool index.")

    # Indexing runs document by document and can be stopped, so the index may
    # cover a subset. That subset -- not the whole corpus -- is the population
    # this script can speak about. Counting an unindexed document's gold as a
    # miss would not be conservative, it would be wrong: nothing ranked it, so
    # the number would measure how far the indexer got, not how well it ranks.
    # With --doc-order random the covered set is a simple random sample of
    # documents, which is what makes a partial index reportable at all.
    indexed_docs = {doc_of[q] for q in rank_of if q in doc_of}
    all_gold_q = [q for q in (str(u) for u, _d in qs) if gold.get(q)]
    scored = [q for q in all_gold_q if doc_of[q] in indexed_docs]
    ranked = [q for q in scored if q in rank_of]
    n_no_gold = len(qs) - len(all_gold_q)
    all_docs = {d for _u, d in ((str(u), d) for u, d in qs)}
    partial = len(indexed_docs) < len(all_docs)

    print("=" * 84)
    print("FULL-POOL ColQwen: absolute image recall, comparable to Table 6")
    print("=" * 84)
    pool_by_doc = {}
    for q in ranked:
        pool_by_doc.setdefault(doc_of[q], pool[q])
    pv = sorted(pool_by_doc.values())
    print(f"  evaluation questions          {len(qs)}")
    print(f"  documents indexed             {len(indexed_docs)} / {len(all_docs)}"
          + ("   PARTIAL -- random document sample" if partial else "   complete"))
    print(f"  with visual gold, in sample   {len(scored)}   "
          f"({n_no_gold} questions have no visual gold and are outside this "
          f"population)")
    print(f"  ranked by this index          {len(ranked)}")
    if partial:
        print(f"  NOTE: recall below is estimated on {len(indexed_docs)} "
              f"documents drawn at random (seeded shuffle), not all "
              f"{len(all_docs)}. The interval reflects that sample size. "
              f"Documents outside the sample are NOT counted as misses -- "
              f"nothing ranked them.")
    print(f"  pool per document             median {int(np.median(pv))}, "
          f"mean {np.mean(pv):.1f}   (paper: 63)")
    print(f"  images outside candidate pool {n_unpooled} ranked entries")
    print()

    # ---- recall, both readings of the paper's column ---------------------
    docs = sorted({doc_of[q] for q in scored})
    di = {d: i for i, d in enumerate(docs)}
    rows = []
    print(f"{'k':>4}  {'recall@k (full k)':>20}  {'95% CI':>18}  "
          f"{'quota reading':>14}  {'paper':>7}")
    print("-" * 84)
    metrics = {}
    for k in KS:
        num = np.zeros(len(docs))
        den = np.zeros(len(docs))
        numq = np.zeros(len(docs))
        for q in scored:
            i = di[doc_of[q]]
            r = rank_of.get(q, {})
            g = gold[q]
            # gold the index never ranked counts as a miss; the denominator is
            # every visual gold quote, not just the ones that happen to be
            # rankable. Shrinking it here is how recall silently inflates.
            num[i] += sum(1 for e in g if r.get(e, 10 ** 9) < k)
            numq[i] += sum(1 for e in g if r.get(e, 10 ** 9) < PAPER_QUOTA_IMG[k])
            den[i] += len(g)
        rec = num.sum() / den.sum()
        recq = numq.sum() / den.sum()
        lo, hi = cluster_ci(num, den)
        paper = PAPER_IMG_RECALL[k]
        metrics[k] = (rec, lo, hi, recq, paper)
        print(f"{k:>4}  {rec:>20.3f}  [{lo:>7.3f},{hi:>7.3f}]  "
              f"{recq:>14.3f}  {paper:>7.3f}")
        rows.append((k, rec, lo, hi, recq, paper))
    print("-" * 84)

    print()
    print("READING THIS")
    print("  The comparison column is the paper's ColQwen IMAGE recall. Its")
    print("  TEXT recall is not reproducible -- the paper never says how a")
    print("  visual retriever ranks text quotes -- so no text number appears.")
    print("  A CI containing the paper value means this implementation is")
    print("  consistent with theirs at that k; it does NOT mean the systems")
    print("  are the same. Parsing, image extraction and the model version")
    print("  (the paper names no version) all remain unverified.")
    inside = [k for k in KS if metrics[k][1] <= metrics[k][4] <= metrics[k][2]]
    print()
    if len(inside) == len(KS):
        print(f"  VERDICT: the paper's value falls inside the CI at every k "
              f"{list(KS)}.")
    elif inside:
        print(f"  VERDICT: consistent at k={inside}, but NOT at "
              f"k={[k for k in KS if k not in inside]}.")
    else:
        print("  VERDICT: the paper's value is outside the CI at every k. The")
        print("  pool is now the paper's size, so pool size no longer explains")
        print("  the gap; something else in this implementation differs.")

    with ExperimentResult("E34", args.metrics_out,
                          title="全池 ColQwen：与论文 Table 6 的量级核对") as res:
        res.config(retriever="ColQwen2-v1.0 (local), MaxSim late interaction",
                   pool="full document image pool (all images on disk)",
                   pool_mean_per_document=round(float(np.mean(pv)), 2),
                   paper_pool_per_document=63,
                   n_questions=len(scored), n_documents=len(docs),
                   bootstrap=BOOTSTRAP, sample_unit="document",
                   comparable_to_paper="image recall only",
                   partial_index=bool(partial),
                   document_sample="seeded random shuffle" if partial else "all")
        res.metric("n_evaluation_questions", len(qs), unit="questions")
        res.metric("n_documents_indexed", len(indexed_docs), unit="documents",
                   desc="documents this index covers; recall is estimated on "
                        "these only. With --doc-order random they are a simple "
                        "random sample, so the estimate is unbiased and the CI "
                        "reflects the sample size.")
        res.metric("n_documents_total", len(all_docs), unit="documents")
        res.metric("document_coverage", len(indexed_docs) / len(all_docs),
                   unit="fraction",
                   desc="1.0 means the whole evaluation corpus was indexed")
        res.metric("n_visual_gold_questions", len(scored), unit="questions",
                   desc="questions with at least one visual gold quote")
        res.metric("n_questions_without_visual_gold", n_no_gold,
                   unit="questions",
                   desc="no denominator for visual recall; outside the population")
        res.metric("n_visual_gold_questions_ranked", len(ranked),
                   unit="questions")
        res.metric("pool_mean_per_document", float(np.mean(pv)), unit="images")
        res.metric("pool_median_per_document", float(np.median(pv)), unit="images")
        res.metric("n_unpooled_ranked_entries", n_unpooled, unit="entries",
                   desc="ranked images that the official candidate pool never "
                        "contained; their presence is what makes this index "
                        "comparable to the paper and incomparable to the "
                        "description-side retrievers")
        for k, rec, lo, hi, recq, paper in rows:
            res.metric(f"recall@{k}_colqwen_fullpool", rec, ci=(lo, hi),
                       unit="recall", bootstrap_unit="document",
                       paper_value=paper,
                       paper_inside_ci=bool(lo <= paper <= hi),
                       desc="gold image quotes retrieved in the top k of the "
                            "full document image pool; gold the index never "
                            "ranked counts as a miss")
            res.metric(f"recall@{k}_colqwen_fullpool_quota", recq,
                       unit="recall",
                       desc=f"alternative reading: only the {PAPER_QUOTA_IMG[k]} "
                            f"visual slots the paper allots at total budget {k}. "
                            f"Reported because the paper states the quota for "
                            f"hybrid retrieval only, leaving the single-retriever "
                            f"columns ambiguous.")
        res.note("The paper's ColQwen TEXT recall is deliberately not compared: "
                 "the paper never describes how a visual retriever ranks text "
                 "quotes, so any number put beside it would be invented.")
        res.note("Agreement here is a magnitude check on this implementation, "
                 "not a reproduction of the paper's system. Model version, "
                 "PDF parsing and image extraction remain unverified, and the "
                 "paper names no version for any retriever.")
    if args.metrics_out:
        print(f"\nwrote metrics to {args.metrics_out}")


if __name__ == "__main__":
    main()
