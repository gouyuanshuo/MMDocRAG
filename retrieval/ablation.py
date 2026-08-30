"""Factorial attribution for the static-pipeline gain (closes the E28 caveat).

Why this exists
---------------
The headline number compares the closest local paper-style hybrid (E) against
the nested-CV selected pipeline, and that comparison moves THREE things at once:

    text retriever      dense            -> RRF(bm25, dense)
    visual retriever    ColQwen (pixels) -> RRF(bm25, dense) over VLM descriptions
    quota               official 7/3     -> near-balanced

So the +0.0608 is a pipeline delta. The lab notebook already says an ablation is
required before attributing it to any one component; this is that ablation.

    SCOPE. This is attribution, not confirmation. Every cell is evaluated on all
    2,000 questions with a FIXED configuration, so the intervals describe how
    reliably each factor moves recall on this benchmark -- they do not re-earn
    the generalisation claim, which only `nested_cv.py` supports. The quota
    factor uses the pre-named BALANCED_QUOTA arm rather than the fold-selected
    quota, because the fold-selected value was chosen by looking at this data
    and using it as a factor level would smuggle that selection into the
    decomposition. The fold-selected cell is printed separately, as a bridge to
    the headline number, and is labelled as selected.

Reading the output
------------------
`main effect` is the average of the four paired differences in which that one
factor flips and the other two are held at each of their settings. When the
interactions are small, the three main effects approximately add up to the total
E -> (rrf, rrf, balanced) gap; the residual is printed so that can be checked
rather than assumed.

Run:
    python -m retrieval.ablation --pool canonical --k 10
    python -m retrieval.ablation --pool selfbuilt --k 20
"""

import argparse
import collections
import itertools
import os
import sys

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retrieval.eval_stack_v2 import (BALANCED_QUOTA, DEFAULT_COLQWEN,  # noqa: E402
                                     DEFAULT_DB, DEFAULT_QUOTES,
                                     PAPER_QUOTA, SEED, build, vec)
from expkit.results import ExperimentResult, add_output_args   # noqa: E402

BOOT = 4000
TEXT = [("dense", "dense"), ("rrf", "RRF(bm25,dense)")]
# The visual level names must carry what actually changes. Going from ColQwen to
# the description arm swaps the representation (pixels -> VLM-written text) AND
# the number of retrievers (one -> a BM25+BGE fusion). Shortening it to
# "representation effect" would credit a fusion gain to the representation.
VIS = [("colqwen", "ColQwen over images"),
       ("rrf", "BM25+BGE RRF over VLM descriptions")]
VISUAL_FACTOR_NAME = ("visual branch: ColQwen over images -> "
                      "BM25+BGE RRF over VLM descriptions")
TEXT_FACTOR_NAME = "text branch: BGE-small dense -> BM25+BGE RRF"
QUOTA_FACTOR_NAME = "modality quota: official -> balanced"
CELLS = [("selfbuilt", 10), ("selfbuilt", 20), ("canonical", 10), ("canonical", 20)]


def cluster_ci(d, docs, rng, n_boot=BOOT):
    """Document-clustered bootstrap: point estimate, 95% interval, two-sided p.

    The p-value is the usual bootstrap one -- twice the smaller tail mass on the
    wrong side of zero -- floored at 1/n_boot, because a resampling procedure
    cannot resolve a p smaller than its own resolution and reporting p=0 would
    claim otherwise.
    """
    by = collections.defaultdict(list)
    for i, x in enumerate(docs):
        by[x].append(i)
    ks = sorted(by)
    sd = np.array([d[by[x]].sum() for x in ks])
    sn = np.array([len(by[x]) for x in ks], dtype=float)
    p = rng.integers(0, len(ks), size=(n_boot, len(ks)))
    m = sd[p].sum(axis=1) / sn[p].sum(axis=1)
    lo, hi = np.percentile(m, [2.5, 97.5])
    tail = min((m <= 0).mean(), (m >= 0).mean())
    pval = max(2.0 * tail, 1.0 / n_boot)
    return d.mean(), lo, hi, pval


def holm(pvals, alpha=0.05):
    """Holm-Bonferroni step-down. Returns adjusted p-values in input order.

    Uniformly more powerful than Bonferroni at the same familywise error rate,
    and it needs no independence assumption -- which matters here, because the
    four cells share questions and the three factors share the same eight cells.
    """
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    adj = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        val = (m - rank) * pvals[i]
        running = max(running, val)          # enforce monotonicity
        adj[i] = min(1.0, running)
    return adj


