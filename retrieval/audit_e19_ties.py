"""E19 re-audit: what survives once the oracle stops breaking ties by argmin.

`budget_alloc.py` computes the per-question optimal text/image split with
`C.argmax(axis=1)`. Recall at a given split is a ratio of small integers -- most
questions have two or three gold items -- so the curve over splits is a step
function with long flat tops, and many splits are tied at the maximum. NumPy's
argmax returns the *first* of them, which is systematically the smallest text
quota. Two consequences, both of which inflate the reported headroom:

    the oracle is not "the best split for this query", it is "the most extreme
    of the splits that are equally best", and

    the permuted control inherits that same extreme marginal distribution, so
    it assigns an extreme split to every question and looks worse than a
    realistic alternative policy would.

The quantity E19 reported as query-specific structure, oracle minus permuted,
is therefore an upper bound on an upper bound. This script reports the
tie-aware versions instead:

    tie count            how much of the optimum is actually a plateau
    fixed-is-optimal     fraction of questions where the single best fixed split
                         is already among the optimal ones -- the sharpest test,
                         because those questions contain no query-specific signal
                         at all by construction
    closest-to-fixed     an oracle restricted to the tied-optimal split nearest
                         the fixed policy; the gap it still leaves over the fixed
                         policy is the part that genuinely needs per-query choice
    safe interval        the median width of the contiguous optimal plateau
    regret               what the fixed policy loses per question

Run:
    python -m retrieval.audit_e19_ties --pool selfbuilt --k 20
"""

import argparse
import collections
import os
import sys

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retrieval.budget_alloc import (DEFAULT_DB, PAPER_QUOTA, SEED,   # noqa: E402
                                    build_cached, curve)

BOOT = 2000


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--pool", default="selfbuilt", choices=("canonical", "selfbuilt"))
    ap.add_argument("--k", type=int, default=20)
    args = ap.parse_args()
    k = args.k

    rows = build_cached(args.db, pool=args.pool)
    C = curve(rows, k)
    n = len(C)
    print("=" * 80)
    print(f"E19 TIE AUDIT   pool={args.pool}  k={k}  questions={n}")
    print("=" * 80)

    best = C.max(axis=1, keepdims=True)
    tied = (C == best)                       # boolean, n x (k+1)
    n_tied = tied.sum(axis=1)
    fixed_a = int(C.mean(axis=0).argmax())
    fixed = C[:, fixed_a].mean()
    oracle = C.max(axis=1).mean()

    print(f"best fixed split                  : text {fixed_a} / image {k - fixed_a}")
    print(f"questions with >1 optimal split   : {np.mean(n_tied > 1):.1%}")
    print(f"median number of tied optima      : {np.median(n_tied):.0f} of {k + 1}")
    print(f"mean number of tied optima        : {n_tied.mean():.1f}")

    # contiguity of the plateau: how wide is the safe interval around it
    widths = []
    for i in range(n):
        idx = np.flatnonzero(tied[i])
        widths.append(idx.max() - idx.min() + 1)
    print(f"median width of optimal interval  : {np.median(widths):.0f} splits")
    print(f"fixed split is ALREADY optimal for: {tied[:, fixed_a].mean():.1%} "
          f"of questions")

    print()
    print("-" * 80)
    print("ORACLE VARIANTS")
    print("-" * 80)
    # closest tied-optimal split to the fixed policy
    cols = np.arange(k + 1)
    dist = np.abs(cols[None, :] - fixed_a)
    masked = np.where(tied, dist, 10 ** 6)
    closest = masked.argmin(axis=1)
    closest_val = C[np.arange(n), closest].mean()

    rng = np.random.default_rng(SEED)
    # argmin-tie oracle (what E19 used) and its permuted control
    opt_first = C.argmax(axis=1)
    perm = rng.permutation(n)
    permuted_first = C[np.arange(n), opt_first[perm]].mean()

    # tie-aware: sample uniformly from each question's own optimal set, then
    # permute. This keeps the control's marginal distribution honest.
    def sample_tied():
        out = np.empty(n, dtype=int)
        for i in range(n):
            idx = np.flatnonzero(tied[i])
            out[i] = idx[rng.integers(0, len(idx))]
        return out

    tie_perm = []
    for _ in range(20):
        s = sample_tied()
        tie_perm.append(C[np.arange(n), s[rng.permutation(n)]].mean())
    permuted_tie = float(np.mean(tie_perm))

    print(f"{'policy':<44}{'recall':>10}")
    print(f"{'best fixed split':<44}{fixed:>10.4f}")
    print(f"{'ORACLE (any optimal split)':<44}{oracle:>10.4f}")
    print(f"{'oracle restricted to closest-to-fixed':<44}{closest_val:>10.4f}")
    print(f"{'permuted control, argmin ties (E19)':<44}{permuted_first:>10.4f}")
    print(f"{'permuted control, tie-aware sampling':<44}{permuted_tie:>10.4f}")
    print()
    print(f"{'apparent headroom (oracle - fixed)':<44}{oracle - fixed:>+10.4f}")
    print(f"{'E19 query-specific (oracle - perm_first)':<44}"
          f"{oracle - permuted_first:>+10.4f}   <- the reported number")
    print(f"{'tie-aware  (oracle - perm_tieaware)':<44}"
          f"{oracle - permuted_tie:>+10.4f}   <- corrected")
    print(f"{'regret of fixed policy':<44}{oracle - fixed:>+10.4f}")

    print()
    print("distribution of the FIRST optimal split (what argmax returns):")
    c1 = collections.Counter(opt_first)
    print("  " + ", ".join(f"a={a}:{c}" for a, c in sorted(c1.items())[:10]) + " ...")
    print("distribution of a UNIFORM draw from each question's optimal set:")
    c2 = collections.Counter(sample_tied())
    print("  " + ", ".join(f"a={a}:{c}" for a, c in sorted(c2.items())[:10]) + " ...")
    print()
    print("Reading: if the fixed split is already optimal for a large share of "
          "questions,\nthe oracle's advantage on the rest is what an adaptive "
          "policy could win, and\nthat is bounded by 'oracle - closest-to-fixed' "
          f"= {oracle - closest_val:+.4f}.")


if __name__ == "__main__":
    main()
