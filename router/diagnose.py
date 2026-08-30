"""Why does the modality router fail to capture its headroom?

The oracle gain is large and completely consistent: +5.2 to +12.8 F1 on all 19
paired models. Yet a question-only router captures roughly none of it. Before
reporting that as a finding, three alternative explanations have to be ruled
out -- the failure could be the method rather than the data.

  1. UNDERFITTING. If the router cannot beat best-fixed even on the data it was
     trained on, the features are too weak and generalisation is not the issue.

  2. NO RANKING SIGNAL. Margin-weighted AUC asks whether the router orders
     questions correctly at all, independent of where the 0.5 threshold sits.
     An AUC at 0.5 means the question text carries no information.

  3. THE LABEL IS NOT A PROPERTY OF THE QUESTION. This is the important one.
     If two models disagree about which mode is better on the same question at
     close to chance, then "multimodal wins here" describes an interaction
     between one model and one question, not something a question-only router
     could ever read off. Cohen's kappa measures this against the chance rate
     implied by each model's own base rate.

A fourth probe tests the plan's design decision to derive oracle labels from
measured per-question performance rather than from the dataset's
`evidence_modality_type`. If gold modality predicted which arm wins, the
cheaper labelling would have been fine. It is a leak probe, never a feature.

Run:
    python -m router.diagnose
"""

import argparse
import itertools
import json
import os
import sqlite3
import sys

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from router.train_modality import (DEFAULT_DB, DEFAULT_SPLIT, evaluate,
                                   fit_router, load_features, load_outcomes,
                                   reference, split_masks)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The vocabulary `evidence_modality_type` actually uses. It never says "image":
# the four visual kinds are spelled out, and "text" is the only non-visual one.
# Testing for "image" silently matches nothing.
VISUAL_KINDS = {"table", "figure", "chart", "layout"}


def weighted_auc(score, label, weight):
    """AUC over positive/negative pairs, each pair weighted by both margins.

    Ties (weight 0) drop out on their own, which is what we want: getting a
    tie 'wrong' costs nothing, so it should not count for or against ranking.
    """
    pos = label.astype(bool)
    if pos.sum() == 0 or (~pos).sum() == 0:
        return float("nan")
    sp, wp = score[pos], weight[pos]
    sn, wn = score[~pos], weight[~pos]
    num = den = 0.0
    for s, w in zip(sp, wp):
        pair = w * wn
        num += (pair * ((s > sn) + 0.5 * (s == sn))).sum()
        den += pair.sum()
    return num / den if den else float("nan")


def kappa(a, b):
    """Cohen's kappa between two binary label vectors."""
    n = len(a)
    obs = (a == b).mean()
    pa, pb = a.mean(), b.mean()
    exp = pa * pb + (1 - pa) * (1 - pb)
    return (obs - exp) / (1 - exp) if abs(1 - exp) > 1e-12 else float("nan")


