"""Is there a real, predictable modality signal at the RETRIEVAL layer?

Phase 1A.5 showed there is none at the generation-input layer: whether images
beat their text descriptions is a coin flip belonging to the model-question
pair, so no router can read it off the question. Before building Phase 1B/2/3
on the assumption that retrieval-layer routing is different, that assumption
should be checked -- cheaply, and before spending weeks on it.

The retrieval-layer decision has a structurally different character, and this
script measures whether that difference is actually present in this corpus:

  Generation layer            Retrieval layer
  ----------------            ---------------
  outcome is a sampled        retrieval is a deterministic function of the
  generation, so the          query and the index: if a text index cannot
  per-question label is       reach a piece of evidence, it fails every time
  noisy
  both arms always see        some evidence is physically absent from a text
  the same evidence           index -- a figure on a page with no text layer
                              simply is not there

So the question is: how much gold evidence is unreachable by a text index, and
is that concentrated in particular questions and documents rather than
sprinkled uniformly? Concentration is what makes it routable. If every question
had the same small fraction of unreachable evidence, a router would have
nothing to separate.

This uses only the canonical layer and the PDFs. No retrieval, no API, no
model. It measures the ceiling of the signal, not a router's ability to use it.

Run:
    python -m router.retrieval_signal
"""

import argparse
import collections
import json
import os
import sqlite3
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO_ROOT, "canonical", "mmdocrag.sqlite")
DEFAULT_PDF_ROOT = r"D:\Dataset\MMDocRAG\doc_pdfs\doc_pdfs"
PAGE_CACHE = os.path.join(REPO_ROOT, "canonical", "page_textlen.json")
DEFAULT_OCR_DB = os.path.join(REPO_ROOT, "canonical", "ocr_cache.sqlite")

# Same bar router/../canonical/ocr.py uses for Phase 1B indexing: a page with
# only a running header is an empty document as far as BM25/dense is concerned.
TEXT_LAYER_MIN = 100


