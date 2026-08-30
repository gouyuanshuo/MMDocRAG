"""Can the published retrieval configuration be beaten, and by how much?

Every adaptive idea this project tested came back negative: modality routing at
the generation input (kappa 0.038 across 19 models), binary retriever routing
(61.9% of questions carry gold in both modalities, so there is nothing to
choose), learned budget allocation (query-specific structure worth +0.179 that
no feature set predicts beyond 0-2%), and granularity (the fine-chunk advantage
is mostly budget quantisation, not ranking).

What survived all of that is unglamorous and static. Two changes, each measured
on its own elsewhere in this project, and neither of them adaptive:

    quota   the paper allocates the 20-slot budget as 12 text + 8 image. The
            best fixed split measured on both pools is 10/10.
    fusion  the paper's Table 6 rows are single retrievers, or a fixed modality
            quota over two. Reciprocal Rank Fusion of a lexical and a dense
            retriever within each modality is a different construction, and E17
            found it beats the best single retriever once the baseline is not
            accidentally told the gold modality.

This script stacks them against the published configuration on one pool with
everything else held fixed, and reports each step's contribution separately, so
a reader can see which half carries the result.

    POOL. The self-built text corpus (92,752 chunks from the 220 PDFs, gold
    carried over by the 8-gram map at 96.9%) plus the official image quotes with
    their VLM descriptions. Absolute recall is therefore not comparable to the
    paper's Table 6 -- the pools differ. Every comparison here holds the pool
    fixed, which is what makes the deltas meaningful.

Run:
    python -m retrieval.eval_stack
    python -m retrieval.eval_stack --k 15
"""

import argparse
import collections
import os
import sqlite3
import sys

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retrieval.bm25 import BM25                       # noqa: E402
from retrieval.corpus import normalize, tokenize      # noqa: E402
from retrieval.dense import load as load_dense        # noqa: E402
from retrieval import dense_chunks                    # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO_ROOT, "canonical", "mmdocrag.sqlite")
DEFAULT_QUOTES = os.path.join(REPO_ROOT, "retrieval", "quotes.sqlite")

PAPER_QUOTA = {10: (7, 3), 15: (10, 5), 20: (12, 8)}
RRF_C = 60
FB_DOCS = 10          # feedback set size for RM3
FB_TERMS = 20         # expansion terms added
ORIG_WEIGHT = 2       # how many times the original query is repeated
BOOTSTRAP = 4000
SEED = 20260825


def rrf(*rankings):
    """Reciprocal Rank Fusion. Scale-free, so no score normalisation to tune."""
    score = collections.defaultdict(float)
    for lst in rankings:
        for r, e in enumerate(lst):
            score[e] += 1.0 / (RRF_C + r + 1)
    return sorted(score, key=lambda e: -score[e])


def rm3(bm, corpus_tokens, qt, fb_docs=FB_DOCS, fb_terms=FB_TERMS,
        orig_weight=ORIG_WEIGHT):
    """RM3-style pseudo-relevance feedback: expand the query from its own top hits.

    Queries in this benchmark are natural-language questions and the evidence is
    financial and technical prose, so the vocabulary gap is the obvious failure
    mode for a lexical retriever. PRF is the classical zero-cost answer to it and
    needs no model, no API and no training -- which is what makes it worth trying
    after every learned component in this project came back flat.

    Expansion terms are scored by collection frequency in the feedback set times
    idf, so a term that is merely common everywhere does not get picked. The
    original query is repeated `orig_weight` times: BM25.scores sums over the
    token list, so repetition is exactly an integer term weight, and anchoring on
    the original query is what keeps PRF from drifting when the top hits are bad.
    """
    order, _ = bm.rank(qt)
    cnt = collections.Counter()
    for i in order[:fb_docs]:
        cnt.update(set(corpus_tokens[int(i)]))
    qset = set(qt)
    cand = [(t, c * bm.idf.get(t, 0.0)) for t, c in cnt.items()
            if t not in qset and len(t) > 2]
    cand.sort(key=lambda x: (-x[1], x[0]))
    return list(qt) * orig_weight + [t for t, _ in cand[:fb_terms]]