def fmt(d, lo, hi, *_rest):
    star = "*" if (lo > 0 or hi < 0) else " "
    return f"{d:>+9.4f}  [{lo:+.4f},{hi:+.4f}]{star}"


def analyse_cell(pool, k, args, rng):
    """Everything the 2x2x2 design yields for one (pool, k) cell."""
    rows, _meta = build(args.db, args.quotes, args.colqwen, pool)
    docs = np.asarray([r["doc"] for r in rows])
    pa, ba = PAPER_QUOTA[k], BALANCED_QUOTA[k]
    quota = [(pa, f"official {pa[0]}/{pa[1]}"), (ba, f"balanced {ba[0]}/{ba[1]}")]

    cells = {}
    for (t, _), (v, _), (q, _) in itertools.product(TEXT, VIS, quota):
        cells[(t, v, q)] = vec(rows, t, v, q)
    base = cells[("dense", "colqwen", pa)]
    top = cells[("rrf", "rrf", ba)]
    tot = cluster_ci(top - base, docs, rng)

    eff = {}
    for name, axis in ((TEXT_FACTOR_NAME, 0), (VISUAL_FACTOR_NAME, 1),
                       (QUOTA_FACTOR_NAME, 2)):
        diffs = []
        levels = [TEXT, VIS, quota][axis]
        others = [x for i, x in enumerate((TEXT, VIS, quota)) if i != axis]
        for combo in itertools.product(*others):
            key_lo, key_hi, it = [], [], iter(combo)
            for i in range(3):
                if i == axis:
                    key_lo.append(levels[0][0])
                    key_hi.append(levels[1][0])
                else:
                    c = next(it)[0]
                    key_lo.append(c)
                    key_hi.append(c)
            diffs.append(cells[tuple(key_hi)] - cells[tuple(key_lo)])
        d = np.mean(diffs, axis=0)
        eff[name] = (d, cluster_ci(d, docs, rng))

    oat = {}
    for name, key in (("one_at_a_time: text branch only", ("rrf", "colqwen", pa)),
                      ("one_at_a_time: visual branch only", ("dense", "rrf", pa)),
                      ("one_at_a_time: quota only", ("dense", "colqwen", ba))):
        oat[name] = cluster_ci(cells[key] - base, docs, rng)

    resid = tot[0] - sum(v[1][0] for v in eff.values())
    return {
        "pool": pool, "k": k, "rows": rows, "docs": docs, "cells": cells,
        "quota": quota, "pa": pa, "ba": ba, "base": base, "top": top,
        "total": tot, "effects": eff, "one_at_a_time": oat, "residual": resid,
        "n_questions": len(rows), "n_documents": len(set(docs.tolist())),
        "n_unmapped": sum(r["n_unmapped"] for r in rows),
        "n_colqwen": sum(r["has_colqwen"] for r in rows),
    }


def print_cell(c):
    pool, k = c["pool"], c["k"]
    print("=" * 96)
    print(f"FACTORIAL ATTRIBUTION  pool={pool}  k={k}   "
          f"(component attribution, NOT external generalisation)")
    print("=" * 96)
    print(f"questions {c['n_questions']} over {c['n_documents']} documents; "
          f"unmapped gold counted as miss: {c['n_unmapped']}")
    print(f"questions with a ColQwen ranking: {c['n_colqwen']} "
          f"({c['n_colqwen'] / c['n_questions']:.1%})")
    print()
    print(f"{'text branch':<18}{'visual branch':<36}{'quota':<18}"
          f"{'recall@' + str(k):>12}")
    print("-" * 96)
    for (t, tn), (v, vn), (q, qn) in itertools.product(TEXT, VIS, c["quota"]):
        tag = ""
        if (t, v, q) == ("dense", "colqwen", c["pa"]):
            tag = "   <- E, paper-style"
        if (t, v, q) == ("rrf", "rrf", c["ba"]):
            tag = "   <- all three changed"
        print(f"{tn:<18}{vn:<36}{qn:<18}{c['cells'][(t, v, q)].mean():>12.4f}{tag}")
    print("-" * 96)
    print(f"{'TOTAL  E -> all three changed':<56}{fmt(*c['total'])}")
    print()
    print("MAIN EFFECTS  (each factor flipped alone, averaged over the other two)")
    print("-" * 96)
    for name, (_d, ci) in c["effects"].items():
        print(f"{name:<56}{fmt(*ci)}")
    print("-" * 96)
    print(f"{'sum of main effects':<56}"
          f"{sum(v[1][0] for v in c['effects'].values()):>+9.4f}")
    print(f"{'residual (interactions)':<56}{c['residual']:>+9.4f}")
    print()
    print("ONE-AT-A-TIME FROM E  (what a single substitution buys on its own)")
    print("-" * 96)
    for name, ci in c["one_at_a_time"].items():
        print(f"{name:<56}{fmt(*ci)}")
    print("-" * 96)


