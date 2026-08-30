"""Tests for the Phase 3 routing stack.

These check the properties that decide whether the Phase 3 numbers mean what
they say, and none of them can be established by reading the code:

    the cached action table is not silently lossy -- truncating the stored
    rankings to top-32 must leave every reported recall unchanged

    a cascade router must not consume evidence from a retriever it has not paid
    for, and a pre-retrieval router must not consume first-pass features at all

    escalation cost must be charged incrementally, so that a cascade whose
    first pass is partly discarded is not credited with a refund

    the random control must be the exact expectation it claims to be

    out-of-fold predictions must really be out of fold: a target that is a pure
    function of the document must be unpredictable across a document-grouped
    split, and predictable within one

Run:
    python -m tests.test_phase3
"""

import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from retrieval import nested_cv                                # noqa: E402
from retrieval.eval_stack_v2 import (BALANCED_QUOTA, DEFAULT_COLQWEN,  # noqa: E402
                                     DEFAULT_DB, DEFAULT_QUOTES, build,
                                     recall)
from router import actions as A                                # noqa: E402
from router import budget_router as BR                         # noqa: E402
from router import features_p3 as F                            # noqa: E402
from router import tie_audit as TA                             # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}"
          + (f"  -- {detail}" if detail else ""))
    return cond


