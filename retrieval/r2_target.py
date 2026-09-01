"""How accurate would the modality-mix predictor have to be to be worth having?

The question this answers
-------------------------
The proposal sets an R^2 target for RQ1b and names three untried feature
sources for reaching it: visual retriever scores, model internal
representations, and an LLM evidence-sufficiency judgement. E23 got test R^2
from -0.155 (384-d question embedding) to +0.136 (22-d scores plus first-pass
observations) and stopped there, noting that the allocation gain stayed at
0-2%. That leaves the obvious follow-up unanswered: is +0.136 simply too low,
so that a better feature source would pay off -- or is the mapping from R^2 to
retrieval gain itself so flat that no achievable R^2 matters?

Chasing a higher R^2 is only worth doing if the answer is the first one. This
script settles it by measuring the curve directly instead of arguing about it.

Method
------
E21 established that allocating by the TRUE modality mix cashes 41-49% of the
oracle headroom, so the ceiling is real and the question is purely about
prediction error. For a grid of target R^2, this builds a synthetic predictor

    p = v + eps,    eps ~ N(0, sigma^2),    sigma^2 = (1 - R^2) * Var(v)

and measures what allocating from p buys. Two properties make the resulting
curve an UPPER BOUND rather than a forecast, and both matter for reading it:

  * The synthetic predictor is UNBIASED and its error is independent of v. A
    fitted ridge shrinks toward the training mean, so its errors correlate with
    v and it does strictly worse at the same R^2.
  * The shrinkage coefficient is chosen on the TEST set, which no deployable
    system could do. It is chosen there on purpose: the point is a ceiling.

So if the curve says an achievable R^2 buys nothing, no feature source can
rescue it, and that is a conclusion about the target rather than about the
features. If it says the target is reachable and would pay, then the three
untried sources are worth the money.

Clipping predictions into [0, 1] perturbs the realised R^2 away from its
nominal target, so every row reports the REALISED R^2 of the predictor it
actually used, never the one that was asked for.

Run:
    python -m retrieval.r2_target --pool canonical
"""

import argparse
import collections
import json
import os
import pickle
import sqlite3
import sys

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from expkit.results import ExperimentResult, add_output_args        # noqa: E402
from retrieval.reflect_alloc import (recall_two_stage, DEFAULT_DB,  # noqa: E402
                                     DEFAULT_SPLIT, K_TOTAL, REPO_ROOT)

BOOT = 4000
SEED = 20260831
DRAWS = 200
LAMBDAS = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.75, 0.9, 1.0)
# E23's best measured test R^2, from 22 dimensions of scores plus first-pass
# observations. Marked on the curve so the reader can see where the project
# actually stands rather than where it hopes to stand.
MEASURED_R2 = 0.136