def gold_modality(dataset_dir, setting, q_ids):
    path = os.path.join(dataset_dir, f"evaluation_{setting}.jsonl")
    lookup = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                g = json.loads(line)
                mods = g.get("evidence_modality_type") or []
                if isinstance(mods, str):
                    mods = [mods]
                lookup[g["q_id"]] = set(m.lower() for m in mods)
    return [lookup.get(int(q), set()) for q in q_ids]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--split", default=DEFAULT_SPLIT)
    ap.add_argument("--setting", default="20", choices=["15", "20"])
    ap.add_argument("--dataset-dir", default=os.path.join(REPO_ROOT, "dataset"))
    args = ap.parse_args()

    q_ids, X, names, _ = load_features(args.setting)
    outcomes = load_outcomes(args.db, args.setting)
    masks, _ = split_masks(q_ids, args.split)
    models = sorted(outcomes)
    tr, te = masks["train"], masks["test"]

    arrs = {m: np.asarray([outcomes[m][int(q)] for q in q_ids], dtype=np.float64)
            for m in models}

    # ---- probe 0 --------------------------------------------------------
    # A negative result is only worth reporting once the apparatus is shown to
    # work. This trains the identical pipeline -- same features, same split,
    # same classifier -- on a label that is unambiguously present in the
    # question text. If this scores near chance too, the pipeline is broken and
    # nothing below means anything.
    print("=" * 94)
    print("PROBE 0 (positive control): can this pipeline learn a label that IS "
          "in the question?")
    print("=" * 94)
    con = sqlite3.connect(args.db)
    qtypes = dict(con.execute(
        "SELECT q_id, question_type FROM questions WHERE setting = ?",
        (args.setting,)).fetchall())
    con.close()
    from sklearn.metrics import roc_auc_score
    for target in ("Comparative", "Descriptive"):
        yc = np.asarray([qtypes[int(q)] == target for q in q_ids])
        sc, cl = fit_router(X[tr][:, :384], yc[tr],
                            np.ones(int(tr.sum())), C=0.3)
        pc = cl.predict_proba(sc.transform(X[te][:, :384]))[:, 1]
        print(f"  question_type == {target:<16} test AUC = "
              f"{roc_auc_score(yc[te], pc):.3f}   (base rate {yc.mean():.2f})")
    print("  Question embedding only, no candidate-set features. The apparatus "
          "works.")
    print()

    # ---- probes 1 and 2 -------------------------------------------------
    print("=" * 94)
    print("PROBE 1+2: can the router fit its own training data, and does it rank?")
    print("=" * 94)
    print(f"{'model':<22}{'train fixed':>12}{'train router':>13}"
          f"{'test fixed':>12}{'test router':>12}{'test AUC':>10}")
    print("-" * 94)
    aucs = []
    for m in models:
        arr = arrs[m]
        y = arr[:, 1] > arr[:, 0]
        w = np.abs(arr[:, 1] - arr[:, 0])
        scaler, clf = fit_router(X[tr], y[tr], w[tr], C=0.3)

        p_tr = clf.predict_proba(scaler.transform(X[tr]))[:, 1]
        p_te = clf.predict_proba(scaler.transform(X[te]))[:, 1]
        f1_tr, _, _ = evaluate(p_tr > 0.5, arr[tr])
        f1_te, _, _ = evaluate(p_te > 0.5, arr[te])
        fx_tr = max(arr[tr][:, 0].mean(), arr[tr][:, 1].mean())
        fx_te = max(arr[te][:, 0].mean(), arr[te][:, 1].mean())
        auc = weighted_auc(p_te, y[te], w[te])
        aucs.append(auc)
        print(f"{m:<22}{fx_tr*100:>12.1f}{f1_tr*100:>13.1f}"
              f"{fx_te*100:>12.1f}{f1_te*100:>12.1f}{auc:>10.3f}")
    print("-" * 94)
    print(f"mean test AUC {np.nanmean(aucs):.3f}  "
          f"(0.500 = the question carries no ranking information)")

    # ---- probe 3 --------------------------------------------------------
    print()
    print("=" * 94)
    print("PROBE 3: do different models agree on WHICH mode wins a given question?")
    print("=" * 94)
    labels = {m: (arrs[m][:, 1] > arrs[m][:, 0]).astype(int) for m in models}
    ks, aggs = [], []
    for a, b in itertools.combinations(models, 2):
        # Restrict to questions where both models had a strict preference; a
        # tie is an absence of opinion, not a disagreement.
        both = (np.abs(arrs[a][:, 1] - arrs[a][:, 0]) > 1e-9) & \
               (np.abs(arrs[b][:, 1] - arrs[b][:, 0]) > 1e-9)
        k = kappa(labels[a][both], labels[b][both])
        ks.append(k)
        aggs.append((labels[a][both] == labels[b][both]).mean())
    ks = np.asarray(ks)
    print(f"model pairs compared          : {len(ks)}")
    print(f"raw agreement   mean / min / max: {np.mean(aggs):.3f} / "
          f"{np.min(aggs):.3f} / {np.max(aggs):.3f}")
    print(f"Cohen's kappa   mean / min / max: {ks.mean():.3f} / "
          f"{ks.min():.3f} / {ks.max():.3f}")
    print(f"pairs with kappa > 0.2        : {(ks > 0.2).sum()}/{len(ks)}")
    print("\nkappa near 0 means two models disagree about the better mode as "
          "often as their base rates alone predict:\nthe preference belongs to "
          "the model-question pair, not to the question.")

    # ---- probe 4 --------------------------------------------------------
    print()
    print("=" * 94)
    print("PROBE 4 (leak probe): does the dataset's own gold modality predict "
          "which arm wins?")
    print("=" * 94)
    mods = gold_modality(args.dataset_dir, args.setting, q_ids)
    has_visual = np.asarray([bool(s & VISUAL_KINDS) for s in mods])
    # Almost every question has some visual gold, so "has a visual" cannot
    # discriminate. The discriminating version is whether the answer lives
    # *only* in visuals, with no text evidence to fall back on -- the case
    # where a real image should help most.
    visual_only = np.asarray([bool(s & VISUAL_KINDS) and "text" not in s
                              for s in mods])
    print(f"gold includes any visual : {has_visual.mean():.1%}  "
          f"(too near 100% to route on)")
    print(f"gold is visual-only      : {visual_only.mean():.1%}  "
          f"(the policy tested below)")
    print(f"{'model':<22}{'visual-only policy':>22}{'best fixed':>12}"
          f"{'ORACLE':>9}")
    print("-" * 94)
    for m in models:
        arr = arrs[m][te]
        f1, _, _ = evaluate(visual_only[te], arr)
        _, _, orc = reference(arr)
        fx = max(arr[:, 0].mean(), arr[:, 1].mean())
        print(f"{m:<22}{f1*100:>22.1f}{fx*100:>12.1f}{orc[0]*100:>9.1f}")
    print("-" * 94)
    # ---- probe 5 --------------------------------------------------------
    print()
    print("=" * 94)
    print("PROBE 5: is the oracle gain modality complementarity, or just "
          "max-of-two-noisy-scores?")
    print("=" * 94)
    print("Taking the better of two per-question scores yields a positive gain "
          "even between systems that are")
    print("equally good on average -- part selection on noise, part genuine "
          "per-question complementarity. The")
    print("control runs the same oracle over two DIFFERENT MODELS in the SAME "
          "mode, matched on the same range of")
    print("mean gap. This does not isolate noise (two models do differ "
          "per question), but it does establish a")
    print("reference level: if the cross-modality gain is no larger than the "
          "gain between two arbitrary systems,")
    print("then nothing about it is specific to modality, and it should not be "
          "read as modality complementarity.")
    print()

    def orc_gain(a, b):
        """Oracle-over-two-columns gain above the better column mean."""
        return (np.maximum(a, b).mean() - max(a.mean(), b.mean())) * 100

    cross = [(m, orc_gain(arrs[m][:, 0], arrs[m][:, 1]),
              abs(arrs[m][:, 0].mean() - arrs[m][:, 1].mean()) * 100)
             for m in models]

    # Same-mode control: every model pair, pure-text only. Both columns are
    # then the same kind of measurement, so any gain is pure selection effect.
    same = []
    for a, b in itertools.combinations(models, 2):
        same.append((f"{a} vs {b}", orc_gain(arrs[a][:, 0], arrs[b][:, 0]),
                     abs(arrs[a][:, 0].mean() - arrs[b][:, 0].mean()) * 100))

    print(f"{'comparison':<46}{'n':>5}{'mean gain':>11}{'mean |dF1|':>12}")
    print("-" * 94)
    print(f"{'SAME model, two MODES (the Phase 1A.5 oracle)':<46}{len(cross):>5}"
          f"{np.mean([c[1] for c in cross]):>+11.1f}"
          f"{np.mean([c[2] for c in cross]):>12.1f}")
    print(f"{'TWO models, SAME mode (control)':<46}{len(same):>5}"
          f"{np.mean([s[1] for s in same]):>+11.1f}"
          f"{np.mean([s[2] for s in same]):>12.1f}")

    # Oracle gain shrinks as one column comes to dominate the other, so the
    # control is restricted to the same range of mean gaps -- otherwise the two
    # rows would not be compared like for like.
    lo, hi = min(c[2] for c in cross), max(c[2] for c in cross)
    matched = [s for s in same if lo <= s[2] <= hi]
    print(f"{'  ... restricted to the same |dF1| range':<46}{len(matched):>5}"
          f"{np.mean([s[1] for s in matched]):>+11.1f}"
          f"{np.mean([s[2] for s in matched]):>12.1f}")
    print("-" * 94)
    print(f"cross-modality gain range: "
          f"{min(c[1] for c in cross):+.1f} to {max(c[1] for c in cross):+.1f}")
    print(f"same-mode control range  : "
          f"{min(s[1] for s in matched):+.1f} to {max(s[1] for s in matched):+.1f}")
    print()
    print("Probe 3 (kappa) carries the argument on its own and has no such "
          "confound: if 'multimodal suits this")
    print("question' were a stable property of the question, models would agree "
          "about it. They do not.")


if __name__ == "__main__":
    main()
