"""Phase 3 headline: both cascades, all four cells, one Holm-corrected family.

`router.budget_router` answers one cell at a time and stars its intervals
without correction. That is fine for looking, and wrong for claiming: this
project ran two cascades over two pools and two budgets k, and reporting the
best of eight uncorrected tests as a finding is exactly the multiplicity error
the project has already committed once. Holm needs every p-value at once, so
the family has to be assembled inside one process.

The family
----------
    primary    router - random allocation AT THE SAME BUDGET, at the declared
               rate B = 0.50, for 2 cascades x 2 pools x 2 k = 8 tests.

               This is the comparison that carries the whole claim. Beating
               never-escalate is trivial -- escalation adds retrieval, so more
               of it helps on average. Beating a RANDOM choice of which queries
               to escalate is the only evidence that the router knows something
               about the query.

    secondary  router - always escalate, same eight cells, its own Holm family.
               This asks whether the router matches the static expensive system
               while paying for it on a fraction of queries.

B = 0.50 is declared here rather than read off the curves. The budget at which
each cascade first reaches the static system is also reported, but that budget
is chosen by looking at the data and is therefore descriptive, not a test.

The two cascades
----------------
    cpu   bm25 both branches -> RRF both branches. Escalation buys a second
          CPU retriever per branch. This is the "does fusion pay for this
          query" decision.
    gpu   dense text + bm25 image-description -> RRF text + ColQwen visual.
          Escalation buys a GPU late-interaction pass over the page pixels.
          This is the "does this query need to look at the images" decision.

They are different questions with different answers, which is why both are
reported rather than the better one.

Exploratory. This split has been observed since E9 and used to choose methods,
so even a Holm-surviving effect here is not a confirmed generalisation.

Run:
    python -m router.phase3_cells
    python -m router.phase3_cells --features firstpass --budget 0.25
"""

import argparse
import collections
import json
import os
import sys
import zlib

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retrieval.ablation import holm                          # noqa: E402
from retrieval.dense import MODEL as DENSE_MODEL             # noqa: E402
from retrieval.eval_stack_v2 import DEFAULT_DB, SEED, recall  # noqa: E402
from router import actions as A                              # noqa: E402
from router import features_p3 as F                          # noqa: E402
from router.budget_router import (BUDGETS, curve, curve_auc,  # noqa: E402
                                  document_folds, escalation_mask,
                                  load_questions, oof_predict,
                                  random_expectation)
from router.tie_audit import QUOTA_FAMILY                     # noqa: E402
from expkit.results import ExperimentResult, add_output_args  # noqa: E402

BOOT = 4000
CASCADES = collections.OrderedDict([
    ("cpu", (("bm25", "bm25"), ("rrf", "rrf"))),
    ("gpu", (("dense", "bm25"), ("rrf", "colqwen"))),
])
CELLS = [(p, k) for p in ("selfbuilt", "canonical") for k in (10, 20)]
# Candidate feature groups for --features search. Declared here, searched
# inside every training fold, never chosen by looking at a held-out score.
SEARCH_GROUPS = ("shape", "firstpass", "shape+firstpass", "cheap+firstpass",
                 "free")


def cluster_boot(d, docs, rng, n_boot=BOOT):
    """Document-clustered paired bootstrap: mean, CI and a two-sided p."""
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
    return (float(d.mean()), float(lo), float(hi),
            float(max(2.0 * tail, 1.0 / n_boot)), len(ks))


