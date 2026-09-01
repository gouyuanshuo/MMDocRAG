"""Phase 3: query-conditioned routing under a retrieval budget.

The proposal promises per-query routing, and E27 delivered a better *static*
configuration instead. This is the routing experiment, and it asks the question
in the form the cost analysis makes answerable:

    static RRF pays two retrievers on both branches of every query. Can a
    router reach that quality while paying for fewer passes?

not the form E17 already answered no to ("can a router beat fusion on
quality?"). Quality at lower cost is a different and weaker claim, and
`router.tie_audit` establishes before any model is fitted that it is not
arithmetically impossible: a perfect chooser restricted to half the CPU budget
beats static RRF by about +0.05 recall, and the best fixed action at that
budget loses to it by about -0.02. The learned router has to recover that -0.02,
which is roughly 30% of the oracle's headroom.

Two policies
------------
A  PRE-RETRIEVAL CHOICE. Pick one of the four single-retriever actions before
   running anything. Cost is exactly 2 passes for every query. Features must be
   free ones: pool shape, question surface statistics, question embedding.

B  CASCADE. Run the cheap action, then decide from its own output whether to
   escalate to full RRF on both branches. Cost is 2 passes for the queries kept
   and 4 for the queries escalated, so a corpus escalation rate of B costs
   2 + 2B passes per query on average. This is the hierarchical policy the
   proposal names: a first level that always runs, a second level bought only
   where it is predicted to pay.

Protocol
--------
Every prediction is out-of-fold. Documents, not questions, define the folds --
questions inside a document share evidence and difficulty, so a question-level
fold leaks the document. Inside each outer training fold a second
document-grouped loop selects the model family, so the family is never chosen by
looking at the fold it is scored on. The folds come from
`retrieval.nested_cv.document_folds` -- E27's own function, imported rather
than reimplemented, because two copies that are supposed to agree eventually
will not, and nothing downstream would notice.

Controls, all at MATCHED budget
-------------------------------
    random     escalate a random subset of the same size. This is the control
               that matters: a policy that escalates 40% of queries is not
               interesting because it scored better than escalating none, it is
               interesting only if it beat escalating a random 40%.
    oracle     escalate the subset with the largest true gain. Its distance
               from the router is the oracle regret.
    static     never escalate (cost 2) and always escalate (cost 4, = E27's
               system D). The second is the number the whole exercise is
               trying to reach more cheaply.

Intervals are document-cluster bootstrap. The policy is held fixed at its
full-sample out-of-fold decision while the evaluation set is resampled, so the
interval answers "do these two policies differ on this population", not "would
the selection change".

Exploratory. This split has been observed since E9 and used to choose methods.

Run:
    python -m router.budget_router --pool selfbuilt --k 10 --features all
    python -m router.budget_router --pool canonical --k 20 --policy A
"""

import argparse
import collections
import json
import os
import sqlite3
import sys

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sklearn.dummy import DummyRegressor                     # noqa: E402
from sklearn.ensemble import HistGradientBoostingRegressor   # noqa: E402
from sklearn.linear_model import Ridge                       # noqa: E402
from sklearn.pipeline import make_pipeline                   # noqa: E402
from sklearn.preprocessing import StandardScaler             # noqa: E402

from retrieval.dense import MODEL as DENSE_MODEL             # noqa: E402
from retrieval.eval_stack_v2 import DEFAULT_DB, SEED, recall  # noqa: E402
from retrieval.nested_cv import document_folds               # noqa: E402
from router import actions as A                              # noqa: E402
from router import features_p3 as F                          # noqa: E402
from router.tie_audit import QUOTA_FAMILY, cluster_ci        # noqa: E402
from expkit.results import ExperimentResult, add_output_args  # noqa: E402

BOOT = 4000
N_RANDOM = 400
BUDGETS = np.round(np.arange(0.0, 1.0001, 0.05), 3)
CHEAP_ACTIONS = [("bm25", "bm25"), ("bm25", "dense"),
                 ("dense", "bm25"), ("dense", "dense")]
DEFAULT_EXPENSIVE = ("rrf", "rrf")


def models():
    """Candidate families. The dummy is the floor: constant predictions rank
    arbitrarily, so a policy driven by it IS the random control."""
    return collections.OrderedDict([
        ("dummy", DummyRegressor(strategy="mean")),
        ("ridge_1", make_pipeline(StandardScaler(), Ridge(alpha=1.0))),
        ("ridge_10", make_pipeline(StandardScaler(), Ridge(alpha=10.0))),
        ("ridge_100", make_pipeline(StandardScaler(), Ridge(alpha=100.0))),
        ("hgb", HistGradientBoostingRegressor(
            max_iter=200, max_depth=3, learning_rate=0.05,
            min_samples_leaf=40, random_state=SEED)),
    ])


