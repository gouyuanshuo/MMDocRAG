"""Phase 3, step 0: is there anything for a retriever router to route?

This runs before any router is trained, because E8 and E19 both established the
same discipline the hard way: a per-question oracle gain is not by itself
evidence that a routable structure exists, and an oracle computed with
`argmax` is not even the oracle it claims to be.

Two distinct inflations are separated here.

    TIES. Recall at k is a ratio of small integers -- the median question has
    two or three gold items -- so many actions land on exactly the same recall
    for a given question. `C.argmax(axis=1)` returns the first of them, which
    is an arbitrary action, not "the action this query needs". Everything
    downstream inherits that arbitrariness. The tie-aware oracle here samples
    uniformly from each question's own optimal set instead.

    MARGINALS. An oracle assigns a *mix* of actions across the corpus. Some of
    its advantage over a single fixed action comes from that mix alone and
    needs no query-specific knowledge whatsoever. The control that removes it
    is a permutation: keep the oracle's multiset of chosen actions, shuffle
    which question gets which. It matches the oracle's action marginals and
    therefore its cost exactly, and it destroys only the pairing between a
    query and its action. Whatever survives that permutation is the part a
    router could conceivably learn.

E19's control permuted the argmax choices, so it inherited the tie artefact and
compared against an unrealistically extreme control. Both versions are printed
so the size of that correction is visible rather than asserted.

Which floor binds
-----------------
A router has to beat the STRONGER of the best fixed action and the permuted
control, and which one that is has to be read off the data rather than assumed.
E19 found the permuted control above the fixed policy. If instead the fixed
action wins, the oracle's advantage is not coming from its action mix, and the
routable part is whatever the oracle holds over the fixed action.

The cost question this project actually asks
--------------------------------------------
The proposal's claim is about budget, not about beating fusion on quality:
static RRF pays two retrievers on every branch of every query. So the audit is
run once per budget, restricting the action space to what that budget can buy,
and it reports the cheapest action that is still optimal for each query.

A budget is a PAIR of ceilings, not a scalar. CPU retrieval passes and ColQwen
GPU late-interaction passes are different currencies, and this project has
never measured an exchange rate between them, so they are never summed and the
cheapest-optimal action is reported under both lexicographic orders.

Exploratory. This split has been observed since E9 and used to choose methods,
so nothing here supports a generalisation claim on its own.

Run:
    python -m router.tie_audit --pool selfbuilt --k 10
    python -m router.tie_audit --pool canonical --k 20 --include-quota
"""

import argparse
import collections
import os
import sys

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retrieval.dense import MODEL as DENSE_MODEL          # noqa: E402
from retrieval.eval_stack_v2 import (BALANCED_QUOTA, PAPER_QUOTA,  # noqa: E402
                                     SEED, recall)
from router import actions as A                           # noqa: E402
from expkit.results import ExperimentResult, add_output_args   # noqa: E402

BOOT = 4000
N_PERM = 200
# The quota document-grouped nested CV selected in E27. Named, not implied: it
# is neither the balanced quota nor the paper's.
SELECTED_QUOTA = {10: (4, 6), 15: (7, 8), 20: (9, 11)}
QUOTA_FAMILY = {"paper": PAPER_QUOTA, "balanced": BALANCED_QUOTA,
                "selected": SELECTED_QUOTA}


def cluster_ci(d, docs, rng, n_boot=BOOT):
    """Paired bootstrap over DOCUMENTS: 2,000 questions come from 220 docs."""
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


def build_space(rows, k, quota, include_quota):
    """(recall matrix, actions, quotas, cpu cost, gpu cost, labels)."""
    if include_quota:
        acts, quotas = [], []
        for a in A.ACTIONS:
            for t in range(k + 1):
                acts.append(a)
                quotas.append((t, k - t))
        C = np.asarray([[recall(r, a[0], a[1], q)
                         for a, q in zip(acts, quotas)] for r in rows])
        labels = [f"{A.action_label(a)} @ {q[0]}/{q[1]}"
                  for a, q in zip(acts, quotas)]
    else:
        acts = list(A.ACTIONS)
        quotas = [quota] * len(acts)
        C = A.recall_matrix(rows, quota, acts)
        labels = [A.action_label(a) for a in acts]
    cpu = np.array([A.cost(a)["cpu_passes"] for a in acts], dtype=float)
    gpu = np.array([A.cost(a)["gpu_passes"] for a in acts], dtype=float)
    return C, acts, quotas, cpu, gpu, labels


def sample_tied(tied, rng):
    """One uniform draw from each question's own optimal set."""
    out = np.empty(tied.shape[0], dtype=int)
    for i in range(tied.shape[0]):
        idx = np.flatnonzero(tied[i])
        out[i] = idx[rng.integers(0, len(idx))]
    return out


