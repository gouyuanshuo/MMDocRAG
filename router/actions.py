"""Phase 3 substrate: the per-query action table the router chooses from.

Every Phase 3 script scores the same object -- for each evaluation question, the
recall that each retrieval *action* would have achieved, and what that action
costs. Building it takes minutes (BM25 has to rank every document's pool for
every question), so it is built once per pool and cached.

Identity of the numbers
-----------------------
The rankings and the gold sets come from `retrieval.eval_stack_v2.build`, which
is E27's own builder, called here with `keep_scores=True`. Nothing is
recomputed and nothing is re-derived, so a Phase 3 recall and an E27 recall for
the same action are the same number by construction rather than by agreement.
The denominator is E27's: gold that the 8-gram mapper could not place is counted
as a miss, never dropped.

Rankings are truncated to TOP entries. Recall at quota (a, b) only ever slices
[:a] and [:b] with a + b = k, so any k <= TOP is unaffected; `load` asserts this
rather than trusting the caller.

The action space
----------------
An action is a pair (text retriever, visual retriever). The text branch runs
over text chunks, the visual branch over images. Three of the four visual
retrievers -- bm25, dense, rrf -- read the VLM-written image *descriptions* and
never see a pixel; only `colqwen` is visual retrieval. That naming discipline is
from E24/E34 and is kept in every label this module emits.

Cost
----
Two currencies, never added together:

    cpu_passes  how many single-retriever passes over a branch's pool the
                action runs. bm25 and dense cost 1, rrf costs 2 because it runs
                both and fuses their rank lists. Summed over the two branches,
                so RRF-everywhere costs 4 and a single retriever per branch
                costs 2.
    gpu_passes  ColQwen late-interaction scoring passes. 1 when the visual
                branch is ColQwen, 0 otherwise.

`cpu_seconds` is reported too, from the wall-clock measured while building the
table, but the headline cost is passes: seconds depend on this laptop and on
these pool sizes and would not transfer, whereas "does this query pay for one
retriever or two" is the quantity the proposal's budget question is about.

ColQwen's per-query GPU cost is a *scoring* pass against a prebuilt index; the
one-off indexing cost and the 4.49 GB of resident weights are deployment costs
that no per-query budget can amortise away, and they are reported as such rather
than folded into a per-query number.

Run:
    python -m router.actions --pool selfbuilt
    python -m router.actions --pool canonical --rebuild
"""

import argparse
import os
import pickle
import sys
import time

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retrieval.eval_stack_v2 import (BALANCED_QUOTA, DEFAULT_COLQWEN,  # noqa: E402
                                     DEFAULT_DB, DEFAULT_QUOTES,
                                     build, recall)
from retrieval.dense import MODEL as DENSE_MODEL                       # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(REPO_ROOT, "router", "cache")
TOP = 32                       # >= every k this project reports (10, 15, 20)

TEXT_RETRIEVERS = ("bm25", "dense", "rrf")
VISUAL_RETRIEVERS = ("bm25", "dense", "rrf", "colqwen")
ACTIONS = [(t, v) for t in TEXT_RETRIEVERS for v in VISUAL_RETRIEVERS]

# What each retriever actually runs. rrf is not a retriever, it is BM25 and
# dense plus a fusion of their rank lists, so it runs both of them. Keeping the
# decomposition rather than a scalar is what makes incremental cost expressible.
_PARTS = {"bm25": frozenset({"bm25"}), "dense": frozenset({"dense"}),
          "rrf": frozenset({"bm25", "dense"}),
          "colqwen": frozenset({"colqwen"})}
_GPU_PARTS = frozenset({"colqwen"})


def _price(parts):
    return {"cpu_passes": sum(1 for p in parts if p not in _GPU_PARTS),
            "gpu_passes": sum(1 for p in parts if p in _GPU_PARTS)}


def action_label(a):
    t, v = a
    tail = "colqwen visual" if v == "colqwen" else f"{v} image-description"
    return f"{t} text + {tail}"


def cost(action):
    """Cost of running `action` from scratch, as a static system would."""
    t, v = action
    a, b = _price(_PARTS[t]), _price(_PARTS[v])
    return {k: a[k] + b[k] for k in a}


def incremental_cost(cheap, expensive):
    """Extra cost of escalating a query that has already run `cheap`.

    Only passes the first stage did not already run are charged, per branch.
    Work the first stage did that the escalation throws away is NOT refunded --
    a cascade that runs BM25 over image descriptions and then decides to score
    the pixels with ColQwen has still paid for the BM25 pass. That is why a
    cascade can cost more in one currency than the static system it is trying
    to replace, and why this is computed rather than taken as the difference of
    two from-scratch costs.
    """
    cpu = gpu = 0
    for c, e in zip(cheap, expensive):
        add = _price(_PARTS[e] - _PARTS[c])
        cpu += add["cpu_passes"]
        gpu += add["gpu_passes"]
    return {"cpu_passes": cpu, "gpu_passes": gpu}


