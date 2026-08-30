"""E17 redone: learn the retriever OUTCOME, not a hand-specified modality proxy.

What the original did, and why it does not answer the question
--------------------------------------------------------------
`route_headroom.py` fits a classifier on `mostly_visual` -- whether a query's
gold evidence is mostly figures and tables -- and then routes with a hardcoded
rule: predicted-visual goes to BM25, predicted-textual goes to dense. So it
tests one hand-authored policy driven by a proxy label. If that policy loses, it
tells us the proxy is bad or the mapping is wrong; it does not tell us whether a
learned per-query retriever choice is possible. The published E17 conclusion was
drawn from exactly that experiment and was too broad.

The related claim that 61.9% of questions carry gold in both modalities also
does not settle it: BM25 and dense both retrieve text chunks *and* image
descriptions, so a query's modality mix and which retriever wins on it are
different quantities.

What this does instead
----------------------
Trains directly on the outcome. For every query the target is

    regret = recall@k(dense) - recall@k(BM25)

with the sign as the classification label and |regret| as the sample weight,
because a query where the two retrievers tie contributes nothing to a routing
decision and should not pull the fit around.

Feature groups are separated and reported apart, following the E9 correction:

    emb     384-d question embedding. Deployable.
    scores  first-pass retrieval statistics -- score magnitudes, dispersion, and
            the rank overlap between the two retrievers' top-10. Deployable, and
            the group most likely to carry the signal, since disagreement
            between retrievers is observable before any gold is known.
    shape   candidate pool size and composition. Deployable.

The comparison that matters is against static RRF, not against the better single
retriever: fusion is the standing static baseline this project already measured,
and a router costs one retriever where RRF costs two, so the router has to reach
RRF's quality to be worth anything.

All intervals are document-cluster bootstrap. Exploratory: this split has been
observed repeatedly.

Run:
    python -m retrieval.route_outcome --features all
    python -m retrieval.route_outcome --features scores --k 20
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

from retrieval.bm25 import BM25                          # noqa: E402
from retrieval.corpus import normalize, tokenize         # noqa: E402
from retrieval.dense import load as load_dense           # noqa: E402
from retrieval.eval_quote_recall import surrogate        # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO_ROOT, "canonical", "mmdocrag.sqlite")
DEFAULT_SPLIT = os.path.join(REPO_ROOT, "manifests", "split_doc_disjoint.json")
FEATURES_NPZ = os.path.join(REPO_ROOT, "router", "features_20.npz")
SEED = 20260825
BOOT = 4000
RRF_C = 60


def build(db_path, k, repr_mode="vlm"):
    con = sqlite3.connect(db_path)
    ev = con.execute(
        "SELECT evidence_id, doc_name, type, text, img_description "
        "FROM canonical_evidence ORDER BY doc_name, evidence_id").fetchall()
    qs = con.execute(
        "SELECT question_uid, doc_name, question, q_id FROM questions "
        "WHERE split = 'evaluation' ORDER BY question_uid").fetchall()
    gold_rows = con.execute("""
        SELECT g.question_uid, g.evidence_id, e.type
        FROM question_gold_evidence g
        JOIN canonical_evidence e ON e.evidence_id = g.evidence_id
        JOIN questions q          ON q.question_uid = g.question_uid
        WHERE q.split = 'evaluation' AND g.setting = '20'
    """).fetchall()
    con.close()

    gold = collections.defaultdict(list)
    for quid, eid, etype in gold_rows:
        gold[quid].append((eid, "text" if etype == "text" else "visual"))

    by_doc = collections.OrderedDict()
    for eid, doc, etype, text, desc in ev:
        by_doc.setdefault(doc, []).append(
            (eid, normalize(surrogate(etype, text, desc, "", repr_mode))))
    idx = {d: {"eids": [e for e, _ in v],
               "bm25": BM25([tokenize(b) for _, b in v])}
           for d, v in by_doc.items()}

    P, Q = load_dense(repr_mode)
    p_vecs, p_docs, p_eids = P["vecs"], P["docs"], P["eids"]
    q_vec = {str(u): v for u, v in zip(Q["quids"], Q["vecs"])}
    dvec, deid = collections.defaultdict(list), collections.defaultdict(list)
    for i, doc in enumerate(p_docs):
        dvec[str(doc)].append(i)
        deid[str(doc)].append(str(p_eids[i]))

    rows = []
    for quid, doc, question, q_id in qs:
        if quid not in gold or doc not in idx:
            continue
        eids = idx[doc]["eids"]
        qt = tokenize((question or "").lower())
        order, bs = idx[doc]["bm25"].rank(qt)
        r_bm = [eids[i] for i in order]
        sel = np.asarray(dvec[doc])
        sims = p_vecs[sel] @ q_vec[quid]
        d_order = np.lexsort((np.arange(len(sel)), -sims))
        r_dn = [deid[doc][i] for i in d_order]

        fused = collections.defaultdict(float)
        for lst in (r_bm, r_dn):
            for r, e in enumerate(lst):
                fused[e] += 1.0 / (RRF_C + r + 1)
        r_rrf = sorted(fused, key=lambda e: -fused[e])

        gset = {e for e, _ in gold[quid]}
        rec = {"bm25": len(gset & set(r_bm[:k])) / len(gset),
               "dense": len(gset & set(r_dn[:k])) / len(gset),
               "rrf": len(gset & set(r_rrf[:k])) / len(gset)}

        bs_sorted = np.sort(bs)[::-1]
        ds_sorted = np.sort(sims)[::-1]
        n = len(eids)
        top = min(10, n)
        overlap = len(set(r_bm[:top]) & set(r_dn[:top])) / top
        # Score-shape features. Everything here is computable at query time
        # from the two first-pass rankings, with no access to gold.
        scores = [
            float(bs_sorted[0]), float(bs_sorted[:5].mean()), float(bs.mean()),
            float(bs.std()), float(bs_sorted[0] - bs.mean()),
            float(ds_sorted[0]), float(ds_sorted[:5].mean()), float(sims.mean()),
            float(sims.std()), float(ds_sorted[0] - sims.mean()),
            overlap,
        ]
        n_vis = sum(1 for _, kd in gold[quid] if kd == "visual")
        shape = [float(n), float(np.log1p(n)), float(len(qt))]
        rows.append({"quid": quid, "doc": doc, "q_id": q_id,
                     "scores": scores, "shape": shape,
                     "visual_share": n_vis / len(gold[quid]), **rec})
    return rows


def feature_matrix(rows, groups):
    parts = []
    names = []
    if "emb" in groups:
        z = np.load(FEATURES_NPZ, allow_pickle=True)
        lut = {int(q): i for i, q in enumerate(z["q_ids"])}
        emb = z["emb"]
        parts.append(np.asarray([emb[lut[int(r["q_id"])]] for r in rows]))
        names += [f"emb{i}" for i in range(emb.shape[1])]
    if "scores" in groups:
        parts.append(np.asarray([r["scores"] for r in rows]))
        names += ["bm_top1", "bm_top5", "bm_mean", "bm_std", "bm_gap",
                  "dn_top1", "dn_top5", "dn_mean", "dn_std", "dn_gap",
                  "top10_overlap"]
    if "shape" in groups:
        parts.append(np.asarray([r["shape"] for r in rows]))
        names += ["n_cand", "log_n_cand", "q_len"]
    return np.hstack(parts), names


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
    ap.add_argument("--split", default=DEFAULT_SPLIT)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--features", default="all",
                    choices=("emb", "scores", "shape", "scores+shape", "all"))
    args = ap.parse_args()
    groups = {"all": ("emb", "scores", "shape"),
              "scores+shape": ("scores", "shape")}.get(
                  args.features, (args.features,))

    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.preprocessing import StandardScaler

    rows = build(args.db, args.k)
    split = json.load(open(args.split, encoding="utf-8"))["doc_to_split"]
    sp = np.asarray([split.get(r["doc"], "?") for r in rows])
    tr, te = sp == "train", sp == "test"

    X, names = feature_matrix(rows, groups)
    bm = np.asarray([r["bm25"] for r in rows])
    dn = np.asarray([r["dense"] for r in rows])
    rf = np.asarray([r["rrf"] for r in rows])
    docs = np.asarray([r["doc"] for r in rows])
    regret = dn - bm
    y = (regret > 0).astype(int)
    w = np.abs(regret)

    print("=" * 84)
    print(f"E17 REDONE  target = recall@{args.k}(dense) - recall@{args.k}(bm25)")
    print(f"features: {args.features} -> {X.shape[1]}-d ({len(names)} named)")
    print("=" * 84)
    print(f"train {tr.sum()} q / {len(set(docs[tr]))} docs   "
          f"test {te.sum()} q / {len(set(docs[te]))} docs")
    print(f"queries where the two retrievers TIE: {np.mean(regret == 0):.1%}  "
          f"(they carry no routing decision)")
    print(f"dense wins {np.mean(regret > 0):.1%}, bm25 wins {np.mean(regret < 0):.1%}")
    print(f"mean |regret| among non-ties: "
          f"{w[regret != 0].mean():.3f}")

    nz = tr & (regret != 0)
    sc = StandardScaler().fit(X[nz])
    clf = LogisticRegression(C=0.3, max_iter=4000, random_state=SEED)
    clf.fit(sc.transform(X[nz]), y[nz], sample_weight=w[nz])
    p_te = clf.predict_proba(sc.transform(X[te]))[:, 1]

    te_nz = regret[te] != 0
    auc = (roc_auc_score(y[te][te_nz], p_te[te_nz], sample_weight=w[te][te_nz])
           if te_nz.sum() and len(set(y[te][te_nz])) > 1 else float("nan"))
    print(f"\nregret-weighted test AUC on non-tied queries: {auc:.3f}")

    routed = np.where(p_te > 0.5, dn[te], bm[te])
    oracle = np.maximum(bm[te], dn[te])
    fixed_is_dense = dn[tr].mean() > bm[tr].mean()
    fixed = dn[te] if fixed_is_dense else bm[te]
    fixed_name = "dense" if fixed_is_dense else "bm25"
    d_te = docs[te]
    rng = np.random.default_rng(SEED)

    print()
    print(f"{'policy':<40}{'recall@' + str(args.k):>12}{'retrievers':>13}")
    print("-" * 84)
    for label, v, cost in (
            ("always bm25", bm[te], 1), ("always dense", dn[te], 1),
            (f"best fixed ({fixed_name}, chosen on train)", fixed, 1),
            ("ROUTED by predicted outcome", routed, 1),
            ("static RRF (the standing baseline)", rf[te], 2),
            ("ORACLE retriever choice", oracle, "-")):
        print(f"{label:<40}{v.mean():>12.4f}{str(cost):>13}")
    print("-" * 84)

    print(f"\n{'comparison':<40}{'delta':>10}{'doc-cluster 95% CI':>26}")
    for label, a, b in (("routed - best fixed", routed, fixed),
                        ("routed - static RRF", routed, rf[te]),
                        ("oracle - best fixed", oracle, fixed),
                        ("static RRF - best fixed", rf[te], fixed),
                        ("oracle - static RRF", oracle, rf[te])):
        d, lo, hi = cluster_ci(a - b, d_te, rng)
        star = "*" if (lo > 0 or hi < 0) else " "
        print(f"{label:<40}{d:>+10.4f}"
              f"{'[' + format(lo, '+.4f') + ',' + format(hi, '+.4f') + ']' + star:>26}")

    head = oracle.mean() - fixed.mean()
    if head > 1e-9:
        print(f"\nrouter captures {(routed.mean() - fixed.mean()) / head:.0%} "
              f"of the oracle headroom over the best fixed retriever")
    print("\nEXPLORATORY. Split observed repeatedly across E1-E28.")


if __name__ == "__main__":
    main()
