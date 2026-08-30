"""Why does a text retriever find image quotes more easily than text quotes?

At quote granularity BM25 reaches image gold better than text gold (recall@10
0.680 vs 0.501), which is the same direction the paper reports for BGE (74.2 vs
47.0 at k=20). Two explanations compete, and they have opposite consequences for
RQ1b:

  A. FEWER COMPETITORS. The pool holds 19,151 text quotes against 6,565 image
     quotes, so an image quote is ranked against roughly a third as many rivals
     of its own kind. If this is the whole story, the effect is an artefact of
     pool composition and says nothing about modality.

  B. BETTER REPRESENTATION. `img_description` is VLM-written prose -- "a
     comparison chart showing early-stage entry valuations" -- phrased much like
     a question is phrased, while a text quote is raw document prose. If this is
     the story, the effect is real query-document vocabulary alignment, and it
     is exactly what a visual retriever would capture directly.

Separating them
---------------
Percentile rank controls for pool size exactly: rank the gold item only among
quotes of its own modality in its own document, then divide by that pool's size.
A percentile is scale-free, so if image gold still ranks better by percentile,
pool size is not the explanation.

The size contribution is then quantified with a counterfactual: an item at
percentile p in a pool of N lands at rank p*N, so re-scoring the image gold
percentiles against the *text* pool size gives the recall images would have had
if they were as crowded as text. The gap between actual and counterfactual is
what A is worth; whatever separates the counterfactual from text gold is B.

    This assumes the percentile distribution is invariant to pool size -- that
    added distractors are exchangeable with existing ones. That is a first-order
    model, not an identity, and it is why the direct lexical evidence below is
    reported alongside it rather than instead of it.

Direct evidence for B: how much of the question's vocabulary actually appears in
the gold quote, plain and idf-weighted. No modelling assumption at all.

Run:
    python -m retrieval.diagnose_modality
"""