def analyse(name, pool, k, quota_family, features, budget, dense_model,
            folds, inner_folds, cache_dir=None):
    cheap, expensive = CASCADES[name]
    key = f"{name}_{pool}_k{k}_{features}_B{int(budget * 100)}"
    # Seeded from the cell's own identity, not from a stream shared with the
    # other cells: otherwise a run that reuses four cached cells consumes a
    # different amount of randomness than a run that computes all eight, and
    # the same command would print different numbers depending on what was
    # already on disk. crc32 rather than hash(), which is salted per process.
    rng = np.random.default_rng([SEED, zlib.crc32(key.encode())])
    path = os.path.join(cache_dir, key + ".json") if cache_dir else None
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    quota = QUOTA_FAMILY[quota_family][k]
    rows, _ = A.load(pool, k, dense_model)
    docs = [r["doc"] for r in rows]
    n = len(rows)
    qs = load_questions(DEFAULT_DB)
    if features == "search":
        # The feature group is chosen inside the fold, alongside the model
        # family, so no group is picked by looking at the result it produces.
        X = collections.OrderedDict(
            (g, F.featurize(rows, qs, k, quota, F.PRESETS[g], dense_model,
                            cheap)[0]) for g in SEARCH_GROUPS)
    else:
        X, _ = F.featurize(rows, qs, k, quota, F.PRESETS[features],
                           dense_model, cheap)
    base_v = np.asarray([recall(r, cheap[0], cheap[1], quota) for r in rows])
    exp_v = np.asarray([recall(r, expensive[0], expensive[1], quota)
                        for r in rows])
    gain = exp_v - base_v
    fold, _ = document_folds(docs, folds)

    def obj(p, idx):
        return curve_auc(p, gain[idx], base_v[idx].mean())

    pred, chosen = oof_predict(X, gain, fold, inner_folds, docs, obj)

    mask = escalation_mask(pred, budget, n)
    got = np.where(mask, exp_v, base_v)
    rnd = random_expectation(base_v, gain, budget)
    orc = np.where(escalation_mask(gain, budget, n), exp_v, base_v)

    router_c = curve(pred, gain, float(base_v.mean()))
    oracle_c = curve(gain, gain, float(base_v.mean()))
    random_c = np.asarray([random_expectation(base_v, gain, b).mean()
                           for b in BUDGETS])
    target = float(exp_v.mean())
    reach = [float(b) for b, v in zip(BUDGETS, router_c) if v >= target]

    inc = A.incremental_cost(cheap, expensive)
    out = {
        "cascade": name, "pool": pool, "k": k, "features": features,
        "budget": budget, "n": n, "n_documents": len(set(docs)),
        "cheap": A.action_label(cheap), "expensive": A.action_label(expensive),
        "cost_cheap": A.cost(cheap), "cost_expensive": A.cost(expensive),
        "cost_increment": inc,
        "cost_at_budget": A.cascade_cost(cheap, expensive, budget),
        "recall_cheap": float(base_v.mean()),
        "recall_expensive": target,
        "recall_router": float(got.mean()),
        "recall_random": float(rnd.mean()),
        "recall_oracle": float(orc.mean()),
        "auc_router": float(router_c.mean()),
        "auc_random": float(random_c.mean()),
        "auc_oracle": float(oracle_c.mean()),
        "capture": float((router_c.mean() - random_c.mean())
                         / max(oracle_c.mean() - random_c.mean(), 1e-9)),
        "budget_to_match_static": reach[0] if reach else None,
        "models": chosen,
        "frac_gain_positive": float((gain > 0).mean()),
        "frac_gain_zero": float((gain == 0).mean()),
    }
    for tag, other in (("vs_random", rnd), ("vs_always", exp_v),
                       ("oracle_regret", None)):
        a, b = (got, other) if other is not None else (orc, got)
        d, lo, hi, pv, nd = cluster_boot(a - b, docs, rng)
        out[tag] = {"delta": d, "ci_low": lo, "ci_high": hi, "p_raw": pv,
                    "n_documents": nd}
    if path:
        os.makedirs(cache_dir, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--features", default="search",
                    choices=tuple(F.PRESETS) + ("search",),
                    help="a named group, or 'search' to select the group "
                         "inside each training fold together with the model")
    ap.add_argument("--quota", default="balanced", choices=tuple(QUOTA_FAMILY))
    ap.add_argument("--budget", type=float, default=0.50)
    ap.add_argument("--dense-model", default=DENSE_MODEL)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--inner-folds", type=int, default=4)
    ap.add_argument("--cache-dir", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "router", "cache", "cells"),
        help="per-cell results are written here as they finish so an "
             "interrupted run resumes instead of restarting")
    ap.add_argument("--no-cache", action="store_true")
    add_output_args(ap)
    args = ap.parse_args()
    cache = None if args.no_cache else args.cache_dir

    cells = []
    for name in CASCADES:
        for pool, k in CELLS:
            cells.append(analyse(name, pool, k, args.quota, args.features,
                                 args.budget, args.dense_model, args.folds,
                                 args.inner_folds, cache))

    print("=" * 108)
    print(f"PHASE 3 ROUTING, ALL CELLS   features={args.features}  "
          f"declared budget B={args.budget:.2f}  quota={args.quota}  "
          f"folds={args.folds}/{args.inner_folds}")
    print("=" * 108)
    print("EXPLORATORY: this split has been observed since E9 and used to "
          "choose methods.")
    print()
    for name, (cheap, expensive) in CASCADES.items():
        c = A.cost(cheap)
        e = A.cost(expensive)
        i = A.incremental_cost(cheap, expensive)
        print(f"cascade {name}: {A.action_label(cheap)} "
              f"({c['cpu_passes']} cpu + {c['gpu_passes']} gpu)")
        print(f"{'':11}-> {A.action_label(expensive)} "
              f"({e['cpu_passes']} cpu + {e['gpu_passes']} gpu as a static "
              f"system; +{i['cpu_passes']} cpu +{i['gpu_passes']} gpu as an "
              f"escalation)")

    print()
    print("-" * 108)
    print(f"PRIMARY FAMILY: router - random allocation at B={args.budget:.2f}, "
          f"{len(cells)} tests, Holm-corrected")
    print("-" * 108)
    adj = holm([c["vs_random"]["p_raw"] for c in cells])
    for c, a in zip(cells, adj):
        c["vs_random"]["p_holm"] = a
    adj2 = holm([c["vs_always"]["p_raw"] for c in cells])
    for c, a in zip(cells, adj2):
        c["vs_always"]["p_holm"] = a

    print(f"{'cascade':>8}{'pool':>11}{'k':>4}{'cheap':>9}{'router':>9}"
          f"{'random':>9}{'oracle':>9}{'delta':>9}{'95% CI':>21}"
          f"{'p_raw':>8}{'p_holm':>8}  sig")
    print("-" * 108)
    for c in cells:
        v = c["vs_random"]
        sig = "**" if v["p_holm"] < 0.05 else (
            "(raw)" if (v["ci_low"] > 0 or v["ci_high"] < 0) else "")
        print(f"{c['cascade']:>8}{c['pool']:>11}{c['k']:>4}"
              f"{c['recall_cheap']:>9.4f}{c['recall_router']:>9.4f}"
              f"{c['recall_random']:>9.4f}{c['recall_oracle']:>9.4f}"
              f"{v['delta']:>+9.4f}"
              f"  [{v['ci_low']:>+7.4f},{v['ci_high']:>+7.4f}]"
              f"{v['p_raw']:>8.4f}{v['p_holm']:>8.4f}  {sig}")
    n_holm = sum(c["vs_random"]["p_holm"] < 0.05 for c in cells)
    print(f"surviving Holm at alpha=0.05: {n_holm}/{len(cells)}")

    print()
    print("-" * 108)
    print(f"SECONDARY FAMILY: router at B={args.budget:.2f} - always escalate, "
          f"own Holm correction")
    print("-" * 108)
    print(f"{'cascade':>8}{'pool':>11}{'k':>4}{'router':>9}{'always':>9}"
          f"{'delta':>9}{'95% CI':>21}{'p_raw':>8}{'p_holm':>8}  sig")
    print("-" * 96)
    for c in cells:
        v = c["vs_always"]
        sig = "**" if v["p_holm"] < 0.05 else (
            "(raw)" if (v["ci_low"] > 0 or v["ci_high"] < 0) else "")
        print(f"{c['cascade']:>8}{c['pool']:>11}{c['k']:>4}"
              f"{c['recall_router']:>9.4f}{c['recall_expensive']:>9.4f}"
              f"{v['delta']:>+9.4f}"
              f"  [{v['ci_low']:>+7.4f},{v['ci_high']:>+7.4f}]"
              f"{v['p_raw']:>8.4f}{v['p_holm']:>8.4f}  {sig}")
    n_holm2 = sum(c["vs_always"]["p_holm"] < 0.05 for c in cells)
    print(f"surviving Holm at alpha=0.05: {n_holm2}/{len(cells)}")

    print()
    print("-" * 108)
    print("HOW MUCH OF THE ORACLE THE ROUTER CAPTURES, AND WHAT IT COSTS")
    print("-" * 108)
    print(f"{'cascade':>8}{'pool':>11}{'k':>4}{'capture':>9}{'regret':>10}"
          f"{'B to match static':>20}{'cost there':>24}"
          f"{'static costs':>20}")
    print("-" * 106)
    for c in cells:
        b = c["budget_to_match_static"]
        cost_there = (A.cascade_cost(*CASCADES[c["cascade"]], b)
                      if b is not None else None)
        bs = f"{b:.2f}" if b is not None else "never"
        cs = (f"{cost_there['cpu_passes']:.2f} cpu + "
              f"{cost_there['gpu_passes']:.2f} gpu"
              if cost_there else "-")
        st = (f"{c['cost_expensive']['cpu_passes']:.2f} cpu + "
              f"{c['cost_expensive']['gpu_passes']:.2f} gpu")
        print(f"{c['cascade']:>8}{c['pool']:>11}{c['k']:>4}"
              f"{c['capture']:>9.1%}{c['oracle_regret']['delta']:>+10.4f}"
              f"{bs:>20}{cs:>24}{st:>20}")
    print()
    print("capture = (router AUC - random AUC) / (oracle AUC - random AUC) "
          "over the whole\nbudget grid: the share of the achievable "
          "query-specific advantage the router\nactually realises. The B "
          "column is read off the curve and is descriptive, not a\ntest.")

    with ExperimentResult("E36", metrics_out=args.metrics_out) as res:
        res.config(pool="both", k=0, seed=SEED, bootstrap=BOOT,
                   sample_unit="document", features=args.features,
                   quota_family=args.quota, declared_budget=args.budget,
                   folds=args.folds, inner_folds=args.inner_folds,
                   multiplicity="holm", family_size=len(cells),
                   dense_model=args.dense_model)
        for c in cells:
            tag = f"{c['cascade']}/{c['pool']}/k={c['k']}"
            res.metric(f"recall_router [{tag}]", c["recall_router"],
                       **{k2: c[k2] for k2 in ("cascade", "pool", "k",
                                               "recall_cheap",
                                               "recall_expensive",
                                               "recall_random",
                                               "recall_oracle", "capture")})
            v = c["vs_random"]
            res.metric(f"router_minus_random [{tag}]", v["delta"],
                       ci=[v["ci_low"], v["ci_high"]], p_raw=v["p_raw"],
                       p_holm=v["p_holm"],
                       significant_holm=bool(v["p_holm"] < 0.05),
                       n=c["n"], n_documents=v["n_documents"],
                       family="primary", cascade=c["cascade"],
                       cell_pool=c["pool"], cell_k=c["k"])
            v = c["vs_always"]
            res.metric(f"router_minus_always_escalate [{tag}]", v["delta"],
                       ci=[v["ci_low"], v["ci_high"]], p_raw=v["p_raw"],
                       p_holm=v["p_holm"],
                       significant_holm=bool(v["p_holm"] < 0.05),
                       n=c["n"], n_documents=v["n_documents"],
                       family="secondary", cascade=c["cascade"],
                       cell_pool=c["pool"], cell_k=c["k"])
            v = c["oracle_regret"]
            res.metric(f"oracle_regret [{tag}]", v["delta"],
                       ci=[v["ci_low"], v["ci_high"]], p_raw=v["p_raw"],
                       n=c["n"], n_documents=v["n_documents"],
                       cascade=c["cascade"])
            res.metric(f"budget_to_match_static [{tag}]",
                       c["budget_to_match_static"],
                       unit="escalation fraction", cascade=c["cascade"],
                       descriptive=True)
        res.metric("n_significant_holm_primary", n_holm,
                   desc="router beats random allocation at matched budget")
        res.metric("n_significant_holm_secondary", n_holm2,
                   desc="router matches or beats always-escalate")
        res.note("Primary family is router vs random allocation at the same "
                 "budget: beating never-escalate is trivial because "
                 "escalation adds retrieval. B=0.50 was declared before "
                 "reading the curves; the budget at which each cascade "
                 "reaches its static system is descriptive.")


if __name__ == "__main__":
    main()