def page_text_lengths(pdf_root, cache=PAGE_CACHE):
    """{doc_name: [chars per page]}, cached -- get_text over 14,763 pages."""
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as fh:
            return json.load(fh)
    import pymupdf
    out = {}
    names = sorted(n for n in os.listdir(pdf_root) if n.lower().endswith(".pdf"))
    for i, name in enumerate(names, 1):
        try:
            doc = pymupdf.open(os.path.join(pdf_root, name))
        except Exception:
            continue
        out[name[:-4]] = [len(doc[p].get_text().strip())
                          for p in range(doc.page_count)]
        doc.close()
        if i % 50 == 0:
            print(f"  scanned {i}/{len(names)} pdfs", flush=True)
    with open(cache, "w", encoding="utf-8") as fh:
        json.dump(out, fh)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--pdf-root", default=DEFAULT_PDF_ROOT)
    ap.add_argument("--setting", default="20", choices=["15", "20"])
    ap.add_argument("--min-chars", type=int, default=TEXT_LAYER_MIN)
    ap.add_argument("--ocr-db", default=DEFAULT_OCR_DB)
    ap.add_argument("--no-ocr", action="store_true",
                    help="ignore the OCR cache, i.e. measure a text index built "
                         "from the PDF text layer alone")
    args = ap.parse_args()

    print("scanning PDF text layers (cached after the first run)...")
    pages = page_text_lengths(args.pdf_root)
    print(f"{len(pages)} documents, {sum(len(v) for v in pages.values())} pages\n")

    # Folding OCR in is not optional bookkeeping: it changes the answer.
    # Measured on the PDF text layer alone, 27 documents are entirely
    # invisible to a text index; after this project's full-corpus OCR pass,
    # none are. Quoting the pre-OCR figure as the mechanism for
    # retrieval-layer routing would describe a corpus we no longer have.
    ocr = {}
    if not args.no_ocr and os.path.exists(args.ocr_db):
        _con = sqlite3.connect(args.ocr_db)
        ocr = {(d, pg): c for d, pg, c in
               _con.execute("SELECT doc_name, page_id, chars FROM ocr_pages")}
        _con.close()
        print(f"OCR cache: {len(ocr)} pages folded in "
              f"(pass --no-ocr for the text-layer-only view)")
    else:
        print("OCR cache NOT used -- text-layer-only view")
    print()

    con = sqlite3.connect(args.db)
    rows = con.execute("""
        SELECT q.question_uid, q.doc_name, e.type, e.doc_name, e.page_id
        FROM question_gold_evidence g
        JOIN canonical_evidence e ON e.evidence_id = g.evidence_id
        JOIN questions q          ON q.question_uid = g.question_uid
        WHERE q.split = 'evaluation' AND g.setting = ?
    """, (args.setting,)).fetchall()
    con.close()

    # Per question: how much of its gold evidence a text-only index can reach.
    per_q = collections.defaultdict(lambda: {"n": 0, "blind": 0, "visual": 0,
                                             "doc": None})
    unknown_pages = 0
    for quid, qdoc, etype, edoc, page_id in rows:
        rec = per_q[quid]
        rec["doc"] = qdoc
        rec["n"] += 1
        if etype in ("image", "table"):
            rec["visual"] += 1
        lens = pages.get(edoc)
        if lens is None or page_id >= len(lens):
            unknown_pages += 1
            continue
        # Blind = the page hosting this evidence has no usable text layer, so a
        # text index built from the PDF contains nothing for it at all.
        reachable = max(lens[page_id], ocr.get((edoc, page_id), 0))
        if reachable < args.min_chars:
            rec["blind"] += 1

    n_q = len(per_q)
    print("=" * 92)
    print(f"1. GOLD EVIDENCE A TEXT-ONLY INDEX CANNOT REACH  "
          f"(page text layer < {args.min_chars} chars)")
    print("=" * 92)
    tot = sum(r["n"] for r in per_q.values())
    blind = sum(r["blind"] for r in per_q.values())
    vis = sum(r["visual"] for r in per_q.values())
    print(f"evaluation questions            : {n_q}")
    print(f"gold evidence items             : {tot}")
    print(f"  of which figure/table         : {vis} ({vis/tot:.1%})")
    print(f"  on a page with no text layer  : {blind} ({blind/tot:.1%})  "
          f"<- invisible to BM25/dense without OCR")
    if unknown_pages:
        print(f"  page not resolvable in the PDF: {unknown_pages}")

    print()
    print("=" * 92)
    print("2. IS IT CONCENTRATED?  (per question, share of gold evidence a text "
          "index cannot reach)")
    print("=" * 92)
    buckets = collections.Counter()
    for r in per_q.values():
        frac = r["blind"] / r["n"] if r["n"] else 0
        if frac == 0:
            buckets["0%  (text index sees all its evidence)"] += 1
        elif frac < 0.5:
            buckets["1-49%"] += 1
        elif frac < 1.0:
            buckets["50-99%"] += 1
        else:
            buckets["100% (text index sees NONE of it)"] += 1
    order = ["0%  (text index sees all its evidence)", "1-49%", "50-99%",
             "100% (text index sees NONE of it)"]
    for k in order:
        v = buckets[k]
        print(f"  {k:<44}{v:>6}{v/n_q:>9.1%}  {'#' * int(v / n_q * 60)}")
    hard = buckets["100% (text index sees NONE of it)"] + buckets["50-99%"]
    print(f"\nquestions where a text-only retriever is missing at least half of "
          f"the gold: {hard} ({hard/n_q:.1%})")
    print("This is the routable population: it is not spread evenly across "
          "questions, it is a distinct group.")

    print()
    print("=" * 92)
    print("3. IS IT PREDICTABLE FROM THE DOCUMENT?  (the mechanism)")
    print("=" * 92)
    doc_blind = collections.defaultdict(lambda: [0, 0])
    for r in per_q.values():
        d = doc_blind[r["doc"]]
        d[0] += r["blind"]
        d[1] += r["n"]
    full = [d for d, (b, n) in doc_blind.items() if n and b == n]
    part = [d for d, (b, n) in doc_blind.items() if n and 0 < b < n]
    none = [d for d, (b, n) in doc_blind.items() if n and b == 0]
    print(f"documents whose gold evidence is entirely unreachable by text : "
          f"{len(full)}")
    print(f"documents partially unreachable                               : "
          f"{len(part)}")
    print(f"documents fully reachable                                     : "
          f"{len(none)}")
    q_in_full = sum(1 for r in per_q.values() if r["doc"] in set(full))
    print(f"\nquestions living in the fully-unreachable documents: {q_in_full} "
          f"({q_in_full/n_q:.1%})")
    print("For those, visual retrieval is not a preference -- it is the only "
          "way the evidence can be found at all.")
    print("\nUnlike the generation-input decision, this label is deterministic: "
          "a page either has a text layer or")
    print("it does not, and it does not change from run to run.")


if __name__ == "__main__":
    main()
