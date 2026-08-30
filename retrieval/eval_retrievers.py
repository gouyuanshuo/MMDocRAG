"""BM25 vs dense vs their fusion, at quote granularity, split by gold modality.

This is the RQ2 table -- does the best retriever depend on the query? -- and the
text-side half of the RQ1b crossover. Everything is held constant except the
retriever: same quote pool, same queries, same gold, same image representation.

Fusion is Reciprocal Rank Fusion, score = sum over retrievers of 1/(C + rank).
RRF is used rather than score interpolation because BM25 scores and cosine
similarities live on incompatible scales and normalising them introduces a
parameter that would need its own tuning. Note that the paper's own hybrid rows
are a *fixed modality quota*, not RRF, so the numbers are related but not the
same construction.

    POOL CAVEAT. As in retrieval/eval_quote_recall.py, the pool is
    canonical_evidence -- the union of every question's candidate list, mean 115
    quotes per document against the paper's ~600. Absolute recall runs
    optimistic and is not comparable to Table 6. Comparisons *within* this table
    hold the pool fixed and are valid.

Run:
    python -m retrieval.eval_retrievers
    python -m retrieval.eval_retrievers --image-repr ocr
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

from retrieval.bm25 import BM25                          # noqa: E402
from retrieval.corpus import normalize, tokenize         # noqa: E402
from retrieval.dense import load as load_dense           # noqa: E402
from retrieval.eval_quote_recall import surrogate        # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO_ROOT, "canonical", "mmdocrag.sqlite")
DEFAULT_OCR = os.path.join(REPO_ROOT, "retrieval", "quote_ocr.sqlite")
KS = (1, 5, 10, 20)
RRF_C = 60          # the constant from the original RRF paper


def rrf(rank_lists, c=RRF_C):
    """Fuse ranked id-lists into one score dict."""
    score = collections.defaultdict(float)
    for ranks in rank_lists:
        for r, item in enumerate(ranks):
            score[item] += 1.0 / (c + r + 1)
    return score


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--ocr", default=DEFAULT_OCR)
    ap.add_argument("--setting", default="20", choices=["15", "20"])
    ap.add_argument("--split", default="evaluation")
    ap.add_argument("--image-repr", dest="repr", default="vlm",
                    choices=("vlm", "ocr", "both", "none"))
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    ev = con.execute(
        "SELECT evidence_id, doc_name, type, text, img_description "
        "FROM canonical_evidence ORDER BY doc_name, evidence_id").fetchall()
    qs = con.execute(
        "SELECT question_uid, doc_name, question FROM questions WHERE split = ? "
        "ORDER BY question_uid", (args.split,)).fetchall()
    gold_rows = con.execute("""
        SELECT g.question_uid, g.evidence_id, e.type
        FROM question_gold_evidence g
        JOIN canonical_evidence e ON e.evidence_id = g.evidence_id
        JOIN questions q          ON q.question_uid = g.question_uid
        WHERE q.split = ? AND g.setting = ?
    """, (args.split, args.setting)).fetchall()
    con.close()

    ocr = {}
    if os.path.exists(args.ocr):
        c = sqlite3.connect(args.ocr)
        ocr = {e: t or "" for e, t in c.execute("SELECT evidence_id, text FROM quote_ocr")}
        c.close()

    gold = collections.defaultdict(list)
    for quid, eid, etype in gold_rows:
        gold[quid].append((eid, "text" if etype == "text" else "visual"))

    # ---- lexical index ----
    by_doc = collections.OrderedDict()
    for eid, doc, etype, text, desc in ev:
        body = normalize(surrogate(etype, text, desc, ocr.get(eid, ""), args.repr))
        by_doc.setdefault(doc, []).append((eid, body))
    bm_idx = {d: (BM25([tokenize(b) for _, b in items]), [e for e, _ in items])
              for d, items in by_doc.items()}

    # ---- dense index ----
    try:
        P, Q = load_dense(args.repr)
    except FileNotFoundError:
        raise SystemExit(f"no embeddings for --image-repr {args.repr}; run "
                         f"`python -m retrieval.dense --image-repr {args.repr}` first")
    p_eid, p_doc, p_vec = P["eids"], P["docs"], P["vecs"]
    q_vec = {quid: Q["vecs"][i] for i, quid in enumerate(Q["quids"])}
    dense_by_doc = collections.defaultdict(lambda: ([], []))
    for i, doc in enumerate(p_doc):
        dense_by_doc[str(doc)][0].append(str(p_eid[i]))
        dense_by_doc[str(doc)][1].append(i)
    dense_idx = {d: (eids, p_vec[np.asarray(rows)])
                 for d, (eids, rows) in dense_by_doc.items()}

    methods = ("bm25", "dense", "rrf")
    hits = {m: {k: {kd: 0 for kd in ("text", "visual")} for k in KS} for m in methods}
    tot = collections.Counter()

    for quid, doc, question in qs:
        if quid not in gold or doc not in bm_idx or doc not in dense_idx:
            continue
        bm, b_eids = bm_idx[doc]
        order, _ = bm.rank(tokenize((question or "").lower()))
        lex_rank = [b_eids[i] for i in order]

        d_eids, d_vecs = dense_idx[doc]
        sims = d_vecs @ q_vec[quid]
        den_rank = [d_eids[i] for i in np.lexsort((np.arange(len(d_eids)), -sims))]

        fused = rrf([lex_rank, den_rank])
        rrf_rank = sorted(fused, key=lambda e: -fused[e])

        ranks = {"bm25": {e: r for r, e in enumerate(lex_rank)},
                 "dense": {e: r for r, e in enumerate(den_rank)},
                 "rrf": {e: r for r, e in enumerate(rrf_rank)}}
        for eid, kd in gold[quid]:
            if eid not in ranks["bm25"]:
                continue
            tot[kd] += 1
            for m in methods:
                r = ranks[m].get(eid)
                if r is None:
                    continue
                for k in KS:
                    if r < k:
                        hits[m][k][kd] += 1

    n_t, n_v = tot["text"], tot["visual"]
    print(f"pool {len(ev)} quotes / {len(by_doc)} docs, image repr = {args.repr}")
    print(f"gold items: text {n_t}, image {n_v}\n")
    print("=" * 82)
    print("RETRIEVER COMPARISON, quote granularity   (pool is question-conditioned)")
    print("=" * 82)
    print(f"{'retriever':<12}{'gold kind':<12}" + "".join(f"{'@' + str(k):>10}" for k in KS))
    print("-" * 82)
    for m in methods:
        for kd, n in (("text", n_t), ("visual", n_v)):
            label = m if kd == "text" else ""
            print(f"{label:<12}{kd + ' gold':<12}"
                  + "".join(f"{hits[m][k][kd] / n:>10.3f}" for k in KS))
        print("-" * 82)

    print()
    print("=" * 82)
    print("DOES THE BEST RETRIEVER DEPEND ON THE MODALITY?   <- the RQ2 question")
    print("=" * 82)
    print(f"{'':<24}" + "".join(f"{'@' + str(k):>10}" for k in KS))
    for kd, n in (("text", n_t), ("visual", n_v)):
        d = [(hits["dense"][k][kd] - hits["bm25"][k][kd]) / n for k in KS]
        print(f"{'dense - bm25, ' + kd:<24}" + "".join(f"{v:>+10.3f}" for v in d))
    for kd, n in (("text", n_t), ("visual", n_v)):
        d = [(hits["rrf"][k][kd] - max(hits["bm25"][k][kd], hits["dense"][k][kd])) / n
             for k in KS]
        print(f"{'rrf - best single, ' + kd:<24}" + "".join(f"{v:>+10.3f}" for v in d))
    print("\nA sign flip between the two rows of the first block means neither "
          "retriever dominates and the\nchoice is query-dependent -- the "
          "condition RQ2 needs. RRF beating both single retrievers means\nthe "
          "fusion is worth its double cost, which is the baseline any router "
          "has to undercut.")


if __name__ == "__main__":
    main()
