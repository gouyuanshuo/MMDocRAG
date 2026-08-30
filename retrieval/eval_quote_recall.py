"""Quote-granularity retrieval: what does an image quote's text surrogate buy?

Phase 1B measured page granularity and found no modality gap: BM25 reaches
figure evidence as well as text evidence (+0.015 at k=10), because a figure sits
on a text-rich page and the surrounding prose gives the page away. The paper's
own Table 6, measured at *quote* granularity, shows the opposite -- a two-way
crossover where text retrievers win on text quotes (BGE 47.0 vs ColQwen 36.0 at
k=20) and visual retrievers win on image quotes (ColQwen 84.3 vs BGE 74.2).

The difference is granularity: cut the figure away from its page and it has to
stand on whatever text represents it. This script measures how much that
representation is worth, by swapping it and changing nothing else:

    --image-repr vlm    the release's VLM-written img_description
    --image-repr ocr    RapidOCR run over the same crop (retrieval/ocr_quotes.py)
    --image-repr both   concatenated
    --image-repr none   empty, the floor

The vlm-minus-ocr gap is the retrievable information that comes from
understanding a figure rather than reading the characters printed on it. That is
the mechanism a visual retriever exploits directly, so the gap is evidence for
or against spending GPU budget on ColPali before spending it.

    POOL CAVEAT. The retrieval pool is canonical_evidence, which is the union of
    every question's candidate list -- a mean of 115 quotes per document against
    the roughly 600 the paper retrieves from. Every item is in the pool only
    because it was some question's gold or hard negative, so the pool is already
    question-conditioned and absolute recall here runs optimistic. It is NOT
    comparable to Table 6. It is entirely valid for the surrogate comparison,
    which holds the pool fixed and changes one field.

Run:
    python -m retrieval.eval_quote_recall --image-repr vlm
    python -m retrieval.eval_quote_recall --compare
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

from retrieval.bm25 import BM25                  # noqa: E402
from retrieval.corpus import normalize, tokenize  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO_ROOT, "canonical", "mmdocrag.sqlite")
DEFAULT_OCR = os.path.join(REPO_ROOT, "retrieval", "quote_ocr.sqlite")
KS = (1, 5, 10, 20)
REPRS = ("vlm", "ocr", "both", "none")


def load(db_path, ocr_path, setting, split):
    con = sqlite3.connect(db_path)
    ev = con.execute(
        "SELECT evidence_id, doc_name, type, text, img_description "
        "FROM canonical_evidence ORDER BY doc_name, evidence_id").fetchall()
    qs = con.execute(
        "SELECT question_uid, doc_name, question FROM questions WHERE split = ?",
        (split,)).fetchall()
    gold = con.execute("""
        SELECT g.question_uid, g.evidence_id, e.type
        FROM question_gold_evidence g
        JOIN canonical_evidence e ON e.evidence_id = g.evidence_id
        JOIN questions q          ON q.question_uid = g.question_uid
        WHERE q.split = ? AND g.setting = ?
    """, (split, setting)).fetchall()
    con.close()

    ocr = {}
    if os.path.exists(ocr_path):
        c = sqlite3.connect(ocr_path)
        ocr = {e: t or "" for e, t in
               c.execute("SELECT evidence_id, text FROM quote_ocr")}
        c.close()

    g = collections.defaultdict(list)
    for quid, eid, etype in gold:
        g[quid].append((eid, etype))
    return ev, qs, g, ocr


def surrogate(etype, text, desc, ocr_text, repr_mode):
    if etype == "text":
        return text or ""
    if repr_mode == "vlm":
        return desc or ""
    if repr_mode == "ocr":
        return ocr_text or ""
    if repr_mode == "both":
        return ((desc or "") + " " + (ocr_text or "")).strip()
    return ""


def evaluate(ev, qs, gold, ocr, repr_mode):
    by_doc = collections.OrderedDict()
    for eid, doc, etype, text, desc in ev:
        body = surrogate(etype, text, desc, ocr.get(eid, ""), repr_mode)
        by_doc.setdefault(doc, []).append((eid, etype, normalize(body)))

    indexes = {}
    for doc, items in by_doc.items():
        indexes[doc] = (BM25([tokenize(b) for _, _, b in items]),
                        [e for e, _, _ in items])

    hits = {kd: {k: 0 for k in KS} for kd in ("text", "visual")}
    tot = collections.Counter()
    ranks = collections.defaultdict(list)
    empty_surrogate = collections.Counter()

    for quid, doc, question in qs:
        if quid not in gold or doc not in indexes:
            continue
        bm, eids = indexes[doc]
        order, _ = bm.rank(tokenize(question.lower()))
        pos = {eids[i]: r for r, i in enumerate(order)}
        for eid, etype in gold[quid]:
            if eid not in pos:
                tot["absent"] += 1
                continue
            kind = "text" if etype == "text" else "visual"
            tot[kind] += 1
            ranks[kind].append(pos[eid])
            for k in KS:
                if pos[eid] < k:
                    hits[kind][k] += 1

    # How many pool items ended up with no usable text under this surrogate --
    # an empty document can never be retrieved, so this is the hard floor on
    # what the representation can achieve.
    for doc, items in by_doc.items():
        for eid, etype, body in items:
            if etype != "text" and not tokenize(body):
                empty_surrogate["image"] += 1
            elif etype != "text":
                empty_surrogate["image_ok"] += 1
    return hits, tot, ranks, empty_surrogate, by_doc


def report(name, hits, tot, ranks, empty):
    n_t, n_v = tot["text"], tot["visual"]
    print(f"{name:<10}{'text gold':<12}{n_t:>7}" +
          "".join(f"{hits['text'][k]/n_t:>9.3f}" for k in KS) if n_t else "")
    print(f"{'':<10}{'image gold':<12}{n_v:>7}" +
          "".join(f"{hits['visual'][k]/n_v:>9.3f}" for k in KS) if n_v else "")
    if n_v:
        print(f"{'':<10}{'median rank':<12}{'':>7}"
              f"   text {np.median(ranks['text']):.0f} / image "
              f"{np.median(ranks['visual']):.0f}"
              f"   unretrievable image quotes in pool: {empty['image']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--ocr", default=DEFAULT_OCR)
    ap.add_argument("--setting", default="20", choices=["15", "20"])
    ap.add_argument("--split", default="evaluation")
    ap.add_argument("--image-repr", dest="repr", default="vlm", choices=REPRS)
    ap.add_argument("--compare", action="store_true",
                    help="run every representation and print the comparison")
    args = ap.parse_args()

    ev, qs, gold, ocr = load(args.db, args.ocr, args.setting, args.split)
    print(f"pool     : {len(ev)} quotes over "
          f"{len(set(e[1] for e in ev))} documents "
          f"(mean {len(ev)/len(set(e[1] for e in ev)):.0f}/doc)")
    print(f"queries  : {len(qs)} questions, setting {args.setting}")
    print(f"crop OCR : {len(ocr)} cached"
          + ("" if ocr else "  <- run retrieval.ocr_quotes first for the ocr arm"))
    print()

    modes = list(REPRS) if args.compare else [args.repr]
    modes = [m for m in modes if m != "ocr" or ocr] or [args.repr]

    print("=" * 78)
    print(f"BM25 quote retrieval, recall@k   (pool is question-conditioned; "
          f"see docstring)")
    print("=" * 78)
    print(f"{'img repr':<10}{'gold kind':<12}{'items':>7}" +
          "".join(f"{'@' + str(k):>9}" for k in KS))
    print("-" * 78)
    results = {}
    for m in modes:
        hits, tot, ranks, empty, _ = evaluate(ev, qs, gold, ocr, m)
        results[m] = (hits, tot)
        report(m, hits, tot, ranks, empty)
        print("-" * 78)

    if len(results) > 1 and "vlm" in results and "ocr" in results:
        (hv, tv), (ho, to) = results["vlm"], results["ocr"]
        n = tv["visual"]
        print()
        print("=" * 78)
        print("VLM-text minus OCR-text, on image gold")
        print("=" * 78)
        print(f"{'':<24}" + "".join(f"{'@' + str(k):>9}" for k in KS))
        print(f"{'gap':<24}" +
              "".join(f"{(hv['visual'][k] - ho['visual'][k]) / n:>+9.3f}" for k in KS))
        print("\nA large gap means an image quote is retrievable because a model "
              "understood the figure,\nnot because characters were printed on it "
              "-- the information a visual retriever gets\ndirectly, without the "
              "description step.")


if __name__ == "__main__":
    main()
