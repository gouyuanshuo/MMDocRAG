"""Document-grouped nested cross-validation for the retrieval configuration.

Why this exists
---------------
Every retrieval number in this project so far was reported on one 396-question
test split that has been looked at repeatedly since E9 and used to choose the
quota, the retriever, the fusion rule and the chunk granularity. That makes it
an exploratory split: it cannot support a generalisation claim no matter how the
interval is computed.

Nested CV fixes the selection leak directly. The outer loop holds out whole
documents; the inner loop sees only the remaining documents and picks the
configuration; the held-out fold is scored with a configuration it never
influenced. Rotating the outer fold means every one of the ~2,000 questions is
eventually scored out-of-fold, which also removes the second problem with the
old protocol -- 396 questions was too few to separate the systems at k=15 and
k=20.

Grouping is by document, not by question, for the same reason the bootstrap is:
questions from one document share evidence, style and difficulty, so a
question-level fold would leak a document's characteristics across the split.

What is selected in the inner loop
----------------------------------
The quota AND the retriever/fusion configuration. Selecting only the quota would
understate the leak, because the choice of "RRF over both modalities" was itself
made by looking at this data. Everything the project tuned is therefore re-tuned
inside each fold.

The comparison is against two fixed references that are never tuned:

    E   closest local paper-style hybrid: dense text + ColQwen visual, official
        quota. Fixed by the paper, so it needs no inner selection.
    A   local BGE-small-only surrogate, official quota.

Run:
    python -m retrieval.nested_cv --pool selfbuilt
    python -m retrieval.nested_cv --pool canonical --k 20 --folds 5
"""

import argparse
import collections
import json
import os
import sys

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retrieval.eval_stack_v2 import (BALANCED_QUOTA, DEFAULT_COLQWEN,  # noqa: E402
                                     DEFAULT_DB, DEFAULT_QUOTES,
                                     PAPER_QUOTA, SEED, build, recall)
from retrieval.dense import MODEL as DENSE_MODEL                     # noqa: E402
from expkit.results import ExperimentResult, add_output_args   # noqa: E402

BOOT = 4000
# The configuration space the inner loop searches. Retriever pairs are named as
# (text retriever, visual retriever); the quota is searched over every split.
CONFIGS = [("dense", "dense"), ("bm25", "bm25"), ("rrf", "rrf"),
           ("dense", "colqwen"), ("rrf", "colqwen")]


def document_folds(docs, n_folds):
    """Balanced document-grouped folds.

    Documents are shuffled deterministically by descending question count, ties
    broken on name, and each is dealt to the currently lightest fold, so folds
    are balanced in QUESTIONS rather than in document count -- a 169-question
    document would otherwise dominate whichever fold it landed in.

    Phase 3 routes on the same folds, and imports this function rather than
    reimplementing it: two copies of a fold assignment that are supposed to
    agree will eventually stop agreeing, and nothing downstream would notice.
    """
    counts = collections.Counter(docs)
    order = sorted(counts, key=lambda d: (-counts[d], d))
    fold_of, load = {}, [0] * n_folds
    for d in order:
        f = int(np.argmin(load))
        fold_of[d] = f
        load[f] += counts[d]
    return np.asarray([fold_of[d] for d in docs]), load


def score(rows, tr, vr, quota):
    return np.asarray([recall(r, tr, vr, quota) for r in rows])


