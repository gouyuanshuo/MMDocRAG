"""Train and evaluate the generation-input modality router (Phase 1A.5).

Task: given only the question and the shape of its candidate set, decide
whether to send the images as images (multimodal) or as their text
descriptions (pure-text).

Labels are free. Both arms already exist for the same 2000 questions, so the
oracle choice per question is known without spending anything. The label is
`multimodal wins`, and each sample is weighted by |f1_mm - f1_pt|. The
weighting is not a detail: on gpt-4.1, 729 of 2000 questions are exact ties,
which carry no signal and would otherwise be a third of the training set
pulling in an arbitrary direction. Weighting by the margin makes the classifier
spend its capacity on the decisions that actually move the score.

Reported metrics are end-to-end, not classification accuracy. Accuracy on a
tie is meaningless; what matters is the F1 the routed system achieves, how much
of the oracle's headroom that captures, and what it costs.

Run:
    python -m router.train_modality --model gpt-4o
    python -m router.train_modality --all
    python -m router.train_modality --transfer
"""

import argparse
import json
import os
import sqlite3
import sys

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO_ROOT, "router", "outcomes.sqlite")
DEFAULT_SPLIT = os.path.join(REPO_ROOT, "manifests", "split_doc_disjoint.json")
SEED = 20260824


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------

# Feature groups, separated because they differ in whether a deployed system
# could actually compute them, and because mixing them hid a real signal once
# already (see docs/lab-notebook.html L10: a 384-d embedding concatenated onto
# 11 informative columns drove R^2 from +0.110 to -0.070).
#
#   shape      candidate-set statistics. Computable at query time. DEPLOYABLE.
#   qtype      one-hot of the human-annotated question_type. PRIVILEGED: it is
#              a dataset annotation, not something a live system observes, so a
#              result that depends on it is a diagnostic, not a system claim.
#   emb        384-d question embedding. Deployable but high-variance at this
#              sample size.
SHAPE_FEATURES = ("n_txt", "n_img", "log_txt_chars", "log_desc_chars",
                  "log_desc_over_txt")
GROUPS = {
    "emb": ("emb",),
    "shape": ("shape",),
    "qtype": ("qtype",),
    "shape+qtype": ("shape", "qtype"),
    "shallow": ("shape", "qtype"),
    "all": ("emb", "shape", "qtype"),
}


def load_features(setting, groups=("emb", "shape", "qtype")):
    path = os.path.join(REPO_ROOT, "router", f"features_{setting}.npz")
    z = np.load(path, allow_pickle=True)
    sh_names = [str(n) for n in z["shallow_names"]]
    shape_idx = [i for i, n in enumerate(sh_names) if n in SHAPE_FEATURES]
    qtype_idx = [i for i, n in enumerate(sh_names) if n.startswith("qtype=")]
    parts, names = [], []
    if "emb" in groups:
        parts.append(z["emb"])
        names += [f"emb{i}" for i in range(z["emb"].shape[1])]
    if "shape" in groups:
        parts.append(z["shallow"][:, shape_idx])
        names += [sh_names[i] for i in shape_idx]
    if "qtype" in groups:
        parts.append(z["shallow"][:, qtype_idx])
        names += [sh_names[i] for i in qtype_idx]
    if not parts:
        raise SystemExit("no feature groups selected")
    return z["q_ids"], np.hstack(parts), names, str(z["embed_model"])


def load_outcomes(db_path, setting):
    """{model: {q_id: (f1_pt, f1_mm, tok_pt, tok_mm)}}"""
    con = sqlite3.connect(db_path)
    rows = con.execute("""
        SELECT t.model, t.q_id, t.f1, m.f1, t.in_tok, m.in_tok
        FROM outcomes t
        JOIN outcomes m
          ON  m.model = t.model AND m.setting = t.setting AND m.q_id = t.q_id
        WHERE t.setting = ? AND t.mode = 'pure-text' AND m.mode = 'multimodal'
    """, (setting,)).fetchall()
    con.close()
    out = {}
    for model, q_id, f1_pt, f1_mm, tok_pt, tok_mm in rows:
        out.setdefault(model, {})[q_id] = (f1_pt, f1_mm, tok_pt or 0, tok_mm or 0)
    return out


def split_masks(q_ids, split_path):
    with open(split_path, encoding="utf-8") as fh:
        payload = json.load(fh)
    lookup = payload["q_id_to_split"]
    assign = np.asarray([lookup[str(q)] for q in q_ids])
    return {k: assign == k for k in ("train", "val", "test")}, payload["name"]


# --------------------------------------------------------------------------
# policy evaluation
# --------------------------------------------------------------------------

def evaluate(choice, arr):
    """choice: bool array, True = multimodal. arr: (n,4) f1_pt,f1_mm,tok_pt,tok_mm."""
    f1 = np.where(choice, arr[:, 1], arr[:, 0]).mean()
    tok = np.where(choice, arr[:, 3], arr[:, 2]).mean()
    return f1, tok, float(choice.mean())


