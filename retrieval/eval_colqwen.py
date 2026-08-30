"""The missing half of the crossover: a visual retriever on image quotes.

Every retrieval number in this project so far came from a text retriever -- BM25
or BGE over the VLM-written `img_description`. The paper's Table 6 crossover is
between text retrievers and a *visual* one, and that half has never been tested
here. This scores ColQwen2's late-interaction rankings against BM25's on exactly
the same image-quote pool, same queries, same gold.

The reference points from the paper, recall@20 on image gold:

    BGE (text)      74.2
    ColQwen (visual) 84.3      -> +10.1 for the visual retriever

Denominator discipline (2026-08-28)
-----------------------------------
This script used to skip gold that was absent from the candidate pool:

    if eid not in set(eids):
        continue

Today that skip fires zero times -- verified, `experiments.py verify E24` asserts
`E.visual_gold_missing_from_ranking == 0` -- so the published numbers are
unaffected. But the construct is a silent denominator shrink waiting to happen:
the moment a pool is rebuilt without some gold, recall would rise because the
hard cases quietly left the denominator, and nothing would say so. The
denominator is now built from ALL visual gold, out-of-pool gold counts as a
miss, and the four population figures are printed and recorded:

    total_visual_gold      every visual gold pair for these questions
    mapped_visual_gold     gold that exists in the candidate pool
    missing_visual_gold    gold that does not -- counted as miss, never dropped
    ranking_coverage       share of questions ColQwen actually ranked

Incomplete coverage is a hard failure by default. `--allow-partial` downgrades it
to a loud warning that is stamped into metrics.json and the manifest, because a
number computed on a subset must never be filed next to one computed on the
whole.

Pool scope, stated precisely
----------------------------
The pool covers 6,487 of the 13,999 unique images in the 220 evaluation
documents (46.34%), with a per-document median of 20 candidates. ColQwen ranks
100% of what is in the pool and no visual gold is absent from its full ranking
-- but being present in the ranking is NOT the same as entering top-k, and this
script measures the latter. So this is a fair in-pool ranking comparison, not a
retrieval comparison over the complete document image pool.

What the rrf_desc arm does and does not show (2026-08-29)
--------------------------------------------------------
The `rrf_desc` minus `colqwen` contrast used to be described as isolating "the
two representations". It does not. Going from ColQwen to RRF(BM25, BGE) over VLM
descriptions changes two things at once:

    representation          raw image pixels  ->  VLM-written text description
    retrieval architecture  one late-interaction retriever  ->  two retrievers
                            fused with reciprocal rank fusion

A single contrast that moves both cannot attribute its effect to either. It is a
complete VISUAL-BRANCH comparison -- what you get if you replace the whole visual
side of the pipeline -- and that is a legitimate, useful thing to measure. It is
just not a representation effect, and the result must not be reported as one.
Concretely: this run cannot support "VLM text beats pixels". It supports "in this
incomplete image pool, at the tight k=10 budget, the whole description-RRF branch
retrieves better than the whole ColQwen branch".

Coverage arithmetic is computed, never asserted
-----------------------------------------------
The three population figures below are easy to conflate and were previously
partly hard-coded as the literal 2000. They are now all derived from the
databases, and `experiments.py verify E24` checks that numerator, denominator and
ratio agree:

    n_evaluation_questions / n_evaluation_questions_ranked
        every question in the split, and how many ColQwen produced a ranking for
    n_visual_gold_questions / n_visual_gold_questions_ranked
        the subset that has visual gold at all -- the only questions a visual
        recall can be defined on
    questions_scored_here
        what the recall denominator was actually built from

Runs in the MAIN environment -- it only reads the rankings table that
retrieval/colqwen_index.py wrote from the isolated venv.

Run:
    python -m retrieval.eval_colqwen
    python -m retrieval.eval_colqwen --metrics-out artifacts/runs/x/experiments/E24
"""