def cluster_ci(d, docs, rng, n_boot=BOOT):
    by = collections.defaultdict(list)
    for i, x in enumerate(docs):
        by[x].append(i)
    ks = sorted(by)
    sd = np.array([d[by[x]].sum() for x in ks])
    sn = np.array([len(by[x]) for x in ks], dtype=float)
    p = rng.integers(0, len(ks), size=(n_boot, len(ks)))
    m = sd[p].sum(axis=1) / sn[p].sum(axis=1)
    lo, hi = np.percentile(m, [2.5, 97.5])
    return d.mean(), lo, hi


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--quotes", default=DEFAULT_QUOTES)
    ap.add_argument("--colqwen", default=DEFAULT_COLQWEN)
    ap.add_argument("--pool", default="selfbuilt", choices=("selfbuilt", "canonical"))
    ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--folds", type=int, default=5)
    # eval_stack_v2 has had --dense-model since E34; this script did not, and
    # called build() positionally, so it silently used the bge-small default no
    # matter what the caller believed it was measuring. That is the worst shape
    # for a headline result: the encoder is a free variable that never appears
    # in the argv the run records. It is a declared argument now, and it lands
    # in the manifest with everything else.
    ap.add_argument("--dense-model", default=DENSE_MODEL,
                    help="sentence-transformers model or local path for the "
                         "dense text arm. Must match a model already encoded by "
                         "retrieval.dense and retrieval.dense_chunks "
                         f"(default: {DENSE_MODEL}).")
    add_output_args(ap)
    args = ap.parse_args()
    k = args.k

    rows, meta = build(args.db, args.quotes, args.colqwen, args.pool,
                       dense_model=args.dense_model)
    docs = np.asarray([r["doc"] for r in rows])
    uniq = sorted(set(docs.tolist()))
    rng = np.random.default_rng(SEED)

    fold, load = document_folds(docs.tolist(), args.folds)

    print("=" * 88)
    print(f"DOCUMENT-GROUPED NESTED CV   pool={args.pool}  k={k}  folds={args.folds}")
    print("=" * 88)
    print(f"questions {len(rows)}, documents {len(uniq)}, "
          f"unmapped gold counted as miss: {sum(r['n_unmapped'] for r in rows)}")
    print(f"fold sizes (questions): {load}")
    print(f"inner search space: {len(CONFIGS)} retriever configs x {k + 1} quotas")

    # precompute every candidate's per-question recall once
    cand = {}
    for tr, vr in CONFIGS:
        for a in range(k + 1):
            cand[(tr, vr, a)] = score(rows, tr, vr, (a, k - a))

    pa = PAPER_QUOTA[k]
    ref_E = score(rows, "dense", "colqwen", pa)
    ref_A = score(rows, "dense", "dense", pa)

    selected = np.zeros(len(rows))
    picks = []
    for f in range(args.folds):
        inner, outer = fold != f, fold == f
        best, best_v = None, -1.0
        for key, v in cand.items():
            m = v[inner].mean()
            if m > best_v:
                best, best_v = key, m
        selected[outer] = cand[best][outer]
        picks.append((f, best, int(outer.sum())))

    print()
    print(f"{'fold':<6}{'selected config':<34}{'n held out':>12}")
    print("-" * 88)
    for f, (tr, vr, a) in [(p[0], p[1]) for p in picks]:
        n = [p[2] for p in picks if p[0] == f][0]
        print(f"{f:<6}{f'text={tr}, visual={vr}, quota {a}/{k - a}':<34}{n:>12}")
    print("-" * 88)
    stable = len({p[1] for p in picks}) == 1
    print(f"selection stable across folds: {'yes' if stable else 'NO'}"
          + ("" if stable else "  <- the configuration itself is fold-dependent"))

    print()
    print(f"{'system':<44}{'recall@' + str(k):>12}")
    print(f"{'A  local BGE-small surrogate, quota ' + f'{pa[0]}/{pa[1]}':<44}"
          f"{ref_A.mean():>12.4f}")
    print(f"{'E  closest local paper-style hybrid':<44}{ref_E.mean():>12.4f}")
    print(f"{'nested-CV selected pipeline (out-of-fold)':<44}{selected.mean():>12.4f}")

    # Bootstrapped ONCE and reused by both the printed table and the metrics
    # file below. Computing it twice from the same advancing generator drew two
    # different samples of the same quantity, so the human-readable CI and the
    # machine-readable one disagreed in the third decimal -- and metrics.json is
    # the authoritative record, which made the printed table the wrong one.
    deltas = [(label, cluster_ci(a - b, docs, rng))
              for label, a, b in
              (("nested-CV - paper-style (E)", selected, ref_E),
               ("nested-CV - surrogate (A)", selected, ref_A),
               ("paper-style (E) - surrogate (A)", ref_E, ref_A))]

    print()
    print(f"{'comparison':<44}{'delta':>10}{'doc-cluster 95% CI':>26}")
    print("-" * 88)
    for label, (d, lo, hi) in deltas:
        star = "*" if (lo > 0 or hi < 0) else " "
        print(f"{label:<44}{d:>+10.4f}"
              f"{'[' + format(lo, '+.4f') + ',' + format(hi, '+.4f') + ']' + star:>26}")
    print("-" * 88)
    print("Every question is scored under a configuration chosen without it.")
    print("This is the protocol that can support a generalisation claim; the")
    print("earlier single-split numbers cannot.")

    with ExperimentResult("E28", args.metrics_out,
                          title="document-grouped OOF 检索配置评价") as res:
        res.config(analysis="nested_cv", grouping="document", oof=True,
                   unmapped_gold="counted as miss",
                   pool=args.pool, k=k, seed=SEED, bootstrap=BOOT, folds=args.folds,
                   sample_unit="document", quota_paper=f"{pa[0]}/{pa[1]}",
                   n_questions=len(rows), n_documents=len(uniq),
                   selection_stable_across_folds=bool(stable),
                   protocol="grouped outer-CV with training-fold selection "
                            "(not a strict two-level inner CV)")
        res.data_file(args.db, args.quotes, args.colqwen)
        res.metric("recall_surrogate_A", float(ref_A.mean()),
                   desc="local BGE-small surrogate, official quota")
        res.metric("recall_paper_style_E", float(ref_E.mean()),
                   desc="closest local paper-style hybrid (dense text + ColQwen)")
        res.metric("recall_nested_cv_oof", float(selected.mean()),
                   desc="out-of-fold, configuration chosen without the question")
        for label, (dv, lo, hi) in deltas:
            res.metric("delta: " + label, dv, ci=(lo, hi), comparison=label)
        for f, (tr, vr, a_) in [(p_[0], p_[1]) for p_ in picks]:
            res.metric(f"fold{f}_selected_quota_text", a_,
                       fold=f, text_retriever=tr, visual_retriever=vr,
                       desc=f"fold {f} inner selection: {tr}/{vr}, {a_}/{k - a_}")
        res.per_question([
            {"question_uid": r["quid"], "doc_name": r["doc"], "fold": int(fold[i]),
             "n_gold_total": r["n_total"], "n_gold_unmapped": r["n_unmapped"],
             "recall_oof_selected": float(selected[i]),
             "recall_paper_style_E": float(ref_E[i]),
             "recall_surrogate_A": float(ref_A[i]),
             "delta_vs_E": float(selected[i] - ref_E[i])}
            for i, r in enumerate(rows)])
        res.note("internal grouped OOF, not external confirmation: the method "
                 "space was developed on these same 2,000 questions.")
        if not stable:
            res.note(f"configuration selection is NOT stable across folds at k={k}")
    if args.metrics_out:
        print()
        print(f"wrote metrics to {args.metrics_out}")


if __name__ == "__main__":
    main()
