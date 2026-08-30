"""Does text retrieval reach figure evidence as well as it reaches text evidence?

This is the experiment RQ1b turns on. The proposal's original argument was
structural -- some documents are pure scans, so a text index cannot see them at
all -- but this project's own full-corpus OCR pass dissolved it: gold evidence
on pages with no usable text fell from 12.1% to 0.7%, and documents entirely
invisible to a text index from 27 to 0. Every page now has *something* in the
index.

Having something in the index is not the same as being findable. OCR of a chart
yields axis labels and stray numbers, not the trend the question asks about, and
OCR'd pages carry a median of 249 characters against 2,000+ for an ordinary text
page -- thin documents that BM25's length normalisation and any dense encoder
will both handle badly. So the question becomes empirical, and it is measured
here directly:

    recall@k over gold evidence items, split by whether the item is
    a text block or a figure/table.

A wide gap is the routing signal, on a mechanism that survives OCR. A narrow gap
means text retrieval is sufficient and RQ1b needs rethinking. Either way the
answer comes from measurement rather than assumption.

Retrieval is within the question's own document, matching MMDocRAG's "targeted
document corpus" setting, and scored at page level (see retrieval/corpus.py for
why the page is the unit).

Run:
    python -m retrieval.eval_page_recall
    python -m retrieval.eval_page_recall --pages retrieval/pages_noocr.sqlite
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

from retrieval.bm25 import BM25                      # noqa: E402
from retrieval.corpus import tokenize                # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PAGES = os.path.join(REPO_ROOT, "retrieval", "pages.sqlite")
DEFAULT_DB = os.path.join(REPO_ROOT, "canonical", "mmdocrag.sqlite")
KS = (1, 3, 5, 10, 20)


def load_pages(path):
    con = sqlite3.connect(path)
    rows = con.execute(
        "SELECT doc_name, page_id, text FROM pages ORDER BY doc_name, page_id"
    ).fetchall()
    con.close()
    by_doc = collections.OrderedDict()
    for doc, pid, text in rows:
        by_doc.setdefault(doc, []).append((pid, text))
    return by_doc


def load_questions(db_path, setting, split):
    con = sqlite3.connect(db_path)
    qs = con.execute(
        "SELECT question_uid, doc_name, question FROM questions WHERE split = ?",
        (split,)).fetchall()
    gold = con.execute("""
        SELECT g.question_uid, e.doc_name, e.page_id, e.type
        FROM question_gold_evidence g
        JOIN canonical_evidence e ON e.evidence_id = g.evidence_id
        JOIN questions q          ON q.question_uid = g.question_uid
        WHERE q.split = ? AND g.setting = ?
    """, (split, setting)).fetchall()
    con.close()

    items = collections.defaultdict(list)
    for quid, doc, pid, etype in gold:
        items[quid].append((doc, pid, etype))
    return [(q, d, t) for q, d, t in qs if q in items], items


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pages", default=DEFAULT_PAGES)
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--setting", default="20", choices=["15", "20"])
    ap.add_argument("--split", default="evaluation")
    args = ap.parse_args()

    by_doc = load_pages(args.pages)
    questions, gold_items = load_questions(args.db, args.setting, args.split)
    print(f"corpus  : {len(by_doc)} documents, "
          f"{sum(len(v) for v in by_doc.values())} pages  ({os.path.basename(args.pages)})")
    print(f"queries : {len(questions)} questions, setting {args.setting}, "
          f"split {args.split}\n")

    # One BM25 per document, built once and reused across that document's
    # questions -- documents carry 9 questions each on average.
    indexes, page_ids = {}, {}
    for doc, pages in by_doc.items():
        page_ids[doc] = [p for p, _ in pages]
        indexes[doc] = BM25([tokenize(t or "") for _, t in pages])

    # item_hits[kind][k] = number of gold items whose page made the top k
    item_hits = {kd: {k: 0 for k in KS} for kd in ("text", "visual", "all")}
    item_tot = collections.Counter()
    q_recall = {k: [] for k in KS}          # per-question page recall
    ranks_by_kind = collections.defaultdict(list)
    skipped = 0

    for quid, doc, question in questions:
        if doc not in indexes:
            skipped += 1
            continue
        order, _ = indexes[doc].rank(tokenize(question.lower()))
        ranked = [page_ids[doc][i] for i in order]
        pos = {p: r for r, p in enumerate(ranked)}       # page -> 0-based rank

        gold_pages = set()
        for gdoc, gpid, etype in gold_items[quid]:
            if gdoc != doc or gpid not in pos:
                # Evidence in a different document than the question's own, or a
                # page the PDF does not have. Counted, never silently dropped.
                item_tot["unreachable"] += 1
                continue
            kind = "text" if etype == "text" else "visual"
            item_tot[kind] += 1
            gold_pages.add(gpid)
            r = pos[gpid]
            ranks_by_kind[kind].append(r)
            for k in KS:
                if r < k:
                    item_hits[kind][k] += 1
                    item_hits["all"][k] += 1

        if gold_pages:
            for k in KS:
                top = set(ranked[:k])
                q_recall[k].append(len(gold_pages & top) / len(gold_pages))

    n_txt, n_vis = item_tot["text"], item_tot["visual"]
    print("=" * 88)
    print("1. PAGE RECALL PER QUESTION  (BM25, within the question's own document)")
    print("=" * 88)
    print(f"{'':<20}" + "".join(f"{'@' + str(k):>10}" for k in KS))
    print("-" * 88)
    print(f"{'recall':<20}" + "".join(f"{np.mean(q_recall[k]):>10.3f}" for k in KS))
    print(f"\nquestions scored: {len(q_recall[KS[0]])}"
          + (f", skipped (no PDF): {skipped}" if skipped else ""))

    print()
    print("=" * 88)
    print("2. GOLD-ITEM RECALL, SPLIT BY MODALITY   <- the RQ1b test")
    print("=" * 88)
    print(f"{'gold item kind':<20}{'items':>8}" + "".join(f"{'@' + str(k):>10}" for k in KS))
    print("-" * 88)
    for kind, n in (("text", n_txt), ("visual", n_vis)):
        row = f"{kind:<20}{n:>8}"
        for k in KS:
            row += f"{item_hits[kind][k] / n:>10.3f}" if n else f"{'-':>10}"
        print(row)
    if n_txt and n_vis:
        print("-" * 88)
        gap = f"{'gap (text - visual)':<20}{'':>8}"
        for k in KS:
            gap += f"{item_hits['text'][k]/n_txt - item_hits['visual'][k]/n_vis:>+10.3f}"
        print(gap)
        print(f"\nmedian rank of the hosting page:  "
              f"text {np.median(ranks_by_kind['text']):.0f}, "
              f"visual {np.median(ranks_by_kind['visual']):.0f}  (0 = top hit)")
    if item_tot["unreachable"]:
        print(f"\ngold items outside the question's own document or missing from "
              f"the PDF: {item_tot['unreachable']}")

    print()
    print("=" * 88)
    print("READING")
    print("=" * 88)
    if n_txt and n_vis:
        g10 = item_hits["text"][10] / n_txt - item_hits["visual"][10] / n_vis
        if g10 >= 0.10:
            print(f"Text retrieval reaches its own modality {g10:+.3f} better at k=10. "
                  f"A gap this size is the routing\nsignal RQ1b needs, and it survives "
                  f"OCR -- it is about what OCR text can express, not whether it exists.")
        elif g10 >= 0.03:
            print(f"A modest gap ({g10:+.3f} at k=10). Real but small; whether it is "
                  f"worth routing on depends on what\nvisual retrieval recovers on the "
                  f"same items. That is the next measurement.")
        else:
            print(f"Almost no gap ({g10:+.3f} at k=10). OCR-augmented text retrieval "
                  f"reaches figure evidence about as\nwell as text evidence, and RQ1b's "
                  f"premise needs rethinking rather than defending.")


if __name__ == "__main__":
    main()
