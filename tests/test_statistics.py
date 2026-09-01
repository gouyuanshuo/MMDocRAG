"""Tests for the statistical machinery every headline number rests on.

Six modules each carry their own `cluster_ci`. They agree today, but nothing
asserts that they do, and the whole project's credibility sits on those
intervals: if one copy drifts to resampling questions instead of documents, or
to a plain mean instead of a ratio of sums, the affected experiment reports a
narrower interval than the data supports and every check in the repository
still passes. These tests pin the properties rather than the code, so a
divergent copy fails here rather than in a report.

What is checked:

    all six clustered bootstraps agree, to the resolution their own resampling
    can resolve, on the same input

    the clustered interval genuinely responds to clustering -- injecting a pure
    document effect must widen it relative to resampling questions, because
    that effect is exactly what the question-level bootstrap cannot see

    the estimator is a ratio of sums, not a mean of per-document means, so
    documents contributing many questions carry their weight

    Holm-Bonferroni is a correct step-down: monotone, never below the raw
    p-value, never above Bonferroni, and identical to Bonferroni for the
    smallest p in the family

    the bootstrap p-value is floored at the resolution the resampling can
    actually resolve, so no script can print p = 0

Run:
    python -m tests.test_statistics
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from retrieval import ablation as AB                           # noqa: E402
from retrieval import eval_fullpool as FP                      # noqa: E402
from retrieval import eval_stack_v2 as ES                      # noqa: E402
from retrieval import nested_cv as NC                          # noqa: E402
from retrieval import route_outcome as RO                      # noqa: E402
from retrieval import slice_by_type as SL                      # noqa: E402
from router import tie_audit as TA                             # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))


def synthetic(n_docs=60, per_doc=12, doc_sd=0.05, q_sd=0.02, mu=0.01, seed=3):
    """Questions nested in documents, with a real document-level effect."""
    rng = np.random.default_rng(seed)
    docs, vals = [], []
    for d in range(n_docs):
        # documents differ in how many questions they carry, which is the case
        # that separates a ratio of sums from a mean of means
        m = per_doc + int(rng.integers(-6, 7))
        eff = rng.normal(0.0, doc_sd)
        for _ in range(max(m, 2)):
            docs.append(f"doc{d:03d}")
            vals.append(mu + eff + rng.normal(0.0, q_sd))
    return np.asarray(vals), np.asarray(docs)


# ------------------------------------------------------------------ tests
def test_all_cluster_ci_agree():
    d, docs = synthetic()
    got = {}
    for name, fn in (("ablation", AB.cluster_ci), ("nested_cv", NC.cluster_ci),
                     ("route_outcome", RO.cluster_ci),
                     ("tie_audit", TA.cluster_ci)):
        rng = np.random.default_rng(12345)
        r = fn(d, docs, rng)
        got[name] = (float(r[0]), float(r[1]), float(r[2]))
    # eval_stack_v2 takes two arms rather than a difference
    rng = np.random.default_rng(12345)
    r = ES.cluster_ci(d, np.zeros_like(d), docs, rng)
    got["eval_stack_v2"] = (float(r[0]), float(r[1]), float(r[2]))
    # slice_by_type takes an explicit mask, so an all-true mask is the same job
    keys, idx = SL._by_doc(docs)
    rng = np.random.default_rng(12345)
    r = SL.slice_ci(d, docs, [np.ones(len(i), dtype=bool) for i in idx], rng)
    got["slice_by_type"] = (float(r[0]), float(r[1]), float(r[2]))

    pts = [v[0] for v in got.values()]
    check("every cluster_ci returns the same point estimate",
          max(pts) - min(pts) < 1e-12,
          f"spread {max(pts) - min(pts):.2e} over {len(got)} implementations")

    # The bounds come from independent resampling streams in some copies, so
    # they cannot be identical; they must agree far inside their own noise.
    los = [v[1] for v in got.values()]
    his = [v[2] for v in got.values()]
    width = float(np.mean(his) - np.mean(los))
    check("every cluster_ci returns the same interval to within resampling noise",
          (max(los) - min(los)) < 0.15 * width
          and (max(his) - min(his)) < 0.15 * width,
          f"lo spread {max(los)-min(los):.2e}, hi spread {max(his)-min(his):.2e}, "
          f"width {width:.2e}")

    # eval_fullpool's variant takes per-document numerators and denominators
    num = np.array([d[docs == k].sum() for k in sorted(set(docs))])
    den = np.array([float((docs == k).sum()) for k in sorted(set(docs))])
    lo, hi = FP.cluster_ci(num, den)
    check("eval_fullpool's ratio bootstrap lands on the same interval",
          abs(lo - float(np.mean(los))) < 0.15 * width
          and abs(hi - float(np.mean(his))) < 0.15 * width,
          f"[{lo:+.5f},{hi:+.5f}] vs pooled "
          f"[{np.mean(los):+.5f},{np.mean(his):+.5f}]")


def test_clustering_actually_changes_the_interval():
    """A pure document effect must widen the clustered interval.

    This is the property that justifies the whole convention. If the two
    bootstraps returned the same width on data with a strong document effect,
    the clustered one would be decoration.
    """
    d, docs = synthetic(doc_sd=0.08, q_sd=0.005)
    rng = np.random.default_rng(7)
    _m, lo_c, hi_c, _n = TA.cluster_ci(d, docs, rng)
    rng = np.random.default_rng(7)
    _m2, lo_q, hi_q = ES.question_ci(d, np.zeros_like(d), rng)
    check("clustering widens the interval when the effect is per-document",
          (hi_c - lo_c) > 1.5 * (hi_q - lo_q),
          f"clustered {hi_c - lo_c:.5f} vs per-question {hi_q - lo_q:.5f}")

    # and it must NOT widen it materially when there is no document effect
    d2, docs2 = synthetic(doc_sd=0.0, q_sd=0.03)
    rng = np.random.default_rng(7)
    _m, lo_c2, hi_c2, _n = TA.cluster_ci(d2, docs2, rng)
    rng = np.random.default_rng(7)
    _m2, lo_q2, hi_q2 = ES.question_ci(d2, np.zeros_like(d2), rng)
    check("clustering does not inflate the interval when documents are alike",
          (hi_c2 - lo_c2) < 1.4 * (hi_q2 - lo_q2),
          f"clustered {hi_c2 - lo_c2:.5f} vs per-question {hi_q2 - lo_q2:.5f}")


def test_estimator_is_a_ratio_of_sums():
    """Documents must not be weighted equally regardless of size.

    Two documents, one with 100 questions at +1 and one with 2 questions at -1.
    The question-level mean is close to +1; a mean of per-document means is 0.
    The point estimate must be the former.
    """
    d = np.concatenate([np.ones(100), -np.ones(2)])
    docs = np.array(["big"] * 100 + ["small"] * 2)
    rng = np.random.default_rng(1)
    m, _lo, _hi, _n = TA.cluster_ci(d, docs, rng)
    check("point estimate weights documents by their question count",
          abs(m - (100 - 2) / 102.0) < 1e-12,
          f"got {m:.6f}, mean-of-means would be 0.0")


def test_holm_is_a_correct_step_down():
    for pv in ([0.001, 0.02, 0.04, 0.3, 0.9],
               [0.05] * 6,
               [0.0001, 0.0001, 0.5],
               [1.0, 0.9, 0.8]):
        adj = AB.holm(pv)
        m = len(pv)
        order = sorted(range(m), key=lambda i: pv[i])
        seq = [adj[i] for i in order]
        check(f"Holm is monotone in rank  {pv}",
              all(seq[i] <= seq[i + 1] + 1e-12 for i in range(len(seq) - 1)))
        check(f"Holm never reports below the raw p  {pv}",
              all(a >= p - 1e-12 for a, p in zip(adj, pv)))
        check(f"Holm never exceeds Bonferroni  {pv}",
              all(a <= min(1.0, m * p) + 1e-12 for a, p in zip(adj, pv)))
        check(f"Holm equals Bonferroni on the smallest p  {pv}",
              abs(adj[order[0]] - min(1.0, m * pv[order[0]])) < 1e-12)
    check("Holm on a family of one is the identity",
          abs(AB.holm([0.031])[0] - 0.031) < 1e-12)


def test_bootstrap_p_is_floored_at_its_own_resolution():
    """A resampling procedure cannot resolve a p below 1/n_boot."""
    d = np.full(600, 0.5)                      # overwhelming, never crosses zero
    docs = np.array([f"d{i // 10:02d}" for i in range(600)])
    rng = np.random.default_rng(4)
    _m, _lo, _hi, p = AB.cluster_ci(d, docs, rng, n_boot=1000)
    check("bootstrap p is floored at 1/n_boot rather than printed as zero",
          abs(p - 1.0 / 1000) < 1e-12, f"got p={p}")


def test_paired_contrast_keeps_the_pairing():
    """The full-pool paired bootstrap must beat an unpaired one on paired data.

    Two arms differing by a constant on every question: the difference has no
    variance at all, so a bootstrap that resamples the arms together must give
    a near-zero-width interval, while treating them as independent samples
    would not.
    """
    _d, docs = synthetic(seed=9)
    keys = sorted(set(docs))
    num_a = np.array([float((docs == k).sum()) * 0.6 for k in keys])
    num_b = np.array([float((docs == k).sum()) * 0.5 for k in keys])
    den = np.array([float((docs == k).sum()) for k in keys])
    pt, lo, hi, _p = FP.paired_cluster_ci(num_a, num_b, den)
    check("paired bootstrap collapses the interval when the difference is constant",
          abs(pt - 0.1) < 1e-9 and (hi - lo) < 1e-9,
          f"point {pt:.6f}, width {hi - lo:.2e}")


def main():
    print("=" * 78)
    print("STATISTICAL MACHINERY")
    print("=" * 78)
    test_all_cluster_ci_agree()
    test_clustering_actually_changes_the_interval()
    test_estimator_is_a_ratio_of_sums()
    test_holm_is_a_correct_step_down()
    test_bootstrap_p_is_floored_at_its_own_resolution()
    test_paired_contrast_keeps_the_pairing()
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