import argparse
import collections
import os
import sqlite3
import statistics
import sys

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retrieval.bm25 import BM25                    # noqa: E402
from retrieval.corpus import normalize, tokenize   # noqa: E402
from retrieval.dense import load as load_dense     # noqa: E402
from expkit.results import ExperimentResult, add_output_args   # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO_ROOT, "canonical", "mmdocrag.sqlite")
DEFAULT_SCORES = os.path.join(REPO_ROOT, "retrieval", "colqwen_scores.sqlite")
KS = (1, 5, 10, 20)
RRF_C = 60
BOOTSTRAP = 4000
SEED = 20260825
RETRIEVERS = (("dense", "BGE dense over VLM-text"),
              ("bm25", "BM25 over VLM-text"),
              ("colqwen", "ColQwen2 (raw pixels)"),
              ("rrf_desc", "RRF(BM25,BGE) over VLM-text"),
              ("rrf", "RRF(BM25-text, ColQwen)"))

# The comparison this script exists for, named for what it actually varies.
# Both the representation AND the number/kind of retrievers change across it, so
# it is a whole-branch swap, not a representation contrast.
VISUAL_BRANCH = ("visual branch: BM25+BGE RRF over VLM descriptions "
                 "- ColQwen over raw images")
VISUAL_BRANCH_MEANING = (
    "Replaces the entire visual branch. This changes both representation "
    "(raw image pixels -> VLM-written descriptions) and retrieval architecture "
    "(one late-interaction retriever -> two retrievers fused by RRF). It is a "
    "complete visual-branch comparison, not an isolated representation effect.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--scores", default=DEFAULT_SCORES)
    ap.add_argument("--allow-partial", action="store_true",
                    help="proceed despite incomplete question/ranking coverage. "
                         "The shortfall is stamped into metrics.json and the "
                         "manifest; do NOT file the result beside a full run.")
    add_output_args(ap)
    args = ap.parse_args()

    if not os.path.exists(args.scores):
        raise SystemExit(f"no ColQwen rankings at {args.scores}; run "
                         f".venv-colpali/Scripts/python.exe -m retrieval.colqwen_index")

    con = sqlite3.connect(args.db)
    imgs = con.execute(
        "SELECT evidence_id, doc_name, img_description FROM canonical_evidence "
        "WHERE type <> 'text' ORDER BY doc_name, evidence_id").fetchall()
    qs = con.execute(
        "SELECT question_uid, doc_name, question FROM questions "
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

    cq = sqlite3.connect(args.scores)
    col = collections.defaultdict(list)
    n_unpooled = 0
    for quid, eid, rank in cq.execute(
            "SELECT question_uid, evidence_id, rank FROM ranking "
            "ORDER BY question_uid, rank"):
        col[quid].append(eid)
        if eid.startswith("unpooled:"):
            n_unpooled += 1
    cq.close()

    # A full-disk ColQwen index ranks every image in the document; BM25 and the
    # dense arm can only rank the 6,548 that carry a VLM description. Scoring
    # them side by side would hand ColQwen 2.1x the distractors and then report
    # the difference as a retriever effect. That comparison is not merely noisy,
    # it is measuring the pools -- so it is refused rather than annotated.
    if n_unpooled:
        raise SystemExit(
            f"\n{args.scores} is a FULL-DISK index: {n_unpooled} ranked entries "
            f"are outside the candidate pool.\n"
            f"This script compares ColQwen against BM25 and BGE over VLM "
            f"descriptions, and those two have no representation for an image "
            f"the pool never contained. Running here would give ColQwen 13,999 "
            f"candidates and its rivals 6,548, then report the gap as if it "
            f"were about the retrievers.\n"
            f"Use `python -m retrieval.eval_fullpool --scores {args.scores}` "
            f"for the ColQwen-only absolute recall that Table 6 is comparable "
            f"to. See docs/paper-baseline-audit.md.")

    by_doc = collections.OrderedDict()
    for eid, doc, desc in imgs:
        by_doc.setdefault(doc, []).append((eid, normalize(desc or "")))
    bm = {d: (BM25([tokenize(b) for _, b in v]), [e for e, _ in v])
          for d, v in by_doc.items()}
    pool_ids = {d: set(ids) for d, (_, ids) in bm.items()}

    # ---- population accounting, BEFORE any scoring -----------------------
    # Everything the questions ask for, whether or not retrieval can reach it.
    # Every figure here is counted from the two databases. Nothing is written as
    # a literal, because a literal cannot notice when the data underneath it
    # changes -- which is the whole failure mode this block guards against.
    q_with_gold = [(u, d, q) for u, d, q in qs if gold.get(u)]
    n_eval_q = len(qs)
    n_eval_q_ranked = sum(1 for u, _, _ in qs if u in col)
    cov_all = n_eval_q_ranked / n_eval_q if n_eval_q else 0.0
    total_visual_gold = sum(len(gold[u]) for u, _, _ in q_with_gold)
    mapped = missing = 0
    for u, d, _ in q_with_gold:
        pool = pool_ids.get(d, set())
        for eid in gold[u]:
            if eid in pool:
                mapped += 1
            else:
                missing += 1
    n_q_total = len(q_with_gold)
    n_q_ranked = sum(1 for u, _, _ in q_with_gold if u in col)
    ranking_coverage = n_q_ranked / n_q_total if n_q_total else 0.0
    n_no_visual_gold = n_eval_q - n_q_total
    pool_sizes_doc = [len(pool_ids.get(d, ())) for d in sorted(
        {d for _, d, _ in q_with_gold})]

    print("=" * 78)
    print("POPULATION (built before scoring, so the denominator cannot drift)")
    print("=" * 78)
    print(f"evaluation questions       : {n_eval_q}")
    print(f"  ...ColQwen ranked        : {n_eval_q_ranked}  "
          f"(coverage {cov_all:.4f})")
    print(f"questions with visual gold : {n_q_total}   "
          f"({n_no_visual_gold} have none and cannot enter a visual recall)")
    print(f"  ...ColQwen ranked        : {n_q_ranked}  "
          f"(coverage {ranking_coverage:.4f})")
    print(f"total_visual_gold          : {total_visual_gold}")
    print(f"mapped_visual_gold         : {mapped}")
    print(f"missing_visual_gold        : {missing}   <- counted as MISS, not dropped")
    if pool_sizes_doc:
        print(f"pool per document          : median "
              f"{statistics.median(pool_sizes_doc):.0f}, mean "
              f"{statistics.mean(pool_sizes_doc):.2f}, "
              f"min {min(pool_sizes_doc)}, max {max(pool_sizes_doc)}")

    partial = ranking_coverage < 1.0 or missing > 0
    if partial and not args.allow_partial:
        raise SystemExit(
            f"\nINCOMPLETE COVERAGE -- refusing to report.\n"
            f"  questions ranked   {n_q_ranked}/{n_q_total} "
            f"({ranking_coverage:.4f})\n"
            f"  gold out of pool   {missing}/{total_visual_gold}\n"
            f"Rebuild the ColQwen index, or pass --allow-partial to proceed with "
            f"the shortfall recorded. Reporting a recall whose denominator "
            f"silently shrank is the failure this check exists to prevent.")
    if partial:
        print("\n" + "!" * 78)
        print("!! PARTIAL RUN (--allow-partial). These numbers are NOT comparable")
        print("!! to a full run and are stamped as partial in metrics.json.")
        print("!" * 78)

    # ---- dense arm -------------------------------------------------------
    P, Q = load_dense("vlm")
    p_eid, p_doc, p_vec, p_type = P["eids"], P["docs"], P["vecs"], P["types"]
    q_vec = {str(u): v for u, v in zip(Q["quids"], Q["vecs"])}
    dn = collections.defaultdict(list)
    for i, doc in enumerate(p_doc):
        if str(p_type[i]) != "text":
            dn[str(doc)].append(i)
    dense_idx = {d: ([str(p_eid[i]) for i in rows], p_vec[np.asarray(rows)])
                 for d, rows in dn.items()}

    hits = {m: {k: 0 for k in KS} for m, _ in RETRIEVERS}
    # Per-question hit counts, kept so a paired delta can be resampled by
    # document. A difference of two ratios computed only in aggregate has no
    # interval, and reporting "ColQwen - BM25 = -0.015" with no interval invites
    # the reader to treat it as a real gap.
    hit_track = {}
    per_q = []
    n_scored = 0
    for quid, doc, question in q_with_gold:
        if doc not in bm:
            # no candidate pool at all: every gold for this question is a miss,
            # and the question still counts
            per_q.append({"question_uid": quid, "doc_name": doc,
                          "pool_size": 0, "n_gold": len(gold[quid]),
                          "n_gold_in_pool": 0, "ranked_by_colqwen": False})
            continue
        b, eids = bm[doc]
        order, _ = b.rank(tokenize((question or "").lower()))
        lex = [eids[i] for i in order]
        vis = col.get(quid, [])
        d_eids, d_vecs = dense_idx.get(doc, ([], None))
        if d_eids:
            sims = d_vecs @ q_vec[quid]
            den = [d_eids[i] for i in np.lexsort((np.arange(len(d_eids)), -sims))]
        else:
            den = []
        # two different fusions, deliberately kept apart:
        #   rr   = BM25-over-descriptions + ColQwen   (contains the visual arm)
        #   rrd  = BM25 + BGE, both over descriptions (no pixels at all)
        # rrd vs ColQwen is a whole-visual-branch swap: it changes the
        # representation and the retrieval architecture together. rr vs ColQwen
        # cannot even do that much, because rr contains ColQwen -- it measures
        # complementarity only. Neither contrast isolates a representation.
        fused = collections.defaultdict(float)
        for lst in (lex, vis):
            for r, e in enumerate(lst):
                fused[e] += 1.0 / (RRF_C + r + 1)
        rr = sorted(fused, key=lambda e: -fused[e])
        fused_d = collections.defaultdict(float)
        for lst in (lex, den):
            for r, e in enumerate(lst):
                fused_d[e] += 1.0 / (RRF_C + r + 1)
        rrd = sorted(fused_d, key=lambda e: -fused_d[e])
        n_scored += 1

        pos_of = {name: {e: i for i, e in enumerate(lst)}
                  for name, lst in (("bm25", lex), ("dense", den),
                                    ("colqwen", vis), ("rrf", rr),
                                    ("rrf_desc", rrd))}
        row = {"question_uid": quid, "doc_name": doc,
               "pool_size": len(eids), "n_gold": len(gold[quid]),
               "n_gold_in_pool": sum(1 for e in gold[quid] if e in pool_ids[doc]),
               "ranked_by_colqwen": quid in col}
        hit_track.setdefault("_doc", []).append(doc)
        hit_track.setdefault("_gold", []).append(len(gold[quid]))
        for name, _ in RETRIEVERS:
            for k in KS:
                # gold outside the pool has no position and therefore misses --
                # it is never removed from the count
                h = sum(1 for e in gold[quid] if pos_of[name].get(e, 10 ** 9) < k)
                hits[name][k] += h
                hit_track.setdefault((name, k), []).append(h)
                if k in (10, 20):
                    row[f"{name}_hits@{k}"] = h
                    row[f"{name}_recall@{k}"] = h / len(gold[quid])
        per_q.append(row)

    den = total_visual_gold          # THE denominator: never the mapped subset
    print()
    print("=" * 78)
    print("IMAGE-QUOTE RETRIEVAL: text retriever vs visual retriever")
    print(f"denominator = total_visual_gold = {den} "
          f"(unconditional; {missing} out-of-pool gold counted as miss)")
    print("=" * 78)
    print(f"{'retriever':<26}" + "".join(f"{'@' + str(k):>11}" for k in KS))
    print("-" * 78)
    for name, label in RETRIEVERS:
        print(f"{label:<26}" + "".join(f"{hits[name][k] / den:>11.3f}" for k in KS))
    print("-" * 78)
    d = [(hits["colqwen"][k] - hits["bm25"][k]) / den for k in KS]
    print(f"{'ColQwen - BM25':<26}" + "".join(f"{v:>+11.3f}" for v in d))
    print()
    print("paper Table 6, image gold @20: BGE 0.742, ColQwen 0.843 (+0.101).")
    print("Pool differs: 6,487 of 13,999 unique evaluation images (46.34%),")
    print("per-document median 20 candidates, so @20 is near-saturated here and")
    print("absolute recall runs optimistic. This is a fair IN-POOL ranking")
    print("comparison, not a retrieval comparison over the full image pool.")

    # ---- paired deltas, resampled by DOCUMENT ----------------------------
    # The estimator matches the headline: a ratio of summed hits to summed gold,
    # not a mean of per-question recalls. Resampling documents rather than
    # questions is required because questions within a document share evidence;
    # one document here contributes 169 questions.
    rng = np.random.default_rng(SEED)
    docs_arr = np.asarray(hit_track.get("_doc", []))
    gold_arr = np.asarray(hit_track.get("_gold", []), dtype=float)
    by_doc = collections.defaultdict(list)
    for i, dnm in enumerate(docs_arr):
        by_doc[dnm].append(i)
    doc_keys = sorted(by_doc)
    doc_gold = np.array([gold_arr[by_doc[d]].sum() for d in doc_keys])

    def paired_ci(a_name, b_name, k, n_boot=BOOTSTRAP):
        a = np.asarray(hit_track[(a_name, k)], dtype=float)
        b = np.asarray(hit_track[(b_name, k)], dtype=float)
        d = a - b
        doc_d = np.array([d[by_doc[x]].sum() for x in doc_keys])
        pick = rng.integers(0, len(doc_keys), size=(n_boot, len(doc_keys)))
        means = doc_d[pick].sum(axis=1) / doc_gold[pick].sum(axis=1)
        lo, hi = np.percentile(means, [2.5, 97.5])
        return d.sum() / gold_arr.sum(), lo, hi

    COMPARISONS = [
        ("ColQwen - BM25", "colqwen", "bm25",
         "single-retriever contrast holding the architecture fixed: ColQwen over "
         "raw images minus BM25 over VLM descriptions"),
        ("ColQwen - BGE", "colqwen", "dense",
         "single-retriever contrast holding the architecture fixed: ColQwen over "
         "raw images minus BGE-small over VLM descriptions"),
        (VISUAL_BRANCH, "rrf_desc", "colqwen", VISUAL_BRANCH_MEANING),
        ("fusion complementarity: RRF(BM25 descriptions, ColQwen) - ColQwen alone",
         "rrf", "colqwen",
         "The fused arm CONTAINS ColQwen, so this measures what BM25 over "
         "descriptions adds on top of ColQwen -- complementarity. It cannot say "
         "which representation or which architecture is better."),
    ]
    print()
    print("=" * 92)
    print("PAIRED DELTAS  --  document-cluster bootstrap "
          f"(B={BOOTSTRAP}, resampling {len(doc_keys)} documents)")
    print("=" * 92)
    SHORT = {
        "ColQwen - BM25": "ColQwen - BM25",
        "ColQwen - BGE": "ColQwen - BGE",
        VISUAL_BRANCH: "visual branch: descRRF - ColQwen",
        "fusion complementarity: RRF(BM25 descriptions, ColQwen) - ColQwen alone":
            "complementarity: desc+ColQwen - ColQwen",
    }
    print(f"{'comparison':<40}{'k':>4}{'delta':>10}{'doc-cluster 95% CI':>28}")
    print("-" * 92)
    paired_out = []
    for label, an, bn, desc in COMPARISONS:
        for k in (10, 20):
            dv, lo, hi = paired_ci(an, bn, k)
            star = "*" if (lo > 0 or hi < 0) else " "
            print(f"{SHORT[label]:<40}{k:>4}{dv:>+10.4f}"
                  f"{'[' + format(lo, '+.4f') + ',' + format(hi, '+.4f') + ']' + star:>28}")
            paired_out.append((label, an, bn, desc, k, dv, lo, hi))
    print("-" * 92)
    print("* = interval excludes zero. Eight comparisons here; no multiplicity")
    print("correction is applied, so read a single starred row cautiously.")
    print()
    print("HOW TO READ THESE ROWS")
    print("  ColQwen - BM25 / - BGE hold the architecture fixed at one retriever")
    print("  and vary the retriever, so they are the closest thing here to a")
    print("  like-for-like contrast; both intervals cross zero at k=10 and k=20.")
    print()
    print(f"  '{SHORT[VISUAL_BRANCH]}' swaps the ENTIRE visual branch.")
    print("  It changes representation (raw pixels -> VLM descriptions) AND")
    print("  architecture (one late-interaction retriever -> two fused by RRF)")
    print("  at the same time. A contrast that moves two things cannot attribute")
    print("  its effect to either, so this is a complete visual-branch")
    print("  comparison, NOT an isolated representation effect. The supportable")
    print("  claim is: in this incomplete image pool, at the tight k=10 budget,")
    print("  the whole description-RRF branch retrieves better. It does NOT show")
    print("  that VLM text representations beat pixel representations.")
    print()
    print("  'complementarity' contains ColQwen inside the fused arm, so it only")
    print("  measures what BM25 over descriptions adds on top of ColQwen.")

    print()
    print("COVERAGE, in the units that are easy to conflate (all counted, none literal)")
    print("-" * 92)
    print(f"  n_evaluation_questions                  {n_eval_q}")
    print(f"  n_evaluation_questions_ranked           {n_eval_q_ranked}")
    print(f"  ranking_coverage_all_questions          {cov_all:.4f}"
          f"   = {n_eval_q_ranked}/{n_eval_q}")
    print(f"  n_visual_gold_questions                 {n_q_total}")
    print(f"  n_visual_gold_questions_ranked          {n_q_ranked}")
    print(f"  ranking_coverage_visual_gold_questions  {ranking_coverage:.4f}"
          f"   = {n_q_ranked}/{n_q_total}")
    print(f"  questions_scored_here                   {n_scored}")
    print(f"  The remaining {n_no_visual_gold} question(s) have no visual gold at all. They are")
    print("  not a coverage shortfall: a visual recall has no denominator for them,")
    print("  so they cannot enter it. Excluding them narrows the POPULATION, not the")
    print("  denominator of the population that is reported.")
    print()
    print("  A ranking that covers the whole candidate pool is NOT the same as")
    print("  entering top-k. ColQwen ranks every image in every document's pool and")
    print("  no visual gold is absent from its full ranking -- yet its Recall@10 is")
    print(f"  {hits['colqwen'][10] / den:.3f} and Recall@20 is {hits['colqwen'][20] / den:.3f},")
    print("  because top-k is what the metric measures. 'Nothing was missed by the")
    print("  index' and 'nothing was missed by the retrieval' are different claims.")

    # ---- structured output ----------------------------------------------
    with ExperimentResult("E24", args.metrics_out,
                          title="ColQwen2 vs image-description retrieval") as res:
        res.config(pool="canonical-image-quotes", k=20, sample_unit="document",
                   retrievers=[n for n, _ in RETRIEVERS], rrf_c=RRF_C,
                   allow_partial=bool(args.allow_partial), partial=bool(partial),
                   denominator="unconditional (total_visual_gold)")
        res.data_file(args.db, args.scores)
        res.metric("total_visual_gold", total_visual_gold, unit="gold pairs")
        res.metric("mapped_visual_gold", mapped, unit="gold pairs")
        res.metric("missing_visual_gold", missing, unit="gold pairs",
                   desc="out of pool; counted as miss")
        # Coverage as an explicit numerator/denominator/ratio triple in each of
        # the two populations. `verify E24` recomputes the ratios from the
        # counts, so a drifting name or a stale literal fails rather than
        # quietly reading as a full-coverage run.
        res.metric("n_evaluation_questions", n_eval_q, unit="questions",
                   desc="every question in the evaluation split")
        res.metric("n_evaluation_questions_ranked", n_eval_q_ranked,
                   unit="questions", desc="of those, ranked by ColQwen")
        res.metric("ranking_coverage_all_questions", cov_all,
                   numerator=n_eval_q_ranked, denominator=n_eval_q,
                   desc="ranked / all evaluation questions")
        res.metric("n_visual_gold_questions", n_q_total, unit="questions",
                   desc="questions with at least one visual gold evidence")
        res.metric("n_visual_gold_questions_ranked", n_q_ranked, unit="questions")
        res.metric("ranking_coverage_visual_gold_questions", ranking_coverage,
                   numerator=n_q_ranked, denominator=n_q_total,
                   desc="ranked / questions with visual gold")
        res.metric("n_questions_without_visual_gold", n_no_visual_gold,
                   unit="questions",
                   desc="no visual recall is defined for these; excluded from "
                        "the population, not from the denominator")
        res.metric("ranking_coverage", ranking_coverage,
                   numerator=n_q_ranked, denominator=n_q_total,
                   desc="deprecated alias of ranking_coverage_visual_gold_questions")
        res.metric("questions_with_visual_gold", n_q_total, unit="questions",
                   desc="deprecated alias of n_visual_gold_questions")
        res.metric("pool_median_per_document",
                   statistics.median(pool_sizes_doc) if pool_sizes_doc else 0,
                   desc="per document, NOT question-weighted")
        res.metric("pool_mean_per_document",
                   statistics.mean(pool_sizes_doc) if pool_sizes_doc else 0)
        for name, label in RETRIEVERS:
            for k in KS:
                res.metric(f"recall@{k}_{name}", hits[name][k] / den,
                           retriever=name, k_eval=k, desc=label)
        for label, an, bn, desc, k, dv, lo, hi in paired_out:
            res.metric(f"paired_delta[{label}]@{k}", dv, ci=(lo, hi),
                       comparison=label, k_eval=k, desc=desc,
                       bootstrap_unit="document", n_documents=len(doc_keys))
        res.metric("questions_scored_here", n_scored, unit="questions",
                   desc="questions that actually contributed to the recall "
                        "numerator and denominator")
        res.note(f"Coverage: {n_eval_q_ranked}/{n_eval_q} evaluation questions "
                 f"ranked ({cov_all:.4f}); {n_q_ranked}/{n_q_total} "
                 f"visual-gold questions ranked ({ranking_coverage:.4f}); "
                 f"{n_scored} scored. {n_no_visual_gold} question(s) have no "
                 f"visual gold, so no visual recall is defined for them. "
                 f"Covering the full candidate pool in the ranking is not the "
                 f"same as entering top-k -- the metric measures top-k.")
        res.note("The visual-branch comparison (BM25+BGE RRF over VLM "
                 "descriptions vs ColQwen over raw images) changes both the "
                 "representation and the retrieval architecture. It is a "
                 "complete visual-branch comparison, not an isolated "
                 "representation effect, and must not be reported as evidence "
                 "that text descriptions beat pixels.")
        res.per_question(per_q)
        if partial:
            res.note("PARTIAL RUN: coverage incomplete; not comparable to a full run")
        res.note("Pool covers 6,487 / 13,999 unique evaluation images (46.34%). "
                 "Being present in the full ranking is not the same as entering "
                 "top-k; this measures top-k.")
    if args.metrics_out:
        print(f"\nwrote metrics to {args.metrics_out}")


if __name__ == "__main__":
    main()