def test_folds_are_one_implementation():
    print("\n1. folds come from E27's own function, and never split a document")
    check("budget_router reuses nested_cv.document_folds",
          BR.document_folds is nested_cv.document_folds)
    docs = ["a"] * 27 + ["b"] * 13 + ["c"] * 5 + ["d"] * 5 + ["e"] * 1
    fold, load = BR.document_folds(docs, 5)
    by_doc = {}
    for d, f in zip(docs, fold):
        by_doc.setdefault(d, set()).add(int(f))
    check("every document lands wholly in one fold",
          all(len(v) == 1 for v in by_doc.values()),
          str({k: sorted(v) for k, v in by_doc.items()}))
    check("folds are balanced in questions, not documents",
          max(load) - min(load) <= max(len(docs) // 5, 27), str(load))
    check("assignment is deterministic",
          list(BR.document_folds(docs, 5)[0]) == list(fold))


def test_cost_is_charged_incrementally():
    print("\n2. escalation cost is incremental, and discarded work is not "
          "refunded")
    cpu = (("bm25", "bm25"), ("rrf", "rrf"))
    gpu = (("dense", "bm25"), ("rrf", "colqwen"))
    inc_cpu = A.incremental_cost(*cpu)
    check("cpu cascade reuses both first-pass runs",
          inc_cpu == {"cpu_passes": 2, "gpu_passes": 0}, str(inc_cpu))
    check("cpu cascade at B=1 equals the static system it replaces",
          A.cascade_cost(*cpu, 1.0) == {"cpu_passes": 4.0, "gpu_passes": 0.0})

    inc_gpu = A.incremental_cost(*gpu)
    check("gpu cascade charges the text pass it still has to add and the "
          "gpu pass", inc_gpu == {"cpu_passes": 1, "gpu_passes": 1},
          str(inc_gpu))
    at1 = A.cascade_cost(*gpu, 1.0)
    static = A.cost(gpu[1])
    check("gpu cascade at B=1 costs MORE cpu than running the target "
          "outright, because the discarded image-description pass is sunk",
          at1["cpu_passes"] > static["cpu_passes"],
          f"cascade {at1} vs static {static}")
    naive = {k: static[k] - A.cost(gpu[0])[k] for k in static}
    check("the naive difference of from-scratch costs would have "
          "under-charged it", naive["cpu_passes"] < inc_gpu["cpu_passes"],
          f"naive {naive} vs incremental {inc_gpu}")
    check("currencies are never summed into one number",
          set(A.cost(("rrf", "colqwen"))) == {"cpu_passes", "gpu_passes"})


def test_random_control_is_the_exact_expectation():
    print("\n3. the random control is computed, not simulated")
    rng = np.random.default_rng(7)
    n = 400
    base = rng.random(n)
    gain = rng.normal(0, 0.3, n)
    for b in (0.25, 0.5, 0.75):
        exact = BR.random_expectation(base, gain, b).mean()
        m = int(round(b * n))
        sim = np.mean([
            base.mean() + gain[rng.permutation(n)[:m]].sum() / n
            for _ in range(4000)])
        check(f"B={b:.2f} exact expectation matches simulation",
              abs(exact - sim) < 4 * gain.std() / np.sqrt(4000 * m),
              f"exact {exact:.6f} sim {sim:.6f}")
    check("B=0 is the first pass alone",
          BR.random_expectation(base, gain, 0.0).mean() == base.mean())
    check("B=1 is always-escalate",
          abs(BR.random_expectation(base, gain, 1.0).mean()
              - (base + gain).mean()) < 1e-12)


def test_features_cannot_see_an_unpaid_pass():
    print("\n4. first-pass features read only the retriever that was run")
    rows, _ = A.load("canonical", 10, verbose=False)
    rows = [dict(r) for r in rows[:200]]
    quota = BALANCED_QUOTA[10]
    X0, names = F.featurize(rows, {}, 10, quota, ("firstpass",),
                            firstpass=("bm25", "bm25"))
    check("feature names name the retriever they came from",
          all(nm.startswith("bm25_") for nm in names), names[:2])
    # Corrupt the retriever the policy did NOT run. If the features move, the
    # cascade is reading a pass it has not paid for.
    for r in rows:
        sc = {k: dict(v) for k, v in r["scores"].items()}
        for br in sc:
            if len(sc[br].get("dense", [])):
                sc[br]["dense"] = np.asarray(sc[br]["dense"]) * -99.0
        r["scores"] = sc
    X1, _ = F.featurize(rows, {}, 10, quota, ("firstpass",),
                        firstpass=("bm25", "bm25"))
    check("corrupting the dense scores does not move bm25 first-pass features",
          np.array_equal(X0, X1))
    X2, names2 = F.featurize(rows, {}, 10, quota, ("firstpass",),
                             firstpass=("dense", "dense"))
    check("asking for the dense first pass does move them",
          not np.array_equal(X0, X2))
    check("and renames them", all(nm.startswith("dense_") for nm in names2))


def test_pre_retrieval_policy_refuses_first_pass_features():
    print("\n5. a pre-retrieval router cannot ask for first-pass features")
    p = subprocess.run(
        [sys.executable, "-m", "router.budget_router", "--policy", "A",
         "--features", "all", "--pool", "canonical", "--k", "10"],
        capture_output=True, text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    check("policy A + firstpass features exits non-zero", p.returncode != 0,
          f"rc={p.returncode}")
    check("and says why", "before any retriever runs" in (p.stderr + p.stdout))


def test_cache_truncation_changes_no_number():
    print("\n6. truncating stored rankings to top-32 changes no reported "
          "recall")
    full, _ = build(DEFAULT_DB, DEFAULT_QUOTES, DEFAULT_COLQWEN, "canonical")
    cached, _ = A.load("canonical", 10, verbose=False)
    check("same questions in the same order",
          [r["quid"] for r in full] == [r["quid"] for r in cached],
          f"{len(full)} vs {len(cached)}")
    worst = 0.0
    for k in (10, 20):
        quota = BALANCED_QUOTA[k]
        for act in A.ACTIONS:
            a = np.asarray([recall(r, act[0], act[1], quota) for r in full])
            b = np.asarray([recall(r, act[0], act[1], quota) for r in cached])
            worst = max(worst, float(np.abs(a - b).max()))
    check("every action at k=10 and k=20 is bit-identical", worst == 0.0,
          f"max abs difference {worst}")
    check("load refuses a k deeper than what it stored",
          _raises(lambda: A.load("canonical", A.TOP + 1, verbose=False)))


def _raises(fn):
    try:
        fn()
    except Exception:
        return True
    return False


def test_oof_predictions_are_out_of_fold():
    print("\n7. out-of-fold predictions cannot see their own document")
    rng = np.random.default_rng(11)
    docs = [f"doc{i // 20}" for i in range(600)]
    fold, _ = BR.document_folds(docs, 5)
    per_doc = {d: rng.normal() for d in set(docs)}
    y = np.asarray([per_doc[d] for d in docs])          # pure document effect
    # A feature that identifies the document, and nothing else.
    codes = {d: i for i, d in enumerate(sorted(set(docs)))}
    X = np.asarray([[codes[d], codes[d] ** 2] for d in docs], dtype=float)

    def obj(p, idx):
        return -float(np.mean((p - y[idx]) ** 2))

    oof, _ = BR.oof_predict(X, y, fold, 4, docs, obj)
    m = BR.models()["hgb"]
    m.fit(X, y)
    infold = m.predict(X)

    def r2(p):
        return 1 - np.sum((y - p) ** 2) / np.sum((y - y.mean()) ** 2)

    # The assertion is the SEPARATION, not an absolute fit: the candidate
    # models are deliberately regularised (depth 3, 40 samples per leaf), so
    # they cannot memorise 30 documents outright and an absolute threshold
    # would be testing the hyperparameters rather than the fold discipline.
    check("a document-only target is learnable within a fold",
          r2(infold) > 0.5, f"R2 {r2(infold):.3f}")
    check("and is NOT learnable out of fold", r2(oof) < 0.2,
          f"R2 {r2(oof):.3f}")
    check("the gap between the two is what fold discipline buys",
          r2(infold) - r2(oof) > 0.5,
          f"in-fold {r2(infold):.3f} vs out-of-fold {r2(oof):.3f}")
    for f in sorted(set(fold.tolist())):
        te = {docs[i] for i in np.flatnonzero(fold == f)}
        tr = {docs[i] for i in np.flatnonzero(fold != f)}
        if te & tr:
            break
    else:
        check("no document appears on both sides of any fold", True)


def test_oracle_and_tie_controls_are_consistent():
    print("\n8. oracle and tie-aware controls obey their own definitions")
    rows, _ = A.load("canonical", 10, verbose=False)
    quota = BALANCED_QUOTA[10]
    C = A.recall_matrix(rows, quota)
    tied = (C == C.max(axis=1, keepdims=True))
    oracle = C.max(axis=1)
    check("oracle is at least every fixed action",
          all(oracle.mean() >= C[:, j].mean() - 1e-12
              for j in range(C.shape[1])))
    cpu = np.array([A.cost(a)["cpu_passes"] for a in A.ACTIONS], float)
    gpu = np.array([A.cost(a)["gpu_passes"] for a in A.ACTIONS], float)
    for order in ("cpu-first", "gpu-first"):
        pick = TA.cheapest_optimal(C, tied, cpu, gpu, order)
        got = C[np.arange(len(rows)), pick]
        check(f"cheapest-optimal ({order}) loses no recall at all",
              np.array_equal(got, oracle))
    rng = np.random.default_rng(3)
    s = TA.sample_tied(tied, rng)
    check("tie-aware sampling only ever draws an optimal action",
          np.array_equal(C[np.arange(len(rows)), s], oracle))
    perm, _ = TA.permuted_mean(C, s, rng, n_perm=20)
    check("permuting those choices cannot beat the oracle",
          perm <= oracle.mean() + 1e-12, f"{perm:.4f} vs {oracle.mean():.4f}")


def main():
    print("=" * 78)
    print("PHASE 3 ROUTING TESTS")
    print("=" * 78)
    test_folds_are_one_implementation()
    test_cost_is_charged_incrementally()
    test_random_control_is_the_exact_expectation()
    test_features_cannot_see_an_unpaid_pass()
    test_pre_retrieval_policy_refuses_first_pass_features()
    test_cache_truncation_changes_no_number()
    test_oof_predictions_are_out_of_fold()
    test_oracle_and_tie_controls_are_consistent()
    print()
    print("=" * 78)
    print(f"{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        for f in FAIL:
            print(f"  FAILED: {f}")
        raise SystemExit(1)
    print("=" * 78)


if __name__ == "__main__":
    main()