def record_cell(res, c):
    k = c["k"]
    for (t, tn), (v, vn), (q, qn) in itertools.product(TEXT, VIS, c["quota"]):
        res.metric(f"cell_recall@{k}[text={t},visual={v},quota={q[0]}/{q[1]}]",
                   c["cells"][(t, v, q)].mean(), text_retriever=t,
                   visual_retriever=v, quota=f"{q[0]}/{q[1]}",
                   desc=f"{tn} + {vn} + {qn}")
    tv, tlo, thi, tp = c["total"]
    res.metric(f"total_E_to_all_three@{k}", tv, ci=(tlo, thi), p_raw=tp,
               comparison="E (paper-style) -> all three changed")
    for name, (_d, (mv, lo, hi, pv)) in c["effects"].items():
        res.metric("main_effect: " + name, mv, ci=(lo, hi), p_raw=pv,
                   comparison=name)
    res.metric("interaction_residual", c["residual"],
               desc="total minus the sum of main effects; ~0 means additive")
    for name, (mv, lo, hi, pv) in c["one_at_a_time"].items():
        res.metric(name, mv, ci=(lo, hi), p_raw=pv, comparison="vs E (paper-style)")
    res.per_question([
        {"question_uid": r["quid"], "doc_name": r["doc"],
         "n_gold_total": r["n_total"], "n_gold_unmapped": r["n_unmapped"],
         "recall_E_paper_style": float(c["base"][i]),
         "recall_all_three_changed": float(c["top"][i]),
         "delta": float(c["top"][i] - c["base"][i])}
        for i, r in enumerate(c["rows"])])