def cluster_ci(d, docs, rng, n_boot=BOOT):
    """Document-cluster bootstrap. Questions nest inside documents."""
    by = collections.defaultdict(list)
    for i, x in enumerate(docs):
        by[x].append(i)
    keys = sorted(by)
    sd = np.array([d[by[x]].sum() for x in keys])
    sn = np.array([len(by[x]) for x in keys], dtype=float)
    p = rng.integers(0, len(keys), size=(n_boot, len(keys)))
    m = sd[p].sum(axis=1) / sn[p].sum(axis=1)
    lo, hi = np.percentile(m, [2.5, 97.5])
    return float(d.mean()), float(lo), float(hi), len(keys)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pool", default="canonical",
                    choices=("canonical", "selfbuilt"))
    ap.add_argument("--k-total", type=int, default=K_TOTAL)
    ap.add_argument("--k-first", type=int, default=6)
    ap.add_argument("--split", default=DEFAULT_SPLIT)
    ap.add_argument("--draws", type=int, default=DRAWS)
    add_output_args(ap)
    args = ap.parse_args()
    k, kf = args.k_total, args.k_first
    rest = k - kf

    rows = pickle.load(open(os.path.join(
        REPO_ROOT, "retrieval", f"budget_rows_{args.pool}.pkl"), "rb"))
    con = sqlite3.connect(DEFAULT_DB)
    doc_of = dict(con.execute(
        "SELECT question_uid, doc_name FROM questions "
        "WHERE split = 'evaluation'"))
    con.close()

    R = np.asarray([[recall_two_stage(r, kf, a, k) for a in range(rest + 1)]
                    for r in rows])
    vis = np.asarray([r["visual_share"] for r in rows])
    docs_all = np.asarray([doc_of.get(r["quid"], "?") for r in rows])

    assign = json.load(open(args.split, encoding="utf-8"))["q_id_to_split"]
    sp = np.asarray([assign[str(r["q_id"])] for r in rows])
    tr, te = sp == "train", sp == "test"
    ar = np.arange(int(te.sum()))
    docs_te = docs_all[te]

    best_a = int(np.argmax(R[tr].mean(axis=0)))
    fixed_v = R[te][:, best_a]
    orc_v = R[te][ar, R[te].argmax(axis=1)]
    fixed, orc = fixed_v.mean(), orc_v.mean()
    head = orc - fixed

    v_te = vis[te]
    var_te = v_te.var()
    rng = np.random.default_rng(SEED)

    print("=" * 92)
    print(f"WHAT R^2 WOULD BE WORTH REACHING   pool={args.pool}  k={k}  "
          f"first pass={kf}  remaining={rest}")
    print("=" * 92)
    print(f"test questions {int(te.sum())}, documents {len(set(docs_te))}, "
          f"Var(visual_share) on test {var_te:.4f}")
    print(f"best fixed split (a_rest={best_a}, chosen on train)   "
          f"recall {fixed:.4f}")
    print(f"per-question oracle split                            "
          f"recall {orc:.4f}")
    print(f"headroom the allocation decision can address         "
          f"{head:+.4f}")
    print()
    print("Every row spends the same retrieval cost: the first pass is paid")
    print("before any decision and the remaining slots are merely divided.")
    print()

    def allocate(p, lam):
        """Shrink the proportional split toward the fixed one and score it."""
        a = np.rint((1 - lam) * rest * (1 - p) + lam * best_a)
        return R[te][ar, np.clip(a, 0, rest).astype(int)]

    # ---- the true-mix reference, which is E21's finding re-derived --------
    true_best = max(LAMBDAS, key=lambda l: allocate(v_te, l).mean())
    true_v = allocate(v_te, true_best)
    d_true, lo_t, hi_t, nd = cluster_ci(true_v - fixed_v, docs_te, rng)
    print(f"allocating from the TRUE mix (lambda={true_best}) buys "
          f"{d_true:+.4f} [{lo_t:+.4f},{hi_t:+.4f}] "
          f"= {d_true / head:.0%} of headroom, over {nd} documents")
    print()

    # ---- the curve -------------------------------------------------------
    print("SYNTHETIC PREDICTORS AT A TARGET R^2  (ceiling, see module docstring)")
    print("-" * 92)
    print(f"{'target':>7}{'realised':>10}{'lambda':>8}{'recall':>9}"
          f"{'vs fixed':>10}  {'95% CI':>21}{'of headroom':>13}")
    print("-" * 92)
    def realised_r2(sigma, seed_tag):
        """Mean R^2 actually achieved after predictions are clipped to [0,1]."""
        drng = np.random.default_rng([SEED, seed_tag, 11])
        den = ((v_te - v_te.mean()) ** 2).sum()
        acc = []
        for _ in range(24):
            p = np.clip(v_te + drng.normal(0.0, sigma, size=v_te.shape), 0.0, 1.0)
            acc.append(1 - ((v_te - p) ** 2).sum() / den)
        return float(np.mean(acc))

    def sigma_for(target):
        """Bisect sigma so the CLIPPED predictor realises `target`.

        The closed form sigma^2 = (1 - R^2) Var(v) is wrong here: visual_share
        piles up at 0 and 1, so clipping removes a large share of the injected
        error and the realised R^2 comes out far above the nominal one. At
        target 0 the closed form lands near 0.29, which would silently place
        E23's measured 0.136 two thirds of the way up the curve. Solving for
        the realised value keeps the x-axis meaning what it says.
        """
        if target >= 0.999:
            return 0.0
        lo, hi = 0.0, 4.0 * float(np.sqrt(var_te)) + 1.0
        tag = int(target * 1000)
        # realised_r2 decreases monotonically in sigma
        if realised_r2(hi, tag) > target:
            return hi                      # target unreachable; report the floor
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            if realised_r2(mid, tag) > target:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    # Reported to four decimals, so a bound below this is indistinguishable
    # from zero on the page and must not be starred or counted as clearing it.
    EDGE = 5e-5
    grid = [0.0, 0.136, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0]
    Z = np.random.default_rng([SEED, 7]).normal(
        0.0, 1.0, size=(args.draws, v_te.shape[0]))
    out = []
    for target in grid:
        sigma = sigma_for(target)
        # Averaging the RECALL over draws, not averaging the predictors: the
        # quantity of interest is what a predictor of this quality delivers on
        # a typical draw, and averaging predictors first would cancel the noise
        # that is the entire point.
        # Common random numbers: one bank of standard normals is drawn once and
        # merely rescaled by sigma at every target. Independent draws per target
        # put about +-0.001 of Monte-Carlo noise on each point, enough to make
        # the curve non-monotone and invite reading an ordering that is not
        # there. With the noise shared, differences along the curve are paired.
        P = np.clip(v_te[None, :] + sigma * Z, 0.0, 1.0)
        r2s = list(1 - ((v_te[None, :] - P) ** 2).sum(axis=1)
                   / ((v_te - v_te.mean()) ** 2).sum())
        best_lam, best_mean, best_vec = None, -1.0, None
        for lam in LAMBDAS:
            vec = np.mean([allocate(P[j], lam) for j in range(P.shape[0])],
                          axis=0)
            if vec.mean() > best_mean:
                best_lam, best_mean, best_vec = lam, vec.mean(), vec
        d, lo, hi, _ = cluster_ci(best_vec - fixed_v, docs_te, rng)
        realised = float(np.mean(r2s))
        star = "*" if (lo > EDGE or hi < -EDGE) else " "
        mark = "   <- E23's measured R^2" if abs(target - MEASURED_R2) < 1e-9 else ""
        print(f"{target:>7.3f}{realised:>10.3f}{best_lam:>8.2f}"
              f"{best_mean:>9.4f}{d:>+10.4f}  [{lo:>+8.4f},{hi:>+8.4f}]{star}"
              f"{d / head if head > 1e-9 else float('nan'):>12.0%}{mark}")
        out.append({"target_r2": target, "realised_r2": realised,
                    "lambda": best_lam, "recall": float(best_mean),
                    "delta": d, "lo": lo, "hi": hi,
                    "share_of_headroom": float(d / head) if head > 1e-9 else None})
    print("-" * 92)

    # ---- read it out -----------------------------------------------------
    # A bound of +0.00004 prints as +0.0000 and is not an interval clear of
    # zero in any sense a reader would accept. The threshold is the resolution
    # at which these numbers are reported, not machine epsilon: claiming
    # significance from a bound smaller than the printed precision is exactly
    # the failure this project has a standing rule against.
    reach = [o for o in out if o["lo"] > EDGE]
    half = [o for o in out if o["share_of_headroom"] is not None
            and o["share_of_headroom"] >= 0.5 * (d_true / head)]
    print()
    print("READING THIS")
    print("  lambda is chosen on the TEST set and the predictor's error is")
    print("  unbiased and independent of the truth, so each row is a CEILING.")
    print("  A deployable ridge at the same R^2 does strictly worse.")
    print()
    if reach:
        first = min(reach, key=lambda o: o["target_r2"])
        print(f"  Lowest R^2 whose interval clears zero even as a ceiling: "
              f"{first['target_r2']:.2f}")
    else:
        print("  No R^2 on this grid produces an interval clear of zero, not")
        print("  even at perfect prediction. The allocation decision itself is")
        print("  what does not pay, and the R^2 target is the wrong target.")
    if half:
        h = min(half, key=lambda o: o["target_r2"])
        print(f"  Lowest R^2 delivering half of what the true mix delivers: "
              f"{h['target_r2']:.2f}")
    print(f"  E23 measured {MEASURED_R2:.3f}. The distance between that and the")
    print("  figures above is what the proposal's three untried feature sources")
    print("  would have to close, and it is the honest way to decide whether")
    print("  paying for them is justified.")
    print()
    print("EXPLORATORY. This split has been observed since E9 and was used to")
    print("choose methods.")

    with ExperimentResult("E38", args.metrics_out,
                          title="RQ1b 的 R² 目标要多高才值得追") as res:
        res.config(pool=args.pool, k_total=k, k_first=kf,
                   draws=args.draws, sample_unit="document", bootstrap=BOOT,
                   predictor="synthetic, unbiased, homoscedastic noise",
                   lambda_selection="chosen on test -- deliberately optimistic",
                   status="exploratory ceiling, not a forecast",
                   measured_r2_from_E23=MEASURED_R2)
        res.metric("recall_best_fixed_split", float(fixed), unit="recall")
        res.metric("recall_oracle_split", float(orc), unit="recall")
        res.metric("headroom", float(head), unit="recall",
                   desc="oracle split minus best fixed split; everything the "
                        "allocation decision could ever address")
        res.metric("delta_from_true_mix", d_true, unit="recall",
                   ci=[lo_t, hi_t], n_documents=nd,
                   desc="E21's finding re-derived: what allocating from the "
                        "true modality mix buys")
        for o in out:
            res.metric(f"delta_at_r2_{o['target_r2']:.3f}".replace(".", "_"),
                       o["delta"], unit="recall", ci=[o["lo"], o["hi"]],
                       realised_r2=o["realised_r2"], shrinkage=o["lambda"],
                       desc="ceiling: unbiased predictor at this R^2, shrinkage "
                            "chosen on test")


if __name__ == "__main__":
    main()