def reference(arr):
    always_t = evaluate(np.zeros(len(arr), bool), arr)
    always_m = evaluate(np.ones(len(arr), bool), arr)
    oracle = evaluate(arr[:, 1] > arr[:, 0], arr)
    return always_t, always_m, oracle


def qtype_rule(X, names, arr_train, mask_train):
    """Per-question-type majority vote, learned on train only.

    The simplest interpretable policy that is not a constant: for each of the 8
    question types, send every question of that type to whichever mode won more
    often (by summed margin) on the training documents.
    """
    idx = {n: i for i, n in enumerate(names)}
    cols = [(t, X[:, -len(names) + idx[t]]) for t in names if t.startswith("qtype=")]
    prefer = {}
    for t, col in cols:
        sel = mask_train & (col > 0.5)
        if sel.sum() == 0:
            prefer[t] = False
            continue
        sub = arr_train[col[mask_train] > 0.5]
        prefer[t] = float((sub[:, 1] - sub[:, 0]).sum()) > 0
    def apply(mask):
        out = np.zeros(mask.sum(), bool)
        for t, col in cols:
            out |= (col[mask] > 0.5) & prefer[t]
        return out
    return apply, prefer


def fit_router(Xtr, ytr, wtr, C):
    scaler = StandardScaler().fit(Xtr)
    clf = LogisticRegression(C=C, max_iter=2000, random_state=SEED)
    clf.fit(scaler.transform(Xtr), ytr, sample_weight=wtr)
    return scaler, clf


def run_model(model, outcomes, q_ids, X, names, masks, verbose=True):
    arr = np.asarray([outcomes[model][int(q)] for q in q_ids], dtype=np.float64)
    y = (arr[:, 1] > arr[:, 0])
    w = np.abs(arr[:, 1] - arr[:, 0])

    tr, va, te = masks["train"], masks["val"], masks["test"]
    # Pick C on val by the metric that matters -- achieved F1 -- not accuracy.
    best = None
    for C in (0.01, 0.03, 0.1, 0.3, 1.0, 3.0):
        scaler, clf = fit_router(X[tr], y[tr], w[tr], C)
        pick = clf.predict(scaler.transform(X[va])).astype(bool)
        f1, _, _ = evaluate(pick, arr[va])
        if best is None or f1 > best[0]:
            best = (f1, C, scaler, clf)
    _, C, scaler, clf = best

    prob_te = clf.predict_proba(scaler.transform(X[te]))[:, 1]
    learned = evaluate(prob_te > 0.5, arr[te])

    rule_apply, prefer = qtype_rule(X, names, arr[tr], tr)
    rule = evaluate(rule_apply(te), arr[te])

    a_t, a_m, orc = reference(arr[te])
    # Which constant policy you would have picked knowing only the train set.
    fixed_is_mm = arr[tr][:, 1].mean() > arr[tr][:, 0].mean()
    fixed = a_m if fixed_is_mm else a_t

    head = orc[0] - fixed[0]
    def captured(v):
        return (v[0] - fixed[0]) / head if head > 1e-12 else float("nan")

    return {
        "model": model, "C": C, "n_test": int(te.sum()),
        "fixed_mode": "multimodal" if fixed_is_mm else "pure-text",
        "always_text": a_t, "always_multi": a_m, "fixed": fixed,
        "oracle": orc, "rule": rule, "learned": learned,
        "headroom": head,
        "captured_rule": captured(rule), "captured_learned": captured(learned),
        "prob_te": prob_te, "arr_te": arr[te],
        "scaler": scaler, "clf": clf, "prefer": prefer,
    }


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------

def print_one(r):
    print(f"\n--- {r['model']}  (test n={r['n_test']}, C={r['C']}) ---")
    print(f"{'policy':<22}{'F1':>7}{'in_tok':>9}{'%multi':>8}{'of headroom':>13}")
    for label, key in (("always pure-text", "always_text"),
                       ("always multimodal", "always_multi"),
                       ("best fixed (train)", "fixed"),
                       ("rule: question type", "rule"),
                       ("learned router", "learned"),
                       ("ORACLE", "oracle")):
        f1, tok, share = r[key]
        cap = ""
        if key == "rule":
            cap = f"{r['captured_rule']:>12.0%}"
        elif key == "learned":
            cap = f"{r['captured_learned']:>12.0%}"
        elif key == "oracle":
            cap = f"{'100%':>12}"
        print(f"{label:<22}{f1*100:>7.1f}{tok:>9.0f}{share:>8.1%}{cap:>13}")