def cascade_cost(cheap, expensive, rate):
    """Mean cost per query of running `cheap` always and escalating `rate`."""
    base, inc = cost(cheap), incremental_cost(cheap, expensive)
    return {k: base[k] + rate * inc[k] for k in base}


def cache_path(pool, dense_model=DENSE_MODEL):
    tag = os.path.basename(str(dense_model).rstrip("/\\")).replace("/", "_")
    return os.path.join(CACHE_DIR, f"actions_{pool}_{tag}.pkl")


def load(pool="selfbuilt", k=None, dense_model=DENSE_MODEL, rebuild=False,
         db=DEFAULT_DB, quotes=DEFAULT_QUOTES, colqwen=DEFAULT_COLQWEN,
         verbose=True):
    """(rows, meta). Builds and caches on first call for a pool."""
    if k is not None and k > TOP:
        raise ValueError(f"k={k} exceeds stored ranking depth TOP={TOP}; "
                         "rebuild the cache with a larger TOP")
    path = cache_path(pool, dense_model)
    if os.path.exists(path) and not rebuild:
        with open(path, "rb") as fh:
            blob = pickle.load(fh)
        if blob.get("top", 0) < (k or 0):
            raise ValueError(f"cache stores top-{blob.get('top')}, "
                             f"k={k} needs more")
        return blob["rows"], blob["meta"]

    os.makedirs(CACHE_DIR, exist_ok=True)
    t0 = time.time()
    rows, meta = build(db, quotes, colqwen, pool, dense_model,
                       keep_scores=True, top_keep=TOP)
    meta["build_seconds"] = time.time() - t0
    meta["pool"] = pool
    meta["dense_model"] = str(dense_model)
    meta["top"] = TOP
    meta["n_questions"] = len(rows)
    blob = {"rows": rows, "meta": meta, "top": TOP}
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        pickle.dump(blob, fh, protocol=4)
    os.replace(tmp, path)
    if verbose:
        mb = os.path.getsize(path) / (1 << 20)
        print(f"[actions] built {len(rows)} questions in "
              f"{meta['build_seconds']:.0f}s; cache {path} = {mb:.1f} MB")
    return rows, meta


def per_query_seconds(meta):
    """Measured wall-clock for one pass of one retriever over one branch."""
    n = max(meta.get("n_questions", 0), 1)
    return {key: sec / n for key, sec in meta.get("timing", {}).items()}


def cpu_seconds(action, meta):
    s = per_query_seconds(meta)
    t, v = action

    def branch(r, kind):
        if r == "colqwen":
            return 0.0
        if r == "rrf":
            # rrf pays both inputs plus the fusion itself.
            return (s.get("bm25_" + kind, 0.0) + s.get("dense_" + kind, 0.0)
                    + s.get("rrf_" + kind, 0.0))
        return s.get(f"{r}_{kind}", 0.0)

    return branch(t, "text") + branch(v, "visual")


def recall_matrix(rows, quota, actions=ACTIONS):
    """(n_questions, n_actions) unconditional recall."""
    return np.asarray(
        [[recall(r, t, v, quota) for t, v in actions] for r in rows],
        dtype=np.float64)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pool", default="selfbuilt",
                    choices=("selfbuilt", "canonical"))
    ap.add_argument("--dense-model", default=DENSE_MODEL)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()

    rows, meta = load(args.pool, args.k, args.dense_model, args.rebuild)
    quota = BALANCED_QUOTA[args.k]
    C = recall_matrix(rows, quota)
    docs = sorted({r["doc"] for r in rows})
    path = cache_path(args.pool, args.dense_model)

    print("=" * 92)
    print(f"PHASE 3 ACTION TABLE   pool={args.pool}  k={args.k}  "
          f"quota={quota[0]}/{quota[1]}  dense={args.dense_model}")
    print("=" * 92)
    print(f"questions {len(rows)} over {len(docs)} documents; "
          f"gold {sum(r['n_total'] for r in rows)}, "
          f"unmapped counted as miss {sum(r['n_unmapped'] for r in rows)}")
    print(f"questions with a ColQwen ranking: "
          f"{sum(r['has_colqwen'] for r in rows)}/{len(rows)}")
    print(f"cache {os.path.getsize(path) / (1 << 20):.1f} MB at {path}")
    print()
    print(f"{'action':<44}{'recall':>9}{'cpu':>6}{'gpu':>6}{'cpu_s/q':>10}")
    print("-" * 75)
    for j in np.argsort(-C.mean(axis=0)):
        a = ACTIONS[j]
        c = cost(a)
        print(f"{action_label(a):<44}{C[:, j].mean():>9.4f}"
              f"{c['cpu_passes']:>6}{c['gpu_passes']:>6}"
              f"{cpu_seconds(a, meta):>10.4f}")
    print()
    print("cpu = single-retriever passes over a branch pool; gpu = ColQwen "
          "late-interaction\npasses. They are different currencies and are "
          "never added. bm25/dense/rrf on the\nvisual branch read VLM image "
          "descriptions, not pixels.")


if __name__ == "__main__":
    main()
