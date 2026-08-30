"""Is retriever routing learnable, and is its headroom real?

The retriever comparison produced a clean sign flip at quote granularity: dense
beats BM25 on text gold by about +0.09 recall@10, BM25 beats dense on image gold
by about -0.08, and RRF fusion beats neither despite paying for both. Neither
retriever dominates, which is the condition RQ2 needs.

Phase 1A.5 taught the discipline that has to follow: a per-query oracle gain is
not by itself evidence of routable structure. So this measures three things in
order.

  1. HEADROOM, with a control. The oracle picks the better retriever per query.
     The control runs the same oracle over two BM25 variants that differ only in
     length normalisation -- systems that should share most of their failures.
     Whatever the real pair achieves above that control is complementarity that
     is specific to the retrievers rather than generic to taking a maximum.

     Unlike Phase 1A.5 the outcome here is deterministic -- a retriever that
     misses a query misses it every time, there is no sampling noise to select
     on -- so a gain over the control is structural by construction. The control
     is reported anyway, because that claim should be shown rather than asserted.

  2. IS THE LABEL PREDICTABLE? The mechanism is visible: which retriever wins
     tracks the modality of the gold evidence. A router cannot see gold, but it
     can try to predict it from the question. That is a far more promising
     target than Phase 1A.5's, and it is tested with the identical pipeline --
     BGE question embedding, logistic regression, document-disjoint split.

  3. DOES THE CHAIN HOLD END TO END? Route by predicted modality, pick the
     retriever, measure achieved recall against best-fixed, RRF and the oracle.

Run:
    python -m retrieval.route_headroom
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

from sklearn.linear_model import LogisticRegression   # noqa: E402
from sklearn.metrics import roc_auc_score             # noqa: E402
from sklearn.preprocessing import StandardScaler      # noqa: E402

from retrieval.bm25 import BM25                       # noqa: E402
from retrieval.corpus import normalize, tokenize      # noqa: E402
from retrieval.dense import load as load_dense        # noqa: E402
from retrieval.eval_quote_recall import surrogate     # noqa: E402
from retrieval.eval_retrievers import rrf             # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO_ROOT, "canonical", "mmdocrag.sqlite")
DEFAULT_SPLIT = os.path.join(REPO_ROOT, "manifests", "split_doc_disjoint.json")
K = 10
SEED = 20260825


def per_query_recall(db_path, repr_mode, k=K):
    """recall@k per query for each retriever, plus the gold-modality mix."""
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

    idx = {}
    for doc, items in by_doc.items():
        toks = [tokenize(b) for _, b in items]
        idx[doc] = {
            "eids": [e for e, _ in items],
            "bm25": BM25(toks),
            # Control arm: same lexical retriever, length normalisation off.
            # It shares BM25's vocabulary and most of its failures, so it bounds
            # how much oracle gain comes from merely taking a maximum.
            "bm25_b0": BM25(toks, b=0.0),
        }

    P, Q = load_dense(repr_mode)
    # np.load on a compressed npz returns a lazy NpzFile: every P["vecs"]
    # access decompresses the whole 36 MB array again. Pull the arrays out
    # once -- reading them inside the per-question loop turned a seconds-long
    # job into an unbounded one.
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
        rank = {}
        for name in ("bm25", "bm25_b0"):
            order, _ = idx[doc][name].rank(qt)
            rank[name] = [eids[i] for i in order]
        rowsel = np.asarray(dvec[doc])
        sims = p_vecs[rowsel] @ q_vec[quid]
        rank["dense"] = [deid[doc][i]
                         for i in np.lexsort((np.arange(len(rowsel)), -sims))]
        fused = rrf([rank["bm25"], rank["dense"]])
        rank["rrf"] = sorted(fused, key=lambda e: -fused[e])

        gset = {e for e, _ in gold[quid]}
        n_vis = sum(1 for _, kd in gold[quid] if kd == "visual")
        rec = {m: len(gset & set(rank[m][:k])) / len(gset) for m in rank}
        rows.append({"quid": quid, "doc": doc, "q_id": q_id, "question": question,
                     "visual_share": n_vis / len(gold[quid]), **rec})
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--split", default=DEFAULT_SPLIT)
    ap.add_argument("--image-repr", dest="repr", default="vlm")
    args = ap.parse_args()

    rows = per_query_recall(args.db, args.repr)
    print(f"{len(rows)} questions scored at recall@{K}\n")

    bm = np.asarray([r["bm25"] for r in rows])
    dn = np.asarray([r["dense"] for r in rows])
    b0 = np.asarray([r["bm25_b0"] for r in rows])
    rf = np.asarray([r["rrf"] for r in rows])
    vis = np.asarray([r["visual_share"] for r in rows])

    print("=" * 84)
    print("1. HEADROOM, AGAINST A CONTROL")
    print("=" * 84)
    real_best = max(bm.mean(), dn.mean())
    real_orc = np.maximum(bm, dn).mean()
    ctl_best = max(bm.mean(), b0.mean())
    ctl_orc = np.maximum(bm, b0).mean()
    print(f"{'pair':<28}{'best fixed':>12}{'oracle':>10}{'gain':>9}")
    print("-" * 84)
    print(f"{'bm25 + dense (real)':<28}{real_best:>12.3f}{real_orc:>10.3f}"
          f"{real_orc - real_best:>+9.3f}")
    print(f"{'bm25 + bm25(b=0) (control)':<28}{ctl_best:>12.3f}{ctl_orc:>10.3f}"
          f"{ctl_orc - ctl_best:>+9.3f}")
    print("-" * 84)
    print(f"{'excess over control':<28}{'':>12}{'':>10}"
          f"{(real_orc - real_best) - (ctl_orc - ctl_best):>+9.3f}")
    print(f"\nRRF (pays for both retrievers): {rf.mean():.3f}   "
          f"vs best fixed {real_best:.3f}   vs oracle {real_orc:.3f}")

    print()
    print("=" * 84)
    print("2. IS THE LABEL PREDICTABLE FROM THE QUESTION?")
    print("=" * 84)
    # Mechanism check first: does gold modality actually track the winner?
    mostly_visual = vis >= 0.5
    print(f"{'gold mix':<28}{'n':>7}{'bm25':>9}{'dense':>9}{'dense-bm25':>12}")
    print("-" * 84)
    for lab, m in (("mostly visual", mostly_visual), ("mostly text", ~mostly_visual)):
        print(f"{lab:<28}{m.sum():>7}{bm[m].mean():>9.3f}{dn[m].mean():>9.3f}"
              f"{dn[m].mean() - bm[m].mean():>+12.3f}")
    print("-" * 84)

    # Now: can that mix be predicted from the question alone?
    z = np.load(os.path.join(REPO_ROOT, "router", "features_20.npz"), allow_pickle=True)
    feat = {int(q): z["emb"][i] for i, q in enumerate(z["q_ids"])}
    with open(args.split, encoding="utf-8") as fh:
        assign = json.load(fh)["q_id_to_split"]
    X = np.asarray([feat[r["q_id"]] for r in rows])
    sp = np.asarray([assign[str(r["q_id"])] for r in rows])
    tr, te = sp == "train", sp == "test"

    sc = StandardScaler().fit(X[tr])
    clf = LogisticRegression(C=0.3, max_iter=2000, random_state=SEED)
    clf.fit(sc.transform(X[tr]), mostly_visual[tr])
    p_te = clf.predict_proba(sc.transform(X[te]))[:, 1]
    auc = roc_auc_score(mostly_visual[te], p_te)
    print(f"predicting 'gold is mostly visual' from the question embedding:")
    print(f"  document-disjoint test AUC = {auc:.3f}   "
          f"(base rate {mostly_visual.mean():.2f}, n_test {te.sum()})")

    print()
    print("=" * 84)
    print("3. END TO END: route by predicted modality")
    print("=" * 84)
    pred_vis = p_te > 0.5
    routed = np.where(pred_vis, bm[te], dn[te])
    orc_te = np.maximum(bm[te], dn[te])
    fixed_te = bm[te] if bm[tr].mean() > dn[tr].mean() else dn[te]
    fixed_name = "bm25" if bm[tr].mean() > dn[tr].mean() else "dense"
    print(f"{'policy':<34}{'recall@' + str(K):>12}{'cost':>18}")
    print("-" * 84)
    print(f"{'always bm25':<34}{bm[te].mean():>12.3f}{'1 retriever':>18}")
    print(f"{'always dense':<34}{dn[te].mean():>12.3f}{'1 retriever':>18}")
    print(f"{'best fixed (' + fixed_name + ', on train)':<34}{fixed_te.mean():>12.3f}"
          f"{'1 retriever':>18}")
    print(f"{'RRF fusion':<34}{rf[te].mean():>12.3f}{'2 retrievers':>18}")
    print(f"{'ROUTED by predicted modality':<34}{routed.mean():>12.3f}"
          f"{'1 retriever':>18}")
    print(f"{'ORACLE retriever choice':<34}{orc_te.mean():>12.3f}{'-':>18}")
    print("-" * 84)
    head = orc_te.mean() - fixed_te.mean()
    print(f"gain over best fixed : {routed.mean() - fixed_te.mean():+.3f}"
          f"   ({(routed.mean() - fixed_te.mean()) / head:.0%} of the oracle headroom)"
          if head > 1e-9 else "")
    print(f"gain over RRF        : {routed.mean() - rf[te].mean():+.3f}"
          f"   at half the retrieval cost")


if __name__ == "__main__":
    main()