def print_table(results):
    print("\n" + "=" * 100)
    print("MODALITY ROUTER, document-disjoint test split")
    print("=" * 100)
    print(f"{'model':<22}{'fixed':>7}{'rule':>7}{'router':>8}{'ORACLE':>8}"
          f"{'head':>7}{'captured':>10}{'tok vs fixed':>14}")
    print("-" * 100)
    for r in results:
        tok_delta = r["learned"][1] / r["fixed"][1] - 1 if r["fixed"][1] else 0
        print(f"{r['model']:<22}{r['fixed'][0]*100:>7.1f}{r['rule'][0]*100:>7.1f}"
              f"{r['learned'][0]*100:>8.1f}{r['oracle'][0]*100:>8.1f}"
              f"{r['headroom']*100:>+7.1f}{r['captured_learned']:>10.0%}"
              f"{tok_delta:>+13.0%} ")
    print("-" * 100)
    cap = [r["captured_learned"] for r in results]
    gain = [(r["learned"][0] - r["fixed"][0]) * 100 for r in results]
    beat = sum(1 for g in gain if g > 0)
    print(f"router beats best-fixed on {beat}/{len(results)} models; "
          f"mean gain {np.mean(gain):+.1f} F1, "
          f"mean headroom captured {np.mean(cap):.0%}")


def print_transfer(results, outcomes, q_ids, X, masks):
    """Train on one model's labels, route another model's questions."""
    models = [r["model"] for r in results]
    te = masks["test"]
    print("\n" + "=" * 100)
    print("CROSS-MODEL TRANSFER: F1 captured of target's headroom "
          "(row = router trained on, column = model routed)")
    print("=" * 100)
    src_show = models[:8]
    print(f"{'train \\ apply':<22}" + "".join(f"{m[:9]:>10}" for m in src_show))
    print("-" * 100)
    by_model = {r["model"]: r for r in results}
    for src in src_show:
        rs = by_model[src]
        prob = rs["clf"].predict_proba(rs["scaler"].transform(X[te]))[:, 1]
        pick = prob > 0.5
        cells = []
        for tgt in src_show:
            arr = np.asarray([outcomes[tgt][int(q)] for q in q_ids],
                             dtype=np.float64)[te]
            f1, _, _ = evaluate(pick, arr)
            rt = by_model[tgt]
            head = rt["oracle"][0] - rt["fixed"][0]
            cells.append(f"{(f1 - rt['fixed'][0]) / head:>10.0%}" if head > 1e-12
                         else f"{'n/a':>10}")
        print(f"{src:<22}" + "".join(cells))
    print("-" * 100)
    print("Diagonal is the in-domain router. Off-diagonal near the diagonal "
          "means the signal is a property of the question,\nnot of the model "
          "-- which is what makes a single router reusable across generators.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--split", default=DEFAULT_SPLIT)
    ap.add_argument("--setting", default="20", choices=["15", "20"])
    ap.add_argument("--model", action="append", help="repeatable")
    ap.add_argument("--all", action="store_true", help="every paired model")
    ap.add_argument("--transfer", action="store_true",
                    help="also print the cross-model transfer matrix")
    ap.add_argument("--detail", action="store_true",
                    help="per-model policy breakdown")
    ap.add_argument("--features", default="all", choices=sorted(GROUPS),
                    help="feature group. 'qtype' is a PRIVILEGED dataset "
                         "annotation, not a deployable signal; 'shape' is the "
                         "deployable subset. Default 'all' reproduces every "
                         "number published before 2026-08-25.")
    ap.add_argument("--manifest", default="",
                    help="write a json manifest of this run to this path")
    args = ap.parse_args()

    q_ids, X, names, embed_model = load_features(
        args.setting, GROUPS[args.features])
    outcomes = load_outcomes(args.db, args.setting)
    masks, split_name = split_masks(q_ids, args.split)

    models = args.model or (sorted(outcomes) if args.all else ["gpt-4o"])
    missing = [m for m in models if m not in outcomes]
    if missing:
        raise SystemExit(f"no paired outcomes for: {missing}")

    print(f"split '{split_name}': train {masks['train'].sum()}, "
          f"val {masks['val'].sum()}, test {masks['test'].sum()}")
    print(f"features: --features {args.features} -> {X.shape[1]}-d "
          f"({embed_model} + {len(names)} named)")
    if args.features in ("all", "qtype", "shape+qtype", "shallow"):
        print("  NOTE: includes question_type, a human annotation. Results that "
              "depend on it are diagnostic, not deployable.")

    results = [run_model(m, outcomes, q_ids, X, names, masks) for m in models]
    if args.detail:
        for r in results:
            print_one(r)
    print_table(results)
    if args.manifest:
        import json
        import subprocess
        try:
            commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).decode().strip()
        except Exception:
            commit = "unknown"
        with open(args.manifest, "w", encoding="utf-8") as fh:
            json.dump({"experiment": "E9 modality router", "status": "EXPLORATORY",
                       "features": args.features, "n_features": int(X.shape[1]),
                       "feature_names": names if len(names) <= 40 else
                       names[:40] + ["..."], "embed_model": embed_model,
                       "setting": args.setting, "split": split_name,
                       "git_commit": commit, "n_models": len(models),
                       "models": models,
                       "privileged_features_included":
                           args.features in ("all", "qtype", "shape+qtype",
                                             "shallow")},
                      fh, indent=2, ensure_ascii=False)
        print(f"wrote manifest {args.manifest}")
    if args.transfer:
        print_transfer(results, outcomes, q_ids, X, masks)


if __name__ == "__main__":
    main()