def curve(pred, gain, base, budgets=BUDGETS):
    """Recall achieved when the top `B` fraction by `pred` is escalated."""
    n = len(pred)
    order = np.argsort(-pred, kind="stable")
    csum = np.concatenate([[0.0], np.cumsum(gain[order])])
    return np.asarray([base + csum[int(round(b * n))] / n for b in budgets])


def curve_auc(pred, gain, base):
    return float(curve(pred, gain, base).mean())


# Budgets whose per-question escalation decision is written to per_question.csv.
# 0.05 and 0.15 are where the GPU cascade matches the static system's recall;
# 0.50 is the budget the primary Holm family is declared at.
ESCALATION_DUMP_BUDGETS = (0.05, 0.15, 0.50)


def escalation_mask(pred, b, n):
    m = np.zeros(n, dtype=bool)
    m[np.argsort(-pred, kind="stable")[:int(round(b * n))]] = True
    return m


def random_rate(b, n):
    """The rate a budget actually realises once the count is an integer."""
    return int(round(b * n)) / n


def random_expectation(base_v, gain, b):
    """Per-question expected recall of escalating a uniformly random subset.

    Computed, not simulated. If exactly m of n questions are escalated and the
    subset is uniform, question i is escalated with probability m/n, so its
    expected recall is base_i + (m/n) * gain_i exactly. Estimating that by
    averaging a few hundred random subsets adds Monte Carlo noise to the one
    control the whole claim rests on, and at these effect sizes that noise was
    large enough to move Holm-adjusted p-values across 0.05.
    """
    return base_v + random_rate(b, len(base_v)) * gain


def oof_predict(X, y, fold, inner_folds, docs, objective, verbose=False):
    """Out-of-fold predictions with the model family selected inside the fold.

    `X` may be a single matrix or an ordered mapping of name -> matrix, in
    which case the feature group is selected inside the fold as well. That
    matters here: E23 showed the 384-d embedding can bury a real low-
    dimensional signal, so which group to use is a real choice, and a choice
    made by looking at the results is a selection leak like any other.

    `objective(pred, idx) -> float, higher better` scores a candidate on an
    inner validation block, so selection optimises the quantity the policy is
    actually judged on rather than a proxy loss.
    """
    banks = X if isinstance(X, dict) else {"features": X}
    n = len(y)
    oof = np.zeros(n)
    chosen = []
    for f in sorted(set(fold.tolist())):
        te = np.flatnonzero(fold == f)
        tr = np.flatnonzero(fold != f)
        inner, _ = document_folds([docs[i] for i in tr], inner_folds)
        best, best_score = None, -np.inf
        for gname, Xg in banks.items():
            for name in models():
                pred_in = np.zeros(len(tr))
                for g in sorted(set(inner.tolist())):
                    ite = np.flatnonzero(inner == g)
                    itr = np.flatnonzero(inner != g)
                    m = models()[name]
                    m.fit(Xg[tr][itr], y[tr][itr])
                    pred_in[ite] = m.predict(Xg[tr][ite])
                s = objective(pred_in, tr)
                if s > best_score:
                    best, best_score = (gname, name), s
        gname, name = best
        m = models()[name]
        m.fit(banks[gname][tr], y[tr])
        oof[te] = m.predict(banks[gname][te])
        chosen.append(f"{gname}/{name}" if len(banks) > 1 else name)
        if verbose:
            print(f"    fold {f}: selected {chosen[-1]} (inner objective "
                  f"{best_score:.4f})")
    return oof, chosen