def build(db_path, quotes_db, pool="selfbuilt"):
    """Rankings for every retriever on one pool.

    Two pools are supported and the conclusion is only trusted if it holds on
    both, because they mis-state the true text:image ratio in opposite
    directions -- the canonical pool at 3.2:1 and the self-built one at 14.3:1
    against a true 8.5:1. `canonical` is the union of the questions' candidate
    lists, so it is question-conditioned and absolute recall runs optimistic;
    `selfbuilt` is the 92,752 chunks built from the PDFs, which is what a
    deployed system would index.
    """
    con = sqlite3.connect(db_path)
    imgs = con.execute(
        "SELECT evidence_id, doc_name, img_description FROM canonical_evidence "
        "WHERE type <> 'text' ORDER BY doc_name, evidence_id").fetchall()
    qs = con.execute(
        "SELECT question_uid, doc_name, question FROM questions "
        "WHERE split = 'evaluation' ORDER BY question_uid").fetchall()
    gold_rows = con.execute("""
        SELECT g.question_uid, g.evidence_id, e.type
        FROM question_gold_evidence g
        JOIN canonical_evidence e ON e.evidence_id = g.evidence_id
        JOIN questions q          ON q.question_uid = g.question_uid
        WHERE q.split = 'evaluation' AND g.setting = '20'
    """).fetchall()
    con.close()

    P, Q = load_dense("vlm")
    if pool == "selfbuilt":
        qc = sqlite3.connect(quotes_db)
        chunks = collections.OrderedDict()
        for cid, doc, text in qc.execute(
                "SELECT chunk_id, doc_name, text FROM chunks "
                "ORDER BY doc_name, page_id, idx"):
            chunks.setdefault(doc, []).append((cid, text or ""))
        gmap = {e: c for e, c in qc.execute(
            "SELECT evidence_id, chunk_id FROM gold_map "
            "WHERE chunk_id IS NOT NULL")}
        qc.close()
        Z = dense_chunks.load(quotes_db)
        cvec = {str(c): i for i, c in enumerate(Z["cids"])}
        cvecs = Z["vecs"]
    else:
        # canonical: the official text quotes are already the retrieval units,
        # so gold needs no transfer and gmap is the identity.
        con2 = sqlite3.connect(db_path)
        chunks = collections.OrderedDict()
        for eid, doc, text in con2.execute(
                "SELECT evidence_id, doc_name, text FROM canonical_evidence "
                "WHERE type = 'text' ORDER BY doc_name, evidence_id"):
            chunks.setdefault(doc, []).append((eid, normalize(text or "")))
        con2.close()
        gmap = {e: e for doc in chunks for e, _ in chunks[doc]}
        cvec = {str(e): i for i, e in enumerate(P["eids"])}
        cvecs = P["vecs"]
    ivec = {str(e): i for i, e in enumerate(P["eids"])}
    ivecs = P["vecs"]
    qvec = {str(u): v for u, v in zip(Q["quids"], Q["vecs"])}

    img_by_doc = collections.OrderedDict()
    for eid, doc, desc in imgs:
        img_by_doc.setdefault(doc, []).append((eid, normalize(desc or "")))

    gold, dropped = collections.defaultdict(
        lambda: {"text": set(), "visual": set()}), 0
    for quid, eid, etype in gold_rows:
        if etype == "text":
            cid = gmap.get(eid)
            if cid is None:
                dropped += 1
                continue
            gold[quid]["text"].add(cid)
        else:
            gold[quid]["visual"].add(eid)
    print(f"[{pool}] text pool {sum(len(v) for v in chunks.values())} units / "
          f"{len(chunks)} docs; image pool {len(imgs)}")
    print(f"gold text evidence with no chunk mapping, dropped: {dropped}")

    idx = {}
    for doc in chunks:
        t_ids = [c for c, _ in chunks[doc]]
        i_ids = [e for e, _ in img_by_doc.get(doc, [])]
        t_tok = [tokenize(t) for _, t in chunks[doc]]
        i_tok = [tokenize(t) for _, t in img_by_doc.get(doc, [])]
        idx[doc] = {
            "text": (BM25(t_tok), t_ids,
                     np.asarray([cvec[c] for c in t_ids]), t_tok),
            "visual": (BM25(i_tok), i_ids,
                       np.asarray([ivec[e] for e in i_ids]) if i_ids else None,
                       i_tok),
        }

    rows = []
    for quid, doc, question in qs:
        if doc not in idx or quid not in gold:
            continue
        g = gold[quid]
        gset = g["text"] | g["visual"]
        if not gset:
            continue
        qt = tokenize((question or "").lower())
        qv = qvec[quid]
        ranked = {"bm25": {}, "dense": {}, "prf": {}, "rrf": {}, "rrf3": {}}
        for kind, bank in (("text", cvecs), ("visual", ivecs)):
            bm, ids, vrows, ctok = idx[doc][kind]
            if not ids:
                for r in ranked.values():
                    r[kind] = []
                continue
            order, _ = bm.rank(qt)
            ranked["bm25"][kind] = [ids[i] for i in order]
            p_order, _ = bm.rank(rm3(bm, ctok, qt))
            ranked["prf"][kind] = [ids[i] for i in p_order]
            sims = bank[vrows] @ qv
            d_order = np.lexsort((np.arange(len(ids)), -sims))
            ranked["dense"][kind] = [ids[i] for i in d_order]
            ranked["rrf"][kind] = rrf(ranked["bm25"][kind], ranked["dense"][kind])
            ranked["rrf3"][kind] = rrf(ranked["bm25"][kind], ranked["dense"][kind],
                                       ranked["prf"][kind])
        rows.append({"quid": quid, "gold": gset, "rank": ranked,
                     "visual_share": len(g["visual"]) / len(gset)})
    print(f"scored questions: {len(rows)}")
    return rows


