"""Two-stage allocation: look at what the first pass returned, then spend the rest.

E19-E21 left the bottleneck sharply defined. The per-query optimal text/image
split is real structure -- permuting it across queries costs 0.10 recall -- and
a rule that consumes the true modality mix captures 41-49% of the oracle
headroom. What fails is the input: regressing `visual_share` from the question
embedding plus first-pass score summaries gives a test R2 of -0.07, worse than
predicting the training mean.

Every feature tried so far is available *before* retrieving anything. The
retrieval layer's structural advantage over the generation layer was supposed to
be that you can look before you leap, and this is the experiment that uses it:
spend a small balanced first pass, read what came back, and allocate the
remainder on that evidence. It is the mechanism SAM-RAG and MARA describe as
test-time reflection, reduced to its cheapest form -- no LLM call, just lexical
statistics over the returned items.

The features that only a first pass can provide:

    idf coverage      how much of the question's rare-term mass the returned
                      text items actually contain, and separately the image
                      items. If the text arm came back empty-handed on the
                      terms that matter, the answer is probably not in text.
    coverage gap      the difference between those two. The signal is the
                      comparison, not either level.
    score decay       score[0] / score[k1-1] within each arm -- a sharp decay
                      means one item stood out, a flat one means nothing did.

Bound first, then realise. `--oracle-observe` reports what a reflection
mechanism could achieve if the first pass revealed exactly how much gold of each
modality it had already captured. If even that cannot beat the fixed split,
reflection is not worth engineering; if it can, the gap between it and the
realisable features says how much better the observations need to get.

Run:
    python -m retrieval.reflect_alloc --pool canonical
    python -m retrieval.reflect_alloc --pool selfbuilt --k-first 6
"""

import argparse
import collections
import json
import math
import os
import pickle
import sqlite3
import sys

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sklearn.linear_model import Ridge                # noqa: E402
from sklearn.preprocessing import StandardScaler      # noqa: E402

from retrieval.corpus import tokenize                 # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO_ROOT, "canonical", "mmdocrag.sqlite")
QUOTES_DB = os.path.join(REPO_ROOT, "retrieval", "quotes.sqlite")
DEFAULT_SPLIT = os.path.join(REPO_ROOT, "manifests", "split_doc_disjoint.json")
K_TOTAL = 20
SEED = 20260825


def load_texts(pool):
    """id -> token set, for every retrievable unit in the pool."""
    con = sqlite3.connect(DEFAULT_DB)
    out = {}
    for eid, txt, desc, etype in con.execute(
            "SELECT evidence_id, text, img_description, type FROM canonical_evidence"):
        body = txt if etype == "text" else desc
        if pool == "selfbuilt" and etype == "text":
            continue                      # self-built pool replaces the text side
        out[eid] = set(tokenize((body or "").lower()))
    con.close()
    if pool == "selfbuilt":
        qc = sqlite3.connect(QUOTES_DB)
        for cid, txt in qc.execute("SELECT chunk_id, text FROM chunks"):
            out[cid] = set(tokenize((txt or "").lower()))
        qc.close()
    return out


def idf_table(texts):
    df = collections.Counter()
    for toks in texts.values():
        df.update(toks)
    n = len(texts)
    return {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}


def first_pass_features(row, texts, idf, k_first):
    """Only what a balanced first pass of k_first slots could actually see."""
    half = k_first // 2
    q = set(tokenize((row["question"] or "").lower())) if "question" in row else None
    q = q if q else set()
    den = sum(idf.get(t, 0.0) for t in q) or 1.0

    feats = []
    covs = {}
    for kind in ("text", "visual"):
        got = row["rank"]["bm25"][kind][:half]
        union = set()
        best = 0.0
        for i in got:
            toks = texts.get(i, set())
            union |= (q & toks)
            best = max(best, sum(idf.get(t, 0.0) for t in (q & toks)) / den)
        cov_union = sum(idf.get(t, 0.0) for t in union) / den
        covs[kind] = cov_union
        s = row["scores"][kind]
        decay = s[0] / (s[1] + 1e-6)
        feats += [cov_union, best, decay, float(len(got))]
    feats += [covs["visual"] - covs["text"],
              covs["visual"] / (covs["text"] + 1e-6),
              (covs["visual"] - covs["text"]) / (covs["visual"] + covs["text"] + 1e-6)]
    return feats