def permuted_mean(C, choice, rng, n_perm=N_PERM):
    """Same multiset of actions, shuffled across questions."""
    n = len(choice)
    vals = [C[np.arange(n), choice[rng.permutation(n)]].mean()
            for _ in range(n_perm)]
    return float(np.mean(vals)), float(np.std(vals))


def subspaces(cpu, gpu):
    """Named cost budgets, each a pair of ceilings rather than a scalar."""
    return [
        ("cpu<=2, no gpu", (cpu <= 2) & (gpu == 0)),
        ("cpu<=3, no gpu", (cpu <= 3) & (gpu == 0)),
        ("cpu<=4, no gpu", (cpu <= 4) & (gpu == 0)),
        ("gpu=1 (colqwen visual)", gpu == 1),
        ("unrestricted", np.ones_like(cpu, dtype=bool)),
    ]


def cheapest_optimal(C, tied, cpu, gpu, order):
    """Per question, the cheapest action that is still optimal for it.

    `order` names the lexicographic key explicitly. "cpu-first" answers how few
    CPU passes the corpus could get away with; "gpu-first" answers how often the
    GPU must be touched at all. Reporting one alone would silently invent an
    exchange rate between two currencies this project has not priced against
    each other.
    """
    idx = np.arange(C.shape[1]) * 1e-6
    key = (cpu * 1e3 + gpu + idx) if order == "cpu-first" \
        else (gpu * 1e3 + cpu + idx)
    return np.where(tied, key[None, :], np.inf).argmin(axis=1)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pool", default="selfbuilt",
                    choices=("selfbuilt", "canonical"))
    ap.add_argument("--dense-model", default=DENSE_MODEL)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--quota", default="balanced", choices=tuple(QUOTA_FAMILY))
    ap.add_argument("--include-quota", action="store_true",
                    help="expand the action space over every text/image split "
                         "too. The quota is free, so this measures headroom, "
                         "not budget.")
    add_output_args(ap)
    args = ap.parse_args()
    k = args.k
    quota = QUOTA_FAMILY[args.quota][k]

    rows, meta = A.load(args.pool, k, args.dense_model)
    docs = [r["doc"] for r in rows]
    n = len(rows)
    C, acts, quotas, cpu, gpu, labels = build_space(
        rows, k, quota, args.include_quota)
    rng = np.random.default_rng(SEED)

    print("=" * 100)
    print(f"PHASE 3 TIE AUDIT   pool={args.pool}  k={k}  "
          f"quota={args.quota} {quota[0]}/{quota[1]}  actions={C.shape[1]}"
          f"{'  (retriever x quota)' if args.include_quota else ''}")
    print("=" * 100)
    print(f"questions {n} over {len(set(docs))} documents; "
          f"gold {sum(r['n_total'] for r in rows)}, unmapped counted as miss "
          f"{sum(r['n_unmapped'] for r in rows)}")
    print("EXPLORATORY: this split has been observed since E9 and used to "
          "choose methods.")

    tied = (C == C.max(axis=1, keepdims=True))
    n_tied = tied.sum(axis=1)
    fixed_j = int(C.mean(axis=0).argmax())
    all_equal = (C.max(axis=1) == C.min(axis=1))
    dead = all_equal & (C.max(axis=1) == 0)
    saturated = all_equal & (C.max(axis=1) >= 1.0)

    print()
    print("-" * 100)
    print("TIE STRUCTURE  --  how much of the optimum is a plateau")
    print("-" * 100)
    print(f"best single fixed action           : {labels[fixed_j]}")
    print(f"questions with >1 optimal action   : {np.mean(n_tied > 1):.1%}")
    print(f"median / mean tied optima          : {np.median(n_tied):.0f} / "
          f"{n_tied.mean():.1f}  of {C.shape[1]}")
    print(f"every action identical for question: {all_equal.mean():.1%} "
          f"(recall 0 for all: {dead.mean():.1%}; recall 1 for all: "
          f"{saturated.mean():.1%})")
    print(f"best fixed action already optimal  : {tied[:, fixed_j].mean():.1%} "
          "of questions")
    print("  Those questions carry no routable signal by construction: no "
          "choice can beat\n  the action a fixed policy already takes on them.")

    # static RRF on both branches at this quota: E27 system D.
    rrf_j = [j for j, a in enumerate(acts)
             if a == ("rrf", "rrf") and quotas[j] == quota][0]
    rrf_vec = C[:, rrf_j]

    print()
    print("-" * 100)
    print("PER-BUDGET AUDIT  --  each row restricts the action space to what "
          "that budget buys")
    print("-" * 100)
    print(f"{'budget':<24}{'act':>4}{'bestfixed':>11}{'oracle':>9}"
          f"{'tie-perm':>10}{'oracle - fixed':>26}{'fixed - perm':>26}")
    print("-" * 110)
    sub_metrics = collections.OrderedDict()
    for name, mask in subspaces(cpu, gpu):
        cols = np.flatnonzero(mask)
        if len(cols) == 0:
            continue
        sub = C[:, cols]
        sfixed_j = int(sub.mean(axis=0).argmax())
        sfixed = sub[:, sfixed_j]
        soracle = sub.max(axis=1)
        stied = (sub == sub.max(axis=1, keepdims=True))
        sperm, ssd = permuted_mean(sub, sample_tied(stied, rng), rng)
        d1, lo1, hi1, nd = cluster_ci(soracle - sfixed, docs, rng)
        d2, lo2, hi2, _ = cluster_ci(sfixed - np.full(n, sperm), docs, rng)
        s1 = "*" if (lo1 > 0 or hi1 < 0) else " "
        s2 = "*" if (lo2 > 0 or hi2 < 0) else " "
        print(f"{name:<24}{len(cols):>4}{sfixed.mean():>11.4f}"
              f"{soracle.mean():>9.4f}{sperm:>10.4f}"
              f"{d1:>+13.4f} [{lo1:>+7.4f},{hi1:>+7.4f}]{s1}"
              f"{d2:>+12.4f} [{lo2:>+7.4f},{hi2:>+7.4f}]{s2}")
        sub_metrics[name] = {
            "cols": cols, "fixed": sfixed,
            "fixed_label": labels[cols[sfixed_j]],
            "oracle": soracle, "perm": sperm, "perm_sd": ssd,
            "oracle_minus_fixed": (d1, lo1, hi1),
            "fixed_minus_perm": (d2, lo2, hi2), "n_documents": nd}
    print("  best fixed action per budget:")
    for nm, m in sub_metrics.items():
        print(f"    {nm:<24}{m['fixed_label']}")

    print()
    print("-" * 100)
    print("THE TIE CORRECTION, ON THE UNRESTRICTED SPACE")
    print("-" * 100)
    perm_tie, sd_tie = permuted_mean(C, sample_tied(tied, rng), rng)
    perm_first, sd_first = permuted_mean(C, C.argmax(axis=1), rng)
    oracle = C.max(axis=1)
    fixed = C[:, fixed_j]
    print(f"{'permuted control, argmax ties (E19 style)':<52}"
          f"{perm_first:>9.4f}  sd {sd_first:.4f}")
    print(f"{'permuted control, tie-aware sampling':<52}"
          f"{perm_tie:>9.4f}  sd {sd_tie:.4f}")
    print(f"{'the tie artefact is worth':<52}"
          f"{perm_tie - perm_first:>+9.4f} of apparent headroom")
    print()
    res_rows = []

    def report(name, a, b, key):
        d, lo, hi, nd = cluster_ci(a - b, docs, rng)
        star = "*" if (lo > 0 or hi < 0) else " "
        print(f"{name:<52}{d:>+9.4f}   [{lo:>+7.4f},{hi:>+7.4f}]{star}")
        res_rows.append((key, d, lo, hi, nd))
        return d, lo, hi

    print(f"{'quantity':<52}{'delta':>9}{'95% CI':>24}")
    print("-" * 85)
    report("oracle - best fixed", oracle, fixed, "oracle_minus_fixed")
    report("oracle - argmax-permuted  (E19 style)", oracle,
           np.full(n, perm_first), "oracle_minus_permuted_argmax")
    report("oracle - tie-aware permuted", oracle, np.full(n, perm_tie),
           "oracle_minus_permuted_tieaware")
    report("best fixed - tie-aware permuted", fixed, np.full(n, perm_tie),
           "fixed_minus_permuted_tieaware")

    binding = "best fixed action" if fixed.mean() > perm_tie \
        else "tie-aware permuted control"
    print()
    print(f"Binding floor for a router here: the {binding}, at "
          f"{max(fixed.mean(), perm_tie):.4f}.")
    print("A router must beat the STRONGER of the two. The permuted control "
          "shows how much\nof the oracle comes from its action mix alone; the "
          "fixed action shows how much\ncomes from always picking the same "
          "good action.")

    print()
    print("-" * 100)
    print("COST CEILING  --  what perfect routing could save, per currency")
    print("-" * 100)
    print(f"static RRF on both branches: recall {rrf_vec.mean():.4f} at "
          f"{cpu[rrf_j]:.0f} cpu + {gpu[rrf_j]:.0f} gpu passes / query")
    for order in ("cpu-first", "gpu-first"):
        pick = cheapest_optimal(C, tied, cpu, gpu, order)
        print(f"  cheapest optimal action, {order:<10}: recall "
              f"{C[np.arange(n), pick].mean():.4f} at "
              f"{cpu[pick].mean():.2f} cpu + {gpu[pick].mean():.2f} gpu / query")
    cpu_only = np.flatnonzero(gpu == 0)
    Ccpu = C[:, cpu_only]
    tied_cpu = (Ccpu == Ccpu.max(axis=1, keepdims=True))
    pick_c = cheapest_optimal(Ccpu, tied_cpu, cpu[cpu_only], gpu[cpu_only],
                              "cpu-first")
    cpu_only_cheap = float(cpu[cpu_only][pick_c].mean())
    print(f"  cpu-only space, cheapest optimal    : recall "
          f"{Ccpu[np.arange(n), pick_c].mean():.4f} at "
          f"{cpu_only_cheap:.2f} cpu / query "
          f"(static RRF pays {cpu[rrf_j]:.0f})")
    print()
    print(f"{'quantity':<52}{'delta':>9}{'95% CI':>24}")
    print("-" * 85)
    for name in ("cpu<=2, no gpu", "cpu<=3, no gpu", "gpu=1 (colqwen visual)"):
        if name not in sub_metrics:
            continue
        m = sub_metrics[name]
        slug = name.split(",")[0].split(" ")[0].replace("<=", "le")
        report(f"oracle at {name} - static RRF (cpu 4)", m["oracle"], rrf_vec,
               f"oracle_{slug}_minus_static_rrf")
        report(f"best fixed at {name} - static RRF (cpu 4)", m["fixed"],
               rrf_vec, f"fixed_{slug}_minus_static_rrf")

    print()
    print("Reading: the oracle at half the cpu budget is the Phase 3 ceiling. "
          "If a perfect\nrouter restricted to that budget cannot beat static "
          "RRF, no learned router can,\nand the budget claim is dead before "
          "any model is fitted.")

    with ExperimentResult("E35", metrics_out=args.metrics_out) as res:
        res.config(pool=args.pool, k=k, seed=SEED, bootstrap=BOOT,
                   sample_unit="document", quota=f"{quota[0]}/{quota[1]}",
                   quota_family=args.quota, dense_model=args.dense_model,
                   n_actions=int(C.shape[1]), n_permutations=N_PERM,
                   include_quota=bool(args.include_quota))
        res.metric("recall_best_fixed", fixed.mean(), action=labels[fixed_j])
        res.metric("recall_static_rrf", rrf_vec.mean(), action=labels[rrf_j])
        res.metric("recall_oracle", oracle.mean())
        res.metric("recall_permuted_tieaware", perm_tie, sd=sd_tie)
        res.metric("recall_permuted_argmax", perm_first, sd=sd_first)
        res.metric("frac_all_actions_identical", float(all_equal.mean()))
        res.metric("frac_all_actions_recall1", float(saturated.mean()))
        res.metric("frac_fixed_already_optimal", float(tied[:, fixed_j].mean()))
        res.metric("mean_tied_optima", float(n_tied.mean()))
        res.metric("cpu_passes_cheapest_optimal_cpu_only", cpu_only_cheap,
                   unit="cpu passes/query")
        res.metric("cpu_passes_static_rrf", float(cpu[rrf_j]),
                   unit="cpu passes/query")
        for nm, m in sub_metrics.items():
            slug = nm.replace("<=", "le").replace(", ", "_").replace(" ", "_")
            res.metric(f"recall_oracle__{slug}", m["oracle"].mean(),
                       budget=nm, n_actions=int(len(m["cols"])))
            res.metric(f"recall_best_fixed__{slug}", m["fixed"].mean(),
                       budget=nm, action=m["fixed_label"])
            res.metric(f"recall_permuted__{slug}", m["perm"], budget=nm)
            d, lo, hi = m["oracle_minus_fixed"]
            res.metric(f"oracle_minus_fixed__{slug}", d, ci=[lo, hi], n=n,
                       n_documents=m["n_documents"], budget=nm)
        for key, d, lo, hi, nd in res_rows:
            res.metric(key, d, ci=[lo, hi], n=n, n_documents=nd)
        res.per_question([
            {"question_uid": r["quid"], "doc_name": r["doc"],
             "recall_best_fixed": float(fixed[i]),
             "recall_static_rrf": float(rrf_vec[i]),
             "recall_oracle": float(oracle[i]),
             "n_tied_optima": int(n_tied[i]),
             "all_actions_identical": bool(all_equal[i])}
            for i, r in enumerate(rows)])
        res.note("Ties and action marginals are two separate inflations of "
                 "apparent headroom; both controls are reported. Budgets are "
                 "pairs of ceilings because cpu and gpu passes are different "
                 "currencies with no measured exchange rate.")


if __name__ == "__main__":
    main()