import argparse
import collections
import math
import os
import sqlite3
import sys

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retrieval.bm25 import BM25                    # noqa: E402
from retrieval.corpus import normalize, tokenize   # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO_ROOT, "canonical", "mmdocrag.sqlite")
KS = (1, 5, 10, 20)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--setting", default="20", choices=["15", "20"])
    ap.add_argument("--split", default="evaluation")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    ev = con.execute(
        "SELECT evidence_id, doc_name, type, text, img_description "
        "FROM canonical_evidence ORDER BY doc_name, evidence_id").fetchall()
    qs = con.execute(
        "SELECT question_uid, doc_name, question FROM questions WHERE split = ?",
        (args.split,)).fetchall()
    gold_rows = con.execute("""
        SELECT g.question_uid, g.evidence_id, e.type
        FROM question_gold_evidence g
        JOIN canonical_evidence e ON e.evidence_id = g.evidence_id
        JOIN questions q          ON q.question_uid = g.question_uid
        WHERE q.split = ? AND g.setting = ?
    """, (args.split, args.setting)).fetchall()
    con.close()

    gold = collections.defaultdict(list)
    for quid, eid, etype in gold_rows:
        gold[quid].append((eid, "text" if etype == "text" else "visual"))

    # body text per quote, and per-document split into the two modality pools
    body, kind = {}, {}
    by_doc = collections.OrderedDict()
    for eid, doc, etype, text, desc in ev:
        k = "text" if etype == "text" else "visual"
        kind[eid] = k
        body[eid] = normalize((text if k == "text" else desc) or "")
        by_doc.setdefault(doc, {"text": [], "visual": []})[k].append(eid)

    # one BM25 per (document, modality): ranking within a modality is what makes
    # the percentile comparable across the two.
    idx = {}
    for doc, pools in by_doc.items():
        idx[doc] = {}
        for k, eids in pools.items():
            if eids:
                idx[doc][k] = (BM25([tokenize(body[e]) for e in eids]), eids)

    pct = collections.defaultdict(list)          # modality -> percentile ranks
    absrank = collections.defaultdict(list)      # modality -> within-pool rank
    poolsz = collections.defaultdict(list)
    cover, cover_idf = collections.defaultdict(list), collections.defaultdict(list)

    # idf over the whole collection, for weighting question-term coverage
    df = collections.Counter()
    for eid, b in body.items():
        df.update(set(tokenize(b)))
    N = len(body)
    idf = {t: math.log(1 + (N - n + 0.5) / (n + 0.5)) for t, n in df.items()}

    for quid, doc, question in qs:
        if quid not in gold or doc not in idx:
            continue
        qtok = tokenize(question.lower())
        qset = set(qtok)
        ranked = {}
        for k, (bm, eids) in idx[doc].items():
            order, _ = bm.rank(qtok)
            ranked[k] = {eids[i]: r for r, i in enumerate(order)}
        for eid, k in gold[quid]:
            if k not in ranked or eid not in ranked[k]:
                continue
            r, n = ranked[k][eid], len(idx[doc][k][1])
            absrank[k].append(r)
            poolsz[k].append(n)
            pct[k].append(r / n)
            gtok = set(tokenize(body[eid]))
            if qset:
                cover[k].append(len(qset & gtok) / len(qset))
                num = sum(idf.get(t, 0) for t in qset & gtok)
                den = sum(idf.get(t, 0) for t in qset)
                cover_idf[k].append(num / den if den else 0.0)

    print("=" * 84)
    print("1. POOL COMPOSITION")
    print("=" * 84)
    tot = collections.Counter(kind.values())
    print(f"quotes in pool          : text {tot['text']}, image {tot['visual']}")
    print(f"mean per-document pool  : text {np.mean(poolsz['text']):.0f}, "
          f"image {np.mean(poolsz['visual']):.0f}")
    print(f"gold items scored       : text {len(pct['text'])}, "
          f"image {len(pct['visual'])}")

    print()
    print("=" * 84)
    print("2. RANK WITHIN OWN MODALITY  (percentile controls for pool size)")
    print("=" * 84)
    print(f"{'':<22}{'median rank':>13}{'median pct':>13}{'mean pct':>11}")
    for k, label in (("text", "text gold"), ("visual", "image gold")):
        print(f"{label:<22}{np.median(absrank[k]):>13.0f}"
              f"{np.median(pct[k]):>13.3f}{np.mean(pct[k]):>11.3f}")
    dp = np.mean(pct["text"]) - np.mean(pct["visual"])
    print(f"\nimage gold sits {dp:+.3f} higher by percentile "
          f"({'B: better representation' if dp > 0.02 else 'no representation edge'})")

    print()
    print("=" * 84)
    print("3. DECOMPOSITION  (counterfactual: image pool grown to text pool size)")
    print("=" * 84)
    pv = np.asarray(pct["visual"])
    nv = np.asarray(poolsz["visual"], dtype=float)
    nt_mean = np.mean(poolsz["text"])
    print(f"{'':<34}" + "".join(f"{'@' + str(k):>10}" for k in KS))
    print("-" * 84)
    act = [np.mean(pv * nv < k) for k in KS]
    cf = [np.mean(pv * nt_mean < k) for k in KS]
    txt = [np.mean(np.asarray(pct["text"]) * np.asarray(poolsz["text"], float) < k)
           for k in KS]
    print(f"{'image gold, actual pool':<34}" + "".join(f"{v:>10.3f}" for v in act))
    print(f"{'image gold, at text pool size':<34}" + "".join(f"{v:>10.3f}" for v in cf))
    print(f"{'text gold, actual':<34}" + "".join(f"{v:>10.3f}" for v in txt))
    print("-" * 84)
    print(f"{'A. attributable to pool size':<34}"
          + "".join(f"{a - c:>+10.3f}" for a, c in zip(act, cf)))
    print(f"{'B. attributable to representation':<34}"
          + "".join(f"{c - t:>+10.3f}" for c, t in zip(cf, txt)))

    print()
    print("=" * 84)
    print("4. DIRECT EVIDENCE: how much question vocabulary the gold quote contains")
    print("=" * 84)
    print(f"{'':<22}{'plain coverage':>16}{'idf-weighted':>15}{'quote length':>14}")
    for k, label in (("text", "text gold"), ("visual", "image gold")):
        lens = [len(tokenize(body[e])) for quid in gold for e, kk in gold[quid]
                if kk == k and e in body]
        print(f"{label:<22}{np.mean(cover[k]):>16.3f}{np.mean(cover_idf[k]):>15.3f}"
              f"{np.median(lens):>14.0f}")
    d_cov = np.mean(cover_idf["visual"]) - np.mean(cover_idf["text"])
    print(f"\nimage gold carries {d_cov:+.3f} more of the question's idf mass. "
          f"No modelling assumption here:")
    print("it is counted directly from the text each quote actually contributes "
          "to the index.")


if __name__ == "__main__":
    main()