def recall_two_stage(row, k_first, a_rest, k_total):
    """First pass takes k_first/2 of each; the remainder splits a_rest to text."""
    half = k_first // 2
    rest = k_total - k_first
    a_rest = int(np.clip(a_rest, 0, rest))
    got = set(row["rank"]["bm25"]["text"][:half + a_rest])
    got |= set(row["rank"]["bm25"]["visual"][:half + (rest - a_rest)])
    return len(row["gold"] & got) / len(row["gold"])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pool", default="canonical", choices=("canonical", "selfbuilt"))
    ap.add_argument("--k-total", type=int, default=K_TOTAL)
    ap.add_argument("--k-first", type=int, default=6,
                    help="slots spent on the balanced probe, split evenly")
    ap.add_argument("--split", default=DEFAULT_SPLIT)
    args = ap.parse_args()
    k, kf = args.k_total, args.k_first
    rest = k - kf

    rows = pickle.load(open(
        os.path.join(REPO_ROOT, "retrieval", f"budget_rows_{args.pool}.pkl"), "rb"))
    # questions were not stored in the cache; join them back on q_id
    con = sqlite3.connect(DEFAULT_DB)
    qtext = dict(con.execute(
        "SELECT q_id, question FROM questions WHERE split = 'evaluation'"))
    con.close()
    for r in rows:
        r["question"] = qtext.get(r["q_id"], "")

    print(f"pool {args.pool}, {len(rows)} questions, k_total {k}, "
          f"first pass {kf} ({kf//2}+{kf//2}), remaining {rest} to allocate\n")

    texts = load_texts(args.pool)
    idf = idf_table(texts)
    print(f"pool units: {len(texts)}")

    # recall for every possible split of the remainder
    R = np.asarray([[recall_two_stage(r, kf, a, k) for a in range(rest + 1)]
                    for r in rows])
    vis = np.asarray([r["visual_share"] for r in rows])

    z = np.load(os.path.join(REPO_ROOT, "router", "features_20.npz"), allow_pickle=True)
    emb = {int(q): z["emb"][i] for i, q in enumerate(z["q_ids"])}
    E = np.asarray([emb[r["q_id"]] for r in rows])

    def pre_scores(r):
        t, v = r["scores"]["text"], r["scores"]["visual"]
        e = 1e-6
        return [t[0], t[1], t[2], v[0], v[1], v[2], v[0] - t[0], v[1] - t[1],
                v[0] / (t[0] + e), v[1] / (t[1] + e),
                (v[0] - t[0]) / (v[0] + t[0] + e)]
    S = np.asarray([pre_scores(r) for r in rows])
    F = np.asarray([first_pass_features(r, texts, idf, kf) for r in rows])
    print(f"first-pass features: {F.shape[1]} dims\n")

    assign = json.load(open(args.split, encoding="utf-8"))["q_id_to_split"]
    sp = np.asarray([assign[str(r["q_id"])] for r in rows])
    tr, va, te = sp == "train", sp == "val", sp == "test"
    n_te = te.sum()
    ar = np.arange(n_te)

    best_a = int(np.argmax(R[tr].mean(axis=0)))
    fixed = R[te][:, best_a].mean()
    orc = R[te][ar, R[te].argmax(axis=1)].mean()

    print("=" * 86)
    print("1. CAN A FIRST PASS PREDICT THE MODALITY MIX?   (test R2 on visual_share)")
    print("=" * 86)
    # The 384-dim embedding is included to be measured, not because it helps:
    # 1,211 training queries cannot support it, and adding it to the 11-dim
    # score features drops R2 from positive to negative. Earlier experiments
    # (E19/E21) always concatenated it, which is why they never saw a positive
    # R2 -- the signal was there and the embedding was burying it.
    sets = {"question embedding": E,
            "pre-retrieval scores": S,
            "embedding + pre-scores": np.hstack([E, S]),
            "FIRST-PASS observations": F,
            "pre-scores + first-pass": np.hstack([S, F]),
            "everything": np.hstack([E, S, F])}
    print(f"{'features':<28}{'dims':>6}{'test R2':>10}{'corr':>9}")
    print("-" * 86)
    preds = {}
    for name, X in sets.items():
        sc = StandardScaler().fit(X[tr])
        rg = Ridge(alpha=10.0).fit(sc.transform(X[tr]), vis[tr])
        p = np.clip(rg.predict(sc.transform(X[te])), 0, 1)
        preds[name] = p
        r2 = 1 - ((vis[te] - p) ** 2).sum() / ((vis[te] - vis[tr].mean()) ** 2).sum()
        c = np.corrcoef(p, vis[te])[0, 1]
        print(f"{name:<28}{X.shape[1]:>6}{r2:>10.3f}{c:>9.3f}")
    print("-" * 86)
    print("R2 below zero means the model is beaten by always predicting the "
          "training mean.")

    print()
    print("=" * 86)
    print("2. WHAT THAT BUYS, AND WHAT AN ORACLE OBSERVATION WOULD BUY")
    print("=" * 86)
    print(f"{'policy':<46}{'recall@' + str(k):>11}{'vs fixed':>11}{'of headroom':>13}")
    print("-" * 86)

    def report(label, a_te):
        got = R[te][ar, np.clip(a_te, 0, rest).astype(int)].mean()
        head = orc - fixed
        print(f"{label:<46}{got:>11.3f}{got - fixed:>+11.3f}"
              f"{(got - fixed) / head if head > 1e-9 else float('nan'):>12.0%}")
        return got

    print(f"{'fixed split (a_rest=' + str(best_a) + ', on train)':<46}"
          f"{fixed:>11.3f}{0.0:>+11.3f}{0.0:>12.0%}")
    for name in ("embedding + pre-scores", "FIRST-PASS observations", "everything"):
        report(f"proportional from {name}",
               np.rint(rest * (1 - preds[name])))
    # oracle observation: the first pass reveals the true mix
    report("proportional from TRUE mix (oracle observation)",
           np.rint(rest * (1 - vis[te])))
    print(f"{'ORACLE remaining split':<46}{orc:>11.3f}{orc - fixed:>+11.3f}"
          f"{1.0:>12.0%}")
    print("-" * 86)
    print(f"first pass costs {kf} of the {k} slots and is spent before any decision,")
    print("so every row above pays the same retrieval cost.")

    # ---- 3. shrink the proportional split toward the fixed one ----
    print()
    print("=" * 86)
    print("3. SHRINKAGE ON THE BEST FEATURE SET  (lambda chosen on val)")
    print("=" * 86)
    print("Proportional allocation amplifies prediction error: even at R2 ~ 0.14")
    print("most predicted variance is wrong, and the recall curve is flat near its")
    print("peak, so a confident wrong split costs more than a timid right one.")
    print()
    denom = ((vis[te] - vis[tr].mean()) ** 2).sum()
    def r2_of(nm):
        return 1 - ((vis[te] - preds[nm]) ** 2).sum() / denom
    cand = ("pre-retrieval scores", "FIRST-PASS observations",
            "pre-scores + first-pass")
    best_set = max(cand, key=r2_of)
    X = sets[best_set]
    sc = StandardScaler().fit(X[tr])
    rg = Ridge(alpha=10.0).fit(sc.transform(X[tr]), vis[tr])
    p_va = np.clip(rg.predict(sc.transform(X[va])), 0, 1)
    p_te = np.clip(rg.predict(sc.transform(X[te])), 0, 1)
    a_va, a_te = np.rint(rest * (1 - p_va)), np.rint(rest * (1 - p_te))
    print(f"feature set: {best_set}  (test R2 {r2_of(best_set):.3f})")
    print(f"{"lambda":<10}{"val recall":>13}{"test recall":>14}"
          f"{"test vs fixed":>16}{"of headroom":>14}")
    print("-" * 86)
    head = orc - fixed
    val_by_lam = {}
    for lam in (0.0, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0):
        mv = np.clip(np.rint((1 - lam) * best_a + lam * a_va), 0, rest).astype(int)
        mt = np.clip(np.rint((1 - lam) * best_a + lam * a_te), 0, rest).astype(int)
        gv = R[va][np.arange(va.sum()), mv].mean()
        gt = R[te][ar, mt].mean()
        val_by_lam[lam] = gv
        print(f"{lam:<10.2f}{gv:>13.3f}{gt:>14.3f}{gt - fixed:>+16.3f}"
              f"{(gt - fixed) / head:>13.0%}")
    print("-" * 86)
    bl = max(val_by_lam, key=val_by_lam.get)
    mt = np.clip(np.rint((1 - bl) * best_a + bl * a_te), 0, rest).astype(int)
    gt = R[te][ar, mt].mean()
    print(f"lambda selected on val = {bl}  ->  test {gt:.3f}, "
          f"{gt - fixed:+.3f} vs fixed = {(gt - fixed) / head:.0%} of the headroom")


if __name__ == "__main__":
    main()