def load_questions(db_path):
    con = sqlite3.connect(db_path)
    rows = con.execute("SELECT question_uid, question FROM questions "
                       "WHERE split = 'evaluation'").fetchall()
    con.close()
    return {str(u): q for u, q in rows}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pool", default="selfbuilt",
                    choices=("selfbuilt", "canonical"))
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--dense-model", default=DENSE_MODEL)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--quota", default="balanced", choices=tuple(QUOTA_FAMILY))
    ap.add_argument("--policy", default="B", choices=("A", "B"))
    ap.add_argument("--features", default="all", choices=tuple(F.PRESETS))
    ap.add_argument("--cheap", default="bm25,bm25",
                    help="first-pass action for policy B, as text,visual")
    ap.add_argument("--expensive", default="rrf,rrf",
                    help="escalation target for policy B, as text,visual. "
                         "Use rrf,colqwen to price the GPU decision instead "
                         "of the second CPU pass.")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--inner-folds", type=int, default=4)
    ap.add_argument("--verbose", action="store_true")
    add_output_args(ap)
    args = ap.parse_args()
    k = args.k
    quota = QUOTA_FAMILY[args.quota][k]
    groups = F.PRESETS[args.features]
    cheap = tuple(args.cheap.split(","))
    expensive = tuple(args.expensive.split(","))
    if cheap not in CHEAP_ACTIONS:
        raise SystemExit(f"--cheap must be one of {CHEAP_ACTIONS}")
    if expensive not in A.ACTIONS:
        raise SystemExit(f"--expensive must be one of {A.ACTIONS}")
    c_cheap, c_exp = A.cost(cheap), A.cost(expensive)
    # Incremental, not the difference of two from-scratch costs: a query that
    # escalates has already paid for the first pass, and whatever of that pass
    # the escalation discards is sunk rather than refunded.
    inc = A.incremental_cost(cheap, expensive)
    d_cpu, d_gpu = inc["cpu_passes"], inc["gpu_passes"]
    if d_cpu <= 0 and d_gpu <= 0:
        raise SystemExit("the escalation target must cost more than the first "
                         "pass in at least one currency, or there is no "
                         "budget question to ask")
    if args.policy == "A" and "firstpass" in groups:
        raise SystemExit(
            "policy A decides before any retriever runs, so it cannot use "
            "firstpass features. Use --features free / cheap / shape / emb.")

    rows, meta = A.load(args.pool, k, args.dense_model)
    questions = load_questions(args.db)
    docs = [r["doc"] for r in rows]
    n = len(rows)
    fold, load = document_folds(docs, args.folds)
    rng = np.random.default_rng(SEED)

    X, names = F.featurize(rows, questions, k, quota, groups,
                           args.dense_model, cheap)
    rec = {a: np.asarray([recall(r, a[0], a[1], quota) for r in rows])
           for a in set(CHEAP_ACTIONS + [DEFAULT_EXPENSIVE, expensive])}

    print("=" * 100)
    print(f"PHASE 3 ROUTER   policy={args.policy}  pool={args.pool}  k={k}  "
          f"quota={args.quota} {quota[0]}/{quota[1]}  features={args.features}")
    print("=" * 100)
    print(f"questions {n} over {len(set(docs))} documents; "
          f"gold {sum(r['n_total'] for r in rows)}, unmapped counted as miss "
          f"{sum(r['n_unmapped'] for r in rows)}")
    print(f"features {X.shape[1]} in groups {', '.join(groups)}")
    print(f"outer folds {args.folds} (question loads {load}), inner "
          f"{args.inner_folds}, all predictions out-of-fold")
    print("EXPLORATORY: this split has been observed since E9 and used to "
          "choose methods.")

    res_rows = []

    def report(name, a, b, key, indent=""):
        d, lo, hi, nd = cluster_ci(np.asarray(a) - np.asarray(b), docs, rng,
                                   BOOT)
        star = "*" if (lo > 0 or hi < 0) else " "
        print(f"{indent}{name:<54}{d:>+9.4f}   [{lo:>+7.4f},{hi:>+7.4f}]{star}")
        res_rows.append((key, d, lo, hi, nd))
        return d, lo, hi

    if args.policy == "B":
        base_v = rec[cheap]
        exp_v = rec[expensive]
        gain = exp_v - base_v
        base = float(base_v.mean())
        print()
        print(f"cascade: {A.action_label(cheap)} "
              f"({c_cheap['cpu_passes']} cpu + {c_cheap['gpu_passes']} gpu) "
              f"-> {A.action_label(expensive)} "
              f"({c_exp['cpu_passes']} cpu + {c_exp['gpu_passes']} gpu)")
        print(f"  escalating one query adds +{d_cpu} cpu and +{d_gpu} gpu "
              f"on top of the first pass, so at rate B the corpus pays "
              f"{c_cheap['cpu_passes']} + {d_cpu}B cpu and "
              f"{c_cheap['gpu_passes']} + {d_gpu}B gpu per query")
        if (c_cheap["cpu_passes"] + d_cpu > c_exp["cpu_passes"]
                or c_cheap["gpu_passes"] + d_gpu > c_exp["gpu_passes"]):
            print(f"  NB at B=1 the cascade costs "
                  f"{c_cheap['cpu_passes'] + d_cpu} cpu + "
                  f"{c_cheap['gpu_passes'] + d_gpu} gpu, MORE than running "
                  f"{A.action_label(expensive)} outright "
                  f"({c_exp['cpu_passes']} cpu + {c_exp['gpu_passes']} gpu): "
                  f"the first pass is sunk. The static system, not the B=1 "
                  f"cascade, is the cost reference.")
        print(f"  first pass alone   {base:.4f}")
        static_name = {("rrf", "rrf"): "E27 system D",
                       ("rrf", "colqwen"): "E27 system G",
                       ("dense", "colqwen"): "E27 system E, balanced quota"}
        tag = static_name.get(expensive)
        print(f"  always escalate    {exp_v.mean():.4f}"
              + (f"  (= {tag})" if tag else ""))
        print(f"  escalation helps on {(gain > 0).mean():.1%} of questions, "
              f"hurts on {(gain < 0).mean():.1%}, changes nothing on "
              f"{(gain == 0).mean():.1%}")

        obj = lambda p, idx: curve_auc(p, gain[idx], base_v[idx].mean())
        pred, chosen = oof_predict(X, gain, fold, args.inner_folds, docs, obj,
                                   args.verbose)
        print(f"  model family selected per outer fold: "
              f"{', '.join(chosen)}")

        router_c = curve(pred, gain, base)
        oracle_c = curve(gain, gain, base)
        random_c = np.asarray([random_expectation(base_v, gain, b).mean()
                               for b in BUDGETS])

        print()
        print("-" * 100)
        print(f"QUALITY-COST PARETO  --  escalation rate B costs "
              f"{c_cheap['cpu_passes']} + {d_cpu}B cpu and "
              f"{c_cheap['gpu_passes']} + {d_gpu}B gpu passes / query")
        print("-" * 100)
        print(f"{'B':>6}{'cpu/q':>8}{'gpu/q':>7}{'router':>10}"
              f"{'random':>10}{'oracle':>10}{'router-random':>15}"
              f"{'regret':>10}")
        print("-" * 76)
        for i, b in enumerate(BUDGETS):
            if i % 2 and b not in (0.25, 0.75):
                continue
            print(f"{b:>6.2f}"
                  f"{c_cheap['cpu_passes'] + d_cpu * b:>8.2f}"
                  f"{c_cheap['gpu_passes'] + d_gpu * b:>7.2f}"
                  f"{router_c[i]:>10.4f}"
                  f"{random_c[i]:>10.4f}{oracle_c[i]:>10.4f}"
                  f"{router_c[i] - random_c[i]:>+15.4f}"
                  f"{oracle_c[i] - router_c[i]:>+10.4f}")

        target = float(exp_v.mean())
        reach = [b for b, v in zip(BUDGETS, router_c) if v >= target]
        reach_o = [b for b, v in zip(BUDGETS, oracle_c) if v >= target]
        print()
        print(f"always-escalate quality {target:.4f} costs "
              f"{c_exp['cpu_passes']:.2f} cpu + {c_exp['gpu_passes']:.2f} gpu "
              f"passes / query.")

        def reached(who, hits):
            if not hits:
                print(f"  {who} never reaches it at any budget below 1.00.")
                return None
            b = float(hits[0])
            cc = c_cheap["cpu_passes"] + d_cpu * b
            cg = c_cheap["gpu_passes"] + d_gpu * b
            parts = []
            for cur, ref, unit in ((cc, c_exp["cpu_passes"], "cpu"),
                                   (cg, c_exp["gpu_passes"], "gpu")):
                if ref:
                    verb = "saving" if cur <= ref else "COSTING"
                    parts.append(f"{verb} {abs(1 - cur / ref):.0%} of the "
                                 f"{unit}")
                elif cur:
                    parts.append(f"adding {cur:.2f} {unit} the static system "
                                 f"never pays")
            print(f"  {who} reaches it at B = {b:.2f}: {cc:.2f} cpu + "
                  f"{cg:.2f} gpu passes / query, vs {c_exp['cpu_passes']:.2f} "
                  f"cpu + {c_exp['gpu_passes']:.2f} gpu for the static "
                  f"system -- {', '.join(parts)}.")
            return b

        reached("router", reach)
        reached("oracle", reach_o)

        print()
        print("-" * 100)
        print("MATCHED-BUDGET COMPARISONS  --  document-cluster bootstrap")
        print("-" * 100)
        print(f"{'quantity':<54}{'delta':>9}{'95% CI':>24}")
        print("-" * 87)
        for b in (0.25, 0.5, 0.75):
            i = int(np.argmin(np.abs(BUDGETS - b)))
            m = escalation_mask(pred, BUDGETS[i], n)
            got = np.where(m, exp_v, base_v)
            rm = random_expectation(base_v, gain, BUDGETS[i])
            om = escalation_mask(gain, BUDGETS[i], n)
            report(f"B={b:.2f} router - random at same budget", got, rm,
                   f"router_minus_random_B{int(b * 100)}")
            report(f"B={b:.2f} router - always escalate", got, exp_v,
                   f"router_minus_always_escalate_B{int(b * 100)}")
            report(f"B={b:.2f} oracle - router  (oracle regret)",
                   np.where(om, exp_v, base_v), got,
                   f"oracle_regret_B{int(b * 100)}")
        auc_r, auc_rand, auc_o = (float(router_c.mean()),
                                  float(random_c.mean()),
                                  float(oracle_c.mean()))
        print()
        print(f"area under the budget curve: router {auc_r:.4f}, random "
              f"{auc_rand:.4f}, oracle {auc_o:.4f}; router captures "
              f"{(auc_r - auc_rand) / max(auc_o - auc_rand, 1e-9):.1%} of the "
              f"oracle's advantage over random")
        # The escalation decision itself is written out, not just the score it
        # is derived from. A downstream run -- the paired generation experiment
        # that has to check the cost claim on answer quality rather than on
        # recall -- must consume exactly the decision this experiment measured.
        # Re-deriving it from `predicted_gain` downstream would work only as
        # long as both sides break ties the same way, and a silent divergence
        # there would move which questions got the expensive pass without
        # moving any number that would reveal it.
        masks = {b: escalation_mask(pred, b, len(rows))
                 for b in ESCALATION_DUMP_BUDGETS}
        per_q = [{"question_uid": r["quid"], "doc_name": r["doc"],
                  "recall_cheap": float(base_v[i]),
                  "recall_expensive": float(exp_v[i]),
                  "true_gain": float(gain[i]),
                  "predicted_gain": float(pred[i]),
                  **{f"escalate_at_B{int(b * 100):03d}": int(masks[b][i])
                     for b in ESCALATION_DUMP_BUDGETS}}
                 for i, r in enumerate(rows)]
    else:
        acts = CHEAP_ACTIONS
        Y = np.column_stack([rec[a] for a in acts])
        preds = np.zeros_like(Y)
        chosen = []
        for j, a in enumerate(acts):
            # One regressor per action, selected on squared error inside the
            # training folds; the policy is the argmax over their out-of-fold
            # predictions.
            def obj(p, idx, jj=j):
                return -float(np.mean((p - Y[idx, jj]) ** 2))
            preds[:, j], ch = oof_predict(X, Y[:, j], fold, args.inner_folds,
                                          docs, obj, args.verbose)
            chosen.append(f"{A.action_label(a)}: {'/'.join(ch)}")
        pick = preds.argmax(axis=1)
        got = Y[np.arange(n), pick]

        # Fold-wise best fixed action: chosen on the training folds only, so
        # the comparator does not get to see the fold it is scored on either.
        fixed = np.zeros(n)
        fixed_names = []
        for f in sorted(set(fold.tolist())):
            te, tr = np.flatnonzero(fold == f), np.flatnonzero(fold != f)
            j = int(Y[tr].mean(axis=0).argmax())
            fixed[te] = Y[te, j]
            fixed_names.append(A.action_label(acts[j]))
        oracle = Y.max(axis=1)

        print()
        print("policy A picks one of the four single-retriever actions before "
              "running any.")
        for j, a in enumerate(acts):
            print(f"  {A.action_label(a):<44}{Y[:, j].mean():>9.4f}")
        print(f"  model per action: {'; '.join(chosen)}")
        print(f"  fold-wise best fixed action: {'; '.join(fixed_names)}")
        print()
        print(f"{'policy':<54}{'recall':>9}{'cpu/q':>8}")
        print("-" * 71)
        print(f"{'router (out-of-fold argmax)':<54}{got.mean():>9.4f}"
              f"{2.0:>8.2f}")
        print(f"{'fold-wise best fixed action':<54}{fixed.mean():>9.4f}"
              f"{2.0:>8.2f}")
        print(f"{'oracle over the four':<54}{oracle.mean():>9.4f}{2.0:>8.2f}")
        print(f"{'static RRF both branches':<54}"
              f"{rec[DEFAULT_EXPENSIVE].mean():>9.4f}{4.0:>8.2f}")
        print()
        print(f"{'quantity':<54}{'delta':>9}{'95% CI':>24}")
        print("-" * 87)
        report("router - fold-wise best fixed", got, fixed,
               "policyA_router_minus_fixed")
        report("router - static RRF (cpu 4)", got, rec[DEFAULT_EXPENSIVE],
               "policyA_router_minus_static_rrf")
        report("oracle - router  (oracle regret)", oracle, got,
               "policyA_oracle_regret")
        print()
        print(f"router picks: " + ", ".join(
            f"{A.action_label(acts[j])} {c / n:.0%}"
            for j, c in sorted(collections.Counter(pick.tolist()).items())))
        per_q = [{"question_uid": r["quid"], "doc_name": r["doc"],
                  "recall_router": float(got[i]),
                  "recall_fixed": float(fixed[i]),
                  "recall_oracle": float(oracle[i]),
                  "picked_action": A.action_label(acts[pick[i]])}
                 for i, r in enumerate(rows)]

    with ExperimentResult("E36", metrics_out=args.metrics_out) as res:
        res.config(pool=args.pool, k=k, seed=SEED, bootstrap=BOOT,
                   sample_unit="document", quota=f"{quota[0]}/{quota[1]}",
                   quota_family=args.quota, dense_model=args.dense_model,
                   policy=args.policy, features=args.features,
                   n_features=int(X.shape[1]), folds=args.folds,
                   inner_folds=args.inner_folds,
                   cheap_action=A.action_label(cheap),
                   expensive_action=A.action_label(expensive))
        if args.policy == "B":
            res.metric("recall_first_pass_only", base,
                       cpu_passes=c_cheap["cpu_passes"],
                       gpu_passes=c_cheap["gpu_passes"],
                       action=A.action_label(cheap))
            res.metric("recall_always_escalate", float(exp_v.mean()),
                       cpu_passes=c_exp["cpu_passes"],
                       gpu_passes=c_exp["gpu_passes"],
                       action=A.action_label(expensive))
            res.metric("auc_router", auc_r)
            res.metric("auc_random", auc_rand)
            res.metric("auc_oracle", auc_o)
            res.metric("budget_to_match_static_rrf",
                       float(reach[0]) if reach else None,
                       unit="escalation fraction")
            for i, b in enumerate(BUDGETS):
                res.metric(f"recall_router_B{int(b * 100):03d}",
                           float(router_c[i]), budget=float(b),
                           cpu_passes=float(c_cheap["cpu_passes"] + d_cpu * b),
                           gpu_passes=float(c_cheap["gpu_passes"]
                                            + d_gpu * b))
                res.metric(f"recall_random_B{int(b * 100):03d}",
                           float(random_c[i]), budget=float(b),
                           cpu_passes=float(c_cheap["cpu_passes"] + d_cpu * b),
                           gpu_passes=float(c_cheap["gpu_passes"]
                                            + d_gpu * b))
                res.metric(f"recall_oracle_B{int(b * 100):03d}",
                           float(oracle_c[i]), budget=float(b),
                           cpu_passes=float(c_cheap["cpu_passes"] + d_cpu * b),
                           gpu_passes=float(c_cheap["gpu_passes"]
                                            + d_gpu * b))
        else:
            res.metric("recall_router", float(got.mean()), cpu_passes=2)
            res.metric("recall_fold_wise_best_fixed", float(fixed.mean()),
                       cpu_passes=2)
            res.metric("recall_oracle_four_actions", float(oracle.mean()),
                       cpu_passes=2)
            res.metric("recall_static_rrf",
                       float(rec[DEFAULT_EXPENSIVE].mean()), cpu_passes=4)
        for key, d, lo, hi, nd in res_rows:
            res.metric(key, d, ci=[lo, hi], n=n, n_documents=nd)
        res.per_question(per_q)
        res.note("All predictions out-of-fold with document-grouped folds and "
                 "in-fold model selection. The control that carries the claim "
                 "is random allocation at the same budget, not the "
                 "never-escalate endpoint.")


if __name__ == "__main__":
    main()