SCOPE_NOTE = (
    "SCOPE: this is INTERNAL COMPONENT ATTRIBUTION, not external generalisation "
    "validation. Every cell uses a fixed configuration over all 2,000 questions "
    "of one benchmark that this project has already used to choose its methods. "
    "The intervals say how reliably each component moves recall HERE; they say "
    "nothing about a new corpus, and they do not re-earn the out-of-fold claim, "
    "which only nested_cv.py's document-grouped protocol supports."
)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--quotes", default=DEFAULT_QUOTES)
    ap.add_argument("--colqwen", default=DEFAULT_COLQWEN)
    ap.add_argument("--pool", default="canonical", choices=("selfbuilt", "canonical"))
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--all-cells", action="store_true",
                    help="run all four pool x k cells in one pass and apply Holm "
                         "across the 4 x 3 main-effect family. Holm needs every "
                         "p-value at once, so it cannot be assembled from four "
                         "separate processes.")
    add_output_args(ap)
    args = ap.parse_args()
    rng = np.random.default_rng(SEED)

    if not args.all_cells:
        c = analyse_cell(args.pool, args.k, args, rng)
        print_cell(c)
        print("A factor whose one-at-a-time interval spans zero did not carry the")
        print("gain on its own, however large the pipeline total is.")
        print()
        print("!! SINGLE-CELL MODE: the stars above are UNCORRECTED. The full")
        print("!! design reports 12 tests (4 cells x 3 main effects); use")
        print("!! --all-cells for the Holm-adjusted family.")
        print()
        print(SCOPE_NOTE)
        with ExperimentResult("E30", args.metrics_out,
                              title="归因消融（单格，未作多重比较校正）") as res:
            res.config(analysis="factorial_attribution", multiplicity="none",
                       pool=args.pool, k=args.k, seed=SEED, bootstrap=BOOT,
                       sample_unit="document", design="2x2x2 factorial",
                       n_questions=c["n_questions"], n_documents=c["n_documents"],
                       scope="internal component attribution")
            res.data_file(args.db, args.quotes, args.colqwen)
            record_cell(res, c)
            res.note("single-cell mode: stars are uncorrected; see --all-cells")
            res.note(SCOPE_NOTE)
        if args.metrics_out:
            print()
            print(f"wrote metrics to {args.metrics_out}")
        return

    # ---- full 2x2 family with Holm --------------------------------------
    analysed = []
    for pool, k in CELLS:
        c = analyse_cell(pool, k, args, rng)
        print_cell(c)
        print()
        analysed.append(c)

    family = []
    for c in analysed:
        for name, (_d, (mv, lo, hi, pv)) in c["effects"].items():
            family.append({"pool": c["pool"], "k": c["k"], "factor": name,
                           "value": mv, "ci_low": lo, "ci_high": hi, "p_raw": pv})
    adj = holm([f["p_raw"] for f in family])
    for f, a in zip(family, adj):
        f["p_holm"] = a
        f["significant_raw"] = bool(f["ci_low"] > 0 or f["ci_high"] < 0)
        f["significant_holm"] = bool(a < 0.05)

    print("=" * 116)
    print(f"HOLM-CORRECTED MAIN EFFECTS   family = {len(family)} tests "
          f"(4 pool x k cells x 3 factors),  alpha = 0.05")
    print("=" * 116)
    print(f"{'pool':<11}{'k':>3}  {'factor':<58}{'effect':>9}"
          f"{'raw 95% CI':>22}{'p_raw':>9}{'p_holm':>9}  sig")
    print("-" * 116)
    for f in sorted(family, key=lambda x: x["p_holm"]):
        ci = f"[{f['ci_low']:+.4f},{f['ci_high']:+.4f}]"
        sig = "**" if f["significant_holm"] else ("(raw)" if f["significant_raw"] else "")
        print(f"{f['pool']:<11}{f['k']:>3}  {f['factor']:<58}{f['value']:>+9.4f}"
              f"{ci:>22}{f['p_raw']:>9.4f}{f['p_holm']:>9.4f}  {sig}")
    print("-" * 116)
    n_raw = sum(f["significant_raw"] for f in family)
    n_holm = sum(f["significant_holm"] for f in family)
    print(f"raw 95% intervals excluding zero : {n_raw}/{len(family)}")
    print(f"surviving Holm at alpha=0.05     : {n_holm}/{len(family)}")
    print("** = survives Holm.  (raw) = raw interval excludes zero but the effect")
    print("does not survive correction; the raw intervals are kept above so the")
    print("correction hides nothing.")
    print(f"Bootstrap resolution floors p at 1/{BOOT} = {1 / BOOT:.5f}; a p at that")
    print("floor means 'smaller than this design can resolve', not 'zero'.")
    print()
    print(SCOPE_NOTE)

    with ExperimentResult("E30", args.metrics_out,
                          title="归因消融：四格 × 三主效应，Holm 校正") as res:
        res.config(analysis="factorial_attribution", multiplicity="holm",
                   family_size=len(family), alpha=0.05,
                   pool="all(selfbuilt,canonical)", k="all(10,20)",
                   seed=SEED, bootstrap=BOOT, sample_unit="document",
                   design="2x2x2 factorial per cell, 4 cells",
                   scope="internal component attribution, not external validation")
        res.data_file(args.db, args.quotes, args.colqwen)
        for c in analysed:
            record_cell(res, c)
        for f in family:
            res.metric(
                f"holm[{f['pool']}/k={f['k']}] {f['factor']}", f["value"],
                ci=(f["ci_low"], f["ci_high"]), p_raw=f["p_raw"],
                p_holm=f["p_holm"], significant_holm=f["significant_holm"],
                significant_raw_ci=f["significant_raw"], comparison=f["factor"],
                cell_pool=f["pool"], cell_k=f["k"], multiplicity="holm",
                family_size=len(family))
        res.metric("n_significant_raw", n_raw, desc="raw 95% intervals excluding 0")
        res.metric("n_significant_holm", n_holm, desc="surviving Holm at alpha=0.05")
        res.note(SCOPE_NOTE)
        res.note(f"Holm family = {len(family)} tests (4 cells x 3 main effects). "
                 f"Raw intervals are recorded alongside so the correction hides "
                 f"nothing.")
    if args.metrics_out:
        print()
        print(f"wrote metrics to {args.metrics_out}")


if __name__ == "__main__":
    main()