def recall(row, retriever, a, k):
    r = row["rank"][retriever]
    got = set(r["text"][:a]) | set(r["visual"][:k - a])
    return len(row["gold"] & got) / len(row["gold"])


def vec(rows, retriever, a, k):
    return np.asarray([recall(r, retriever, a, k) for r in rows])


def ci(a, b, rng):
    d = a - b
    idx = rng.integers(0, len(d), size=(BOOTSTRAP, len(d)))
    lo, hi = np.percentile(d[idx].mean(axis=1), [2.5, 97.5])
    return d.mean(), lo, hi


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--quotes", default=DEFAULT_QUOTES)
    ap.add_argument("--pool", default="selfbuilt", choices=("selfbuilt", "canonical"))
    ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--split", default=os.path.join(
        REPO_ROOT, "manifests", "split_doc_disjoint.json"),
        help="frozen document-disjoint manifest; the quota is chosen on its "
             "train half and every reported number is on its test half")
    args = ap.parse_args()
    k = args.k
    pa = PAPER_QUOTA[k][0]

    rows = build(args.db, args.quotes, args.pool)
    rng = np.random.default_rng(SEED)

    # The quota is a fitted parameter, so it cannot be chosen on the same
    # questions it is then scored on. It is picked on the training half of the
    # frozen document-disjoint split and every number below is reported on the
    # held-out test half. The fusion component needs no such protection -- it
    # fits nothing -- but it is reported on the same held-out rows so the two
    # contributions are directly comparable.
    doc_split = {}
    if os.path.exists(args.split):
        import json
        doc_split = json.load(open(args.split, encoding="utf-8"))["doc_to_split"]
    if doc_split:
        con = sqlite3.connect(args.db)
        q_doc = dict(con.execute(
            "SELECT question_uid, doc_name FROM questions WHERE split='evaluation'"))
        con.close()
        tr = [r for r in rows if doc_split.get(q_doc.get(r["quid"])) == "train"]
        te = [r for r in rows if doc_split.get(q_doc.get(r["quid"])) == "test"]
        print(f"document-disjoint split: train {len(tr)} questions, "
              f"test {len(te)} questions")
    else:
        print("[warn] no split manifest; selecting and scoring on the same rows")
        tr = te = rows

    print()
    print("=" * 72)
    print(f"FIXED-QUOTA CURVE, k={k}  (RRF3, TRAIN half -- selection only)")
    print("=" * 72)
    curve = {a: vec(tr, "rrf3", a, k).mean() for a in range(k + 1)}
    best_a = max(curve, key=curve.get)
    rows = te
    for a in range(k + 1):
        mark = ""
        if a == best_a:
            mark = "  <- best fixed"
        if a == pa:
            mark += "  <- paper"
        print(f"  text {a:>2} / image {k - a:<2}   {curve[a]:.4f}{mark}")

    h = k // 2
    configs = [
        ("paper: BGE dense, quota %d/%d" % (pa, k - pa), "dense", pa),
        ("BM25, quota %d/%d" % (pa, k - pa), "bm25", pa),
        ("BM25+PRF, quota %d/%d" % (pa, k - pa), "prf", pa),
        ("dense, quota %d/%d" % (h, k - h), "dense", h),
        ("RRF(bm25,dense), quota %d/%d" % (pa, k - pa), "rrf", pa),
        ("RRF(bm25,dense), quota %d/%d" % (h, k - h), "rrf", h),
        ("RRF(bm25,dense,prf), quota %d/%d" % (h, k - h), "rrf3", h),
        ("RRF3, best fixed quota %d/%d" % (best_a, k - best_a), "rrf3", best_a),
    ]
    vals = {name: vec(rows, r, a, k) for name, r, a in configs}
    base = vals[configs[0][0]]

    print()
    print("=" * 78)
    print(f"CONFIGURATIONS vs THE PUBLISHED ONE, k={k}")
    print("=" * 78)
    print(f"{'configuration':<36}{'recall':>9}{'delta vs paper':>33}")
    print("-" * 78)
    for name, _, _ in configs:
        v = vals[name]
        if name == configs[0][0]:
            print(f"{name:<36}{v.mean():>9.4f}{'--':>33}")
            continue
        d, lo, hi = ci(v, base, rng)
        star = "*" if (lo > 0 or hi < 0) else " "
        print(f"{name:<36}{v.mean():>9.4f}"
              f"{d:>+16.4f}  [{lo:>+.4f}, {hi:>+.4f}]{star}")
    print("-" * 78)
    print("* = 95% CI excludes zero (paired bootstrap over questions, "
          f"B={BOOTSTRAP})")

    print()
    print("=" * 78)
    print("DECOMPOSITION: what each change contributes on its own")
    print("=" * 78)
    steps = [
        ("quota alone   %d/%d -> %d/%d" % (pa, k - pa, h, k - h),
         vals[configs[3][0]], base),
        ("fusion alone  dense -> RRF", vals[configs[4][0]], base),
        ("PRF alone     bm25 -> bm25+PRF", vals[configs[2][0]], vals[configs[1][0]]),
        ("quota + fusion", vals[configs[5][0]], base),
        ("quota + fusion + PRF", vals[configs[6][0]], base),
        ("  of which: fusion on top of quota", vals[configs[5][0]], vals[configs[3][0]]),
        ("  of which: quota on top of fusion", vals[configs[5][0]], vals[configs[4][0]]),
        ("  of which: PRF on top of both", vals[configs[6][0]], vals[configs[5][0]]),
    ]
    for label, a, b in steps:
        d, lo, hi = ci(a, b, rng)
        star = "*" if (lo > 0 or hi < 0) else " "
        print(f"{label:<36}{d:>+10.4f}  [{lo:>+.4f}, {hi:>+.4f}]{star}")

    vs = np.asarray([r["visual_share"] for r in rows])
    print()
    print("questions with gold in both modalities: "
          f"{np.mean((vs > 0) & (vs < 1)):.1%}   visual-only: "
          f"{np.mean(vs == 1):.1%}   text-only: {np.mean(vs == 0):.1%}")


if __name__ == "__main__":
    main()
