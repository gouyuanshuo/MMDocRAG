"""Adaptive modality budget: how should k evidence slots be split text vs image?

This is RQ1b in its surviving form. Binary retriever routing failed for a
structural reason -- 61.9% of questions need text *and* visual gold, so choosing
one path cannot serve them -- but the allocation question is well posed for
exactly those questions. MMDocRAG allocates by a fixed quota that never varies
(20 -> 12 text + 8 image); a purely visual question and a text-heavy one plainly
deserve different splits.

Setup. Rank text quotes and image quotes separately within the question's
document, then take the top a text and top (k-a) image. Only `a` varies. The
same retriever scores both lists, so the allocation is the single variable under
test; a variant using the best retriever per modality is reported separately
because it changes two things at once.

Baselines, in increasing order of what they are allowed to know:

    paper quota      12/8 at k=20, fixed for every query
    best fixed       the single best `a` found on train -- a stronger baseline
                     than the paper quota and the one that actually has to be beaten
    predicted mix    `a` chosen from the question's predicted gold modality mix
    ORACLE           the best `a` for each query, known only after the fact

and the control that Phase 1A.5's L1 demands:

    PERMUTED ORACLE  each query is given some *other* query's optimal split.
                     If per-query allocation is real structure this collapses
                     toward the fixed baselines; if it stays near the oracle,
                     the oracle was reading the shape of the recall curve rather
                     than anything about the query.

Run:
    python -m retrieval.budget_alloc
    python -m retrieval.budget_alloc --k 15
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
from sklearn.preprocessing import StandardScaler      # noqa: E402

from retrieval.bm25 import BM25                       # noqa: E402
from retrieval.corpus import normalize, tokenize      # noqa: E402
from retrieval.dense import load as load_dense        # noqa: E402
from retrieval.eval_quote_recall import surrogate     # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO_ROOT, "canonical", "mmdocrag.sqlite")
DEFAULT_SPLIT = os.path.join(REPO_ROOT, "manifests", "split_doc_disjoint.json")
SEED = 20260825
# The quotas MMDocRAG uses, as text/image at each total budget.
PAPER_QUOTA = {10: (7, 3), 15: (10, 5), 20: (12, 8)}


QUOTES_DB = os.path.join(REPO_ROOT, "retrieval", "quotes.sqlite")
CACHE = os.path.join(REPO_ROOT, "retrieval", "budget_rows.pkl")


def build_selfbuilt(db_path, quotes_db=QUOTES_DB):
    """Same experiment on the realistic-scale self-built text pool.

    Text units are the 92,752 chunks retrieval/quote_corpus.py built from the
    PDFs (422/doc against the paper's 536); gold text is carried over by the
    8-gram map at 96.9%. Image units stay the official quotes with their VLM
    descriptions, so the two pools bracket the true 8.5:1 text:image ratio from
    either side -- canonical at 3.2:1, this one at 14.3:1. A conclusion that
    holds on both is not an artefact of pool composition.

    BM25 only: E19's headline holds the retriever fixed, so no embeddings are
    needed and the whole comparison runs on CPU.
    """
    con = sqlite3.connect(db_path)
    imgs = con.execute(
        "SELECT evidence_id, doc_name, img_description FROM canonical_evidence "
        "WHERE type <> 'text' ORDER BY doc_name, evidence_id").fetchall()
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

    qc = sqlite3.connect(quotes_db)
    chunks = collections.OrderedDict()
    for cid, doc, text in qc.execute(
            "SELECT chunk_id, doc_name, text FROM chunks ORDER BY doc_name, page_id, idx"):
        chunks.setdefault(doc, []).append((cid, text))
    gmap = {e: c for e, c in qc.execute(
        "SELECT evidence_id, chunk_id FROM gold_map WHERE chunk_id IS NOT NULL")}
    qc.close()

    img_by_doc = collections.OrderedDict()
    for eid, doc, desc in imgs:
        img_by_doc.setdefault(doc, []).append((eid, normalize(desc or "")))

    # Gold in the new id space: text evidence becomes its mapped chunk, image
    # evidence keeps its own id. Text gold with no mapping is dropped and counted.
    gold, dropped = collections.defaultdict(lambda: {"text": set(), "visual": set()}), 0
    for quid, eid, etype in gold_rows:
        if etype == "text":
            cid = gmap.get(eid)
            if cid is None:
                dropped += 1
                continue
            gold[quid]["text"].add(cid)
        else:
            gold[quid]["visual"].add(eid)
    print(f"[selfbuilt] text pool {sum(len(v) for v in chunks.values())} chunks / "
          f"{len(chunks)} docs, image pool {len(imgs)}")
    print(f"[selfbuilt] gold text evidence with no chunk mapping, dropped: {dropped}")

    idx = {}
    for doc in chunks:
        idx[doc] = {
            "text": (BM25([tokenize(t) for _, t in chunks[doc]]),
                     [c for c, _ in chunks[doc]]),
            "visual": (BM25([tokenize(t) for _, t in img_by_doc.get(doc, [])]),
                       [e for e, _ in img_by_doc.get(doc, [])])
            if img_by_doc.get(doc) else None,
        }

    rows = []
    for quid, doc, question, q_id in qs:
        if doc not in idx or quid not in gold:
            continue
        g = gold[quid]
        gset = g["text"] | g["visual"]
        if not gset:
            continue
        qt = tokenize((question or "").lower())
        ranked = {"bm25": {}, "dense": {}}
        scores = {"text": (0.0, 0.0, 0.0), "visual": (0.0, 0.0, 0.0)}
        for k in ("text", "visual"):
            entry = idx[doc][k]
            if entry is None:
                ranked["bm25"][k] = ranked["dense"][k] = []
                continue
            bm, ids = entry
            order, sc = bm.rank(qt)
            ranked["bm25"][k] = [ids[i] for i in order]
            ranked["dense"][k] = ranked["bm25"][k]      # no dense arm in this pool
            top = sc[order[:5]]
            scores[k] = (float(top[0]) if len(top) else 0.0,
                         float(top.mean()) if len(top) else 0.0,
                         float(sc.mean()) if len(sc) else 0.0)
        rows.append({"quid": quid, "q_id": q_id, "gold": gset,
                     "visual_share": len(g["visual"]) / len(gset),
                     "rank": ranked, "scores": scores})
    return rows


def build_cached(db_path, repr_mode="vlm", cache=CACHE, pool="canonical"):
    """build() takes ~4 minutes; every policy variant re-reads the same rows."""
    import pickle
    cache = cache.replace(".pkl", f"_{pool}.pkl")
    if os.path.exists(cache):
        with open(cache, "rb") as fh:
            return pickle.load(fh)
    rows = build_selfbuilt(db_path) if pool == "selfbuilt" else build(db_path, repr_mode)
    with open(cache, "wb") as fh:
        pickle.dump(rows, fh)
    return rows


def build(db_path, repr_mode="vlm"):
    """Per query: separately ranked text and image quote lists, plus gold."""
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

    pools = collections.OrderedDict()
    for eid, doc, etype, text, desc in ev:
        k = "text" if etype == "text" else "visual"
        pools.setdefault(doc, {"text": [], "visual": []})[k].append(
            (eid, normalize(surrogate(etype, text, desc, "", repr_mode))))

    lex = {}
    for doc, pool in pools.items():
        lex[doc] = {k: (BM25([tokenize(b) for _, b in items]),
                        [e for e, _ in items]) if items else None
                    for k, items in pool.items()}

    P, Q = load_dense(repr_mode)
    p_vecs, p_docs, p_eids, p_types = P["vecs"], P["docs"], P["eids"], P["types"]
    q_vec = {str(u): v for u, v in zip(Q["quids"], Q["vecs"])}
    drow = collections.defaultdict(lambda: {"text": [], "visual": []})
    for i, doc in enumerate(p_docs):
        k = "text" if str(p_types[i]) == "text" else "visual"
        drow[str(doc)][k].append(i)

    rows = []
    for quid, doc, question, q_id in qs:
        if quid not in gold or doc not in lex:
            continue
        qt = tokenize((question or "").lower())
        ranked = {"bm25": {}, "dense": {}}
        scores = {"text": (0.0, 0.0, 0.0), "visual": (0.0, 0.0, 0.0)}
        for k in ("text", "visual"):
            entry = lex[doc][k]
            if entry is None:
                ranked["bm25"][k], ranked["dense"][k] = [], []
                continue
            bm, eids = entry
            order, sc = bm.rank(qt)
            ranked["bm25"][k] = [eids[i] for i in order]
            top = sc[order[:5]]
            scores[k] = (float(top[0]) if len(top) else 0.0,
                         float(top.mean()) if len(top) else 0.0,
                         float(sc.mean()) if len(sc) else 0.0)

            rowsel = np.asarray(drow[doc][k])
            sims = p_vecs[rowsel] @ q_vec[quid]
            ordd = np.lexsort((np.arange(len(rowsel)), -sims))
            ranked["dense"][k] = [str(p_eids[rowsel[i]]) for i in ordd]

        gset = {e for e, _ in gold[quid]}
        n_vis = sum(1 for _, kd in gold[quid] if kd == "visual")
        rows.append({"quid": quid, "q_id": q_id, "gold": gset,
                     "visual_share": n_vis / len(gold[quid]),
                     "rank": ranked, "scores": scores})
    return rows


def recall_at_split(row, a, k, retriever="bm25", mix=None):
    """Top `a` text quotes + top `k-a` image quotes; fraction of gold covered."""
    r = row["rank"]
    if mix:  # per-modality retriever choice
        got = set(r[mix["text"]]["text"][:a]) | set(r[mix["visual"]]["visual"][:k - a])
    else:
        got = set(r[retriever]["text"][:a]) | set(r[retriever]["visual"][:k - a])
    return len(row["gold"] & got) / len(row["gold"])


def curve(rows, k, **kw):
    """recall for every split a = 0..k, as an (n_rows, k+1) array."""
    return np.asarray([[recall_at_split(r, a, k, **kw) for a in range(k + 1)]
                       for r in rows])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--split", default=DEFAULT_SPLIT)
    ap.add_argument("--k", type=int, default=20, help="total evidence budget")
    ap.add_argument("--pool", default="canonical", choices=("canonical", "selfbuilt"),
                    help="canonical = the questions' candidate union (3.2:1 "
                         "text:image); selfbuilt = the PDF-derived text corpus "
                         "(14.3:1). The true pool is 8.5:1, so they bracket it")
    ap.add_argument("--target", default="mostly", choices=("mostly", "pure"),
                    help="mostly = gold is >=50%% visual; pure = gold is 100%% "
                         "visual. `pure` is the better-balanced and more "
                         "actionable cut: the oracle gives all slots to images "
                         "for 46%% of queries, which is what that flag marks")
    ap.add_argument("--features", default="both", choices=("emb", "scores", "both"),
                    help="emb = question text only; scores = first-pass retrieval "
                         "score summaries; both = concatenated")
    args = ap.parse_args()
    k = args.k

    rows = build_cached(args.db, pool=args.pool)
    print(f"{len(rows)} questions, budget k = {k}\n")

    with open(args.split, encoding="utf-8") as fh:
        assign = json.load(fh)["q_id_to_split"]
    sp = np.asarray([assign[str(r["q_id"])] for r in rows])
    tr, va, te = sp == "train", sp == "val", sp == "test"

    C = curve(rows, k)                       # BM25 for both modalities
    Cmix = curve(rows, k, mix={"text": "dense", "visual": "bm25"})
    vis = np.asarray([r["visual_share"] for r in rows])

    print("=" * 84)
    print("1. THE ALLOCATION CURVE  (mean recall by number of text slots)")
    print("=" * 84)
    show = sorted({0, 2, 4, 6, 8, 10, 12, 14, 16, 18, k} & set(range(k + 1)))
    print(f"{'text slots a':<16}" + "".join(f"{a:>7}" for a in show))
    print(f"{'image slots':<16}" + "".join(f"{k - a:>7}" for a in show))
    print("-" * 84)
    print(f"{'mean recall':<16}" + "".join(f"{C[:, a].mean():>7.3f}" for a in show))
    best_a_all = int(np.argmax(C.mean(axis=0)))
    print(f"\nbest fixed split over the whole set: {best_a_all} text / "
          f"{k - best_a_all} image  ->  {C[:, best_a_all].mean():.3f}")
    if k in PAPER_QUOTA:
        pa = PAPER_QUOTA[k][0]
        print(f"MMDocRAG quota                    : {pa} text / {k - pa} image  ->  "
              f"{C[:, pa].mean():.3f}")

    print()
    print("=" * 84)
    print("2. IS THE OPTIMAL SPLIT QUERY-SPECIFIC?  (oracle vs permuted control)")
    print("=" * 84)
    rng = np.random.default_rng(SEED)
    opt = C.argmax(axis=1)
    oracle = C[np.arange(len(C)), opt].mean()
    perm = rng.permutation(len(C))
    permuted = C[np.arange(len(C)), opt[perm]].mean()
    fixed = C[:, best_a_all].mean()
    print(f"{'policy':<34}{'recall':>10}")
    print("-" * 84)
    print(f"{'best fixed split (a=' + str(best_a_all) + ')':<34}{fixed:>10.3f}")
    print(f"{'PERMUTED oracle (control)':<34}{permuted:>10.3f}")
    print(f"{'ORACLE per-query split':<34}{oracle:>10.3f}")
    print("-" * 84)
    print(f"{'apparent headroom':<34}{oracle - fixed:>+10.3f}")
    print(f"{'generic (permuted - fixed)':<34}{permuted - fixed:>+10.3f}")
    print(f"{'query-specific (oracle - permuted)':<34}{oracle - permuted:>+10.3f}")
    print(f"\noptimal split distribution: "
          + ", ".join(f"a={a}:{c}" for a, c in
                      sorted(collections.Counter(opt).items())[:8]) + " ...")

    print()
    print("=" * 84)
    print("3. LEARNED ALLOCATION  (document-disjoint test)")
    print("=" * 84)
    z = np.load(os.path.join(REPO_ROOT, "router", "features_20.npz"), allow_pickle=True)
    feat = {int(q): z["emb"][i] for i, q in enumerate(z["q_ids"])}
    E = np.asarray([feat[r["q_id"]] for r in rows])

    # First-pass retrieval scores. Available at inference time and, unlike the
    # question text, they are evidence about *this* document's pool: if the
    # image list scores far above the text list, the answer probably lives in a
    # figure. This is the observable signal the generation layer had no
    # analogue of -- there, nothing measurable correlated with the outcome.
    def score_feats(r):
        t, v = r["scores"]["text"], r["scores"]["visual"]
        eps = 1e-6
        return [t[0], t[1], t[2], v[0], v[1], v[2],
                v[0] - t[0], v[1] - t[1],
                v[0] / (t[0] + eps), v[1] / (t[1] + eps),
                (v[0] - t[0]) / (v[0] + t[0] + eps)]
    S = np.asarray([score_feats(r) for r in rows], dtype=np.float64)
    X = {"emb": E, "scores": S, "both": np.hstack([E, S])}[args.features]
    print(f"features: {args.features}  ->  {X.shape[1]} dims")
    print()

    # Predict the gold modality mix, then map the prediction to a split learned
    # on train. Mapping through the mix rather than regressing `a` directly keeps
    # the policy interpretable and stops it fitting the recall curve's shape.
    y = (vis >= 1.0) if args.target == "pure" else (vis >= 0.5)
    sc = StandardScaler().fit(X[tr])
    clf = LogisticRegression(C=0.3, max_iter=2000, random_state=SEED)
    clf.fit(sc.transform(X[tr]), y[tr])
    p_tr = clf.predict_proba(sc.transform(X[tr]))[:, 1]
    p_te = clf.predict_proba(sc.transform(X[te]))[:, 1]
    from sklearn.metrics import roc_auc_score
    print(f"predicting 'gold is {args.target} visual': test AUC = "
          f"{roc_auc_score(y[te], p_te):.3f}  (base rate {y.mean():.2f})")

    edges = np.quantile(p_tr, [0.25, 0.5, 0.75])
    bin_tr, bin_te = np.digitize(p_tr, edges), np.digitize(p_te, edges)
    best_by_bin = {b: int(np.argmax(C[tr][bin_tr == b].mean(axis=0)))
                   for b in range(4) if (bin_tr == b).sum()}
    print("learned mapping, predicted-visual quartile -> text slots:")
    for b, a in sorted(best_by_bin.items()):
        print(f"  Q{b + 1}  a = {a} text / {k - a} image   "
              f"(n_train {(bin_tr == b).sum()})")

    a_te = np.asarray([best_by_bin.get(b, best_a_all) for b in bin_te])
    learned = C[te][np.arange(te.sum()), a_te].mean()
    best_a_tr = int(np.argmax(C[tr].mean(axis=0)))
    print()
    print(f"{'policy':<34}{'recall':>10}{'vs best fixed':>16}")
    print("-" * 84)
    if k in PAPER_QUOTA:
        print(f"{'MMDocRAG quota (' + str(PAPER_QUOTA[k][0]) + '/' + str(PAPER_QUOTA[k][1]) + ')':<34}"
              f"{C[te][:, PAPER_QUOTA[k][0]].mean():>10.3f}"
              f"{C[te][:, PAPER_QUOTA[k][0]].mean() - C[te][:, best_a_tr].mean():>+16.3f}")
    print(f"{'best fixed (a=' + str(best_a_tr) + ', on train)':<34}"
          f"{C[te][:, best_a_tr].mean():>10.3f}{0.0:>+16.3f}")
    print(f"{'LEARNED allocation':<34}{learned:>10.3f}"
          f"{learned - C[te][:, best_a_tr].mean():>+16.3f}")
    print(f"{'ORACLE per-query':<34}"
          f"{C[te][np.arange(te.sum()), C[te].argmax(axis=1)].mean():>10.3f}")
    # ---- 4. direct policy: skip the intermediate label entirely ----
    print()
    print("=" * 84)
    print("4. DIRECT ALLOCATION POLICY  (regress the recall curve, take argmax)")
    print("=" * 84)
    print("The two-stage policy above predicts a modality label, then looks up a")
    print("split per quantile bin. That pipeline is lossy: across six settings its")
    print("AUC and its allocation gain move in opposite directions, so a better")
    print("label does not buy a better split. This fits what we actually want")
    print("instead -- for each query, the recall each of the k+1 splits would")
    print("achieve -- and picks the argmax. Same features, same split, no")
    print("intermediate objective.")
    print()
    from sklearn.linear_model import Ridge
    from sklearn.metrics import roc_auc_score  # noqa: F811
    for alpha in (1.0, 10.0, 100.0):
        rg = Ridge(alpha=alpha).fit(sc.transform(X[tr]), C[tr])
        pred = rg.predict(sc.transform(X[te]))
        a_hat = pred.argmax(axis=1)
        got = C[te][np.arange(te.sum()), a_hat].mean()
        # how well the predicted curve tracks the real one, per query
        corr = np.mean([np.corrcoef(pred[i], C[te][i])[0, 1]
                        for i in range(len(pred))
                        if C[te][i].std() > 1e-9])
        print(f"  ridge alpha={alpha:<6} recall {got:.3f}   "
              f"vs best fixed {got - C[te][:, best_a_tr].mean():+.3f}   "
              f"mean curve corr {corr:+.3f}   "
              f"mean chosen a {a_hat.mean():.1f}")
    print()
    print(f"{'reference':<34}{'recall':>10}")
    print("-" * 84)
    print(f"{'best fixed (a=' + str(best_a_tr) + ')':<34}{C[te][:, best_a_tr].mean():>10.3f}")
    print(f"{'ORACLE per-query':<34}"
          f"{C[te][np.arange(te.sum()), C[te].argmax(axis=1)].mean():>10.3f}")

    # ---- 5. is any of that correlation query-specific, and is it usable? ----
    print()
    print("=" * 84)
    print("5. IS THE SIGNAL QUERY-SPECIFIC, AND CAN SHRINKAGE USE IT?")
    print("=" * 84)
    rg = Ridge(alpha=100.0).fit(sc.transform(X[tr]), C[tr])
    pred = rg.predict(sc.transform(X[te]))
    mean_tr = C[tr].mean(axis=0)

    # A curve correlation of +0.54 is not evidence of per-query knowledge: every
    # curve rises then falls, so predicting the average shape already scores
    # well. Subtracting the mean curve from both sides leaves only the part that
    # differs between queries -- the only part a router could act on.
    ra = C[te] - mean_tr
    rp = pred - pred.mean(axis=0)
    res_corr = np.mean([np.corrcoef(rp[i], ra[i])[0, 1] for i in range(len(rp))
                        if ra[i].std() > 1e-9 and rp[i].std() > 1e-9])
    raw_corr = np.mean([np.corrcoef(pred[i], C[te][i])[0, 1] for i in range(len(pred))
                        if C[te][i].std() > 1e-9])
    print(f"raw curve correlation            : {raw_corr:+.3f}")
    print(f"after removing the average curve : {res_corr:+.3f}   "
          f"<- the query-specific part")

    # The recall curve is flat near its peak, so argmax of a noisy prediction can
    # land well off it and lose more than it gains. Shrinking the predicted split
    # toward the fixed optimum trades that variance away; if even a small step
    # away from fixed helps, some signal is usable.
    print()
    # lambda is a hyperparameter, so it is chosen on val and only then applied
    # to test. Reading the sweep off test and reporting its peak would be
    # selecting on the evaluation set.
    pred_va = rg.predict(sc.transform(X[va]))
    a_pred_va = pred_va.argmax(axis=1).astype(float)
    a_pred_te = pred.argmax(axis=1).astype(float)
    lams = (0.0, 0.1, 0.25, 0.5, 0.75, 1.0)

    def mix(a_pred_arr, lam):
        return np.clip(np.rint((1 - lam) * best_a_tr + lam * a_pred_arr), 0, k).astype(int)

    print(f"{'lambda':<10}{'val recall':>13}{'test recall':>14}"
          f"{'test vs fixed':>16}{'chosen a sd':>14}")
    print("-" * 84)
    val_scores = {}
    for lam in lams:
        gv = C[va][np.arange(va.sum()), mix(a_pred_va, lam)].mean()
        a_te = mix(a_pred_te, lam)
        gt = C[te][np.arange(te.sum()), a_te].mean()
        val_scores[lam] = gv
        print(f"{lam:<10.2f}{gv:>13.3f}{gt:>14.3f}"
              f"{gt - C[te][:, best_a_tr].mean():>+16.3f}{a_te.std():>14.1f}")
    print("-" * 84)
    best_lam = max(val_scores, key=val_scores.get)
    a_te = mix(a_pred_te, best_lam)
    got = C[te][np.arange(te.sum()), a_te].mean()
    fixed_te = C[te][:, best_a_tr].mean()
    orc_te = C[te][np.arange(te.sum()), C[te].argmax(axis=1)].mean()
    print(f"lambda selected on val: {best_lam}")
    print(f"  test recall {got:.3f}  vs fixed {got - fixed_te:+.3f}  "
          f"= {(got - fixed_te) / (orc_te - fixed_te):.0%} of the oracle headroom")
    print("lambda=0 is the fixed split; lambda=1 is the raw argmax policy.")

    print()
    print("-" * 84)
    print(f"best per-modality retriever (dense text / bm25 image), best fixed split: "
          f"{Cmix[te].mean(axis=0).max():.3f}")
    print("that row changes retriever and allocation at once, so it is reported "
          "as a variant rather than\nas the headline -- the headline holds the "
          "retriever fixed so allocation is the only variable.")


if __name__ == "__main__":
    main()
