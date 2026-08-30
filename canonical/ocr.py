"""OCR the PDF pages that carry no extractable text layer.

Why
---
PyMuPDF only reads a PDF's embedded text. 1,606 of the corpus's 14,763 pages
(10.9%) have none -- 28 documents are image-only slide decks end to end. The
benchmark authors ran MinerU, which includes OCR, so their gold evidence covers
text we cannot otherwise see. Gate 2 stalls at 94.28% for exactly this reason:
of its 180 unmatched items, 148 sit on pages with no text layer and only 32 are
genuine matching failures.

This module fills that gap with RapidOCR (ONNX, CPU, no external binary) and
caches the result so pages are never OCR'd twice.

Targets
-------
    --targets gate2   pages hosting gold text evidence and lacking a text layer
                      (128 pages / 26 docs -- enough to re-run Gate 2)
    --targets all     every page in the corpus lacking a text layer
                      (~1,606 pages -- needed before Phase 1B text retrieval,
                      since without it 28 documents are invisible to BM25/dense)

Run:
    python -m canonical.ocr --targets gate2
    python -m canonical.ocr --targets all --dpi 200
"""

import argparse
import os
import sqlite3
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO_ROOT, "canonical", "mmdocrag.sqlite")
DEFAULT_OCR_DB = os.path.join(REPO_ROOT, "canonical", "ocr_cache.sqlite")
DEFAULT_PDF_ROOT = r"D:\Dataset\MMDocRAG\doc_pdfs\doc_pdfs"

# A page with fewer than this many extractable characters is treated as having
# no usable text layer. Pure-image pages usually yield 0; a stray header or
# page number can leave a handful.
#
# 20 is the Gate 2 setting: it isolates pages whose gold evidence PyMuPDF
# genuinely cannot see. Phase 1B wants a higher bar (--min-chars 100). A page
# carrying only a running header enters a BM25/dense index as an effectively
# empty document, which is worse than not indexing it: it dilutes term
# statistics and can still be retrieved. Measured over the 14,763-page corpus,
# raising the bar from 20 to 100 adds 377 pages (1,606 -> 1,983).
TEXT_LAYER_MIN = 20

OCR_SCHEMA = """
CREATE TABLE IF NOT EXISTS ocr_pages (
    doc_name   TEXT NOT NULL,
    page_id    INTEGER NOT NULL,
    dpi        INTEGER NOT NULL,
    engine     TEXT NOT NULL,
    text       TEXT,
    chars      INTEGER,
    seconds    REAL,
    created    TEXT,
    PRIMARY KEY (doc_name, page_id)
);
"""


def open_cache(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(OCR_SCHEMA)
    return con


def cached_pages(con):
    return {(d, p) for d, p in con.execute("SELECT doc_name, page_id FROM ocr_pages")}


def gate2_targets(db_path, pdf_root, min_chars=TEXT_LAYER_MIN):
    """(doc, page) pairs that host gold text evidence but have no text layer."""
    import pymupdf
    con = sqlite3.connect(db_path)
    rows = con.execute("""
        SELECT DISTINCT e.doc_name, e.page_id
        FROM canonical_evidence e
        WHERE e.type = 'text'
          AND e.evidence_id IN (SELECT evidence_id FROM question_gold_evidence)
        ORDER BY e.doc_name, e.page_id
    """).fetchall()
    con.close()

    targets, current, doc = [], None, None
    for doc_name, page_id in rows:
        if doc_name != current:
            if doc:
                doc.close()
            current, doc = doc_name, None
            path = os.path.join(pdf_root, f"{doc_name}.pdf")
            if os.path.exists(path):
                try:
                    doc = pymupdf.open(path)
                except Exception:
                    doc = None
        if doc is None or page_id >= doc.page_count:
            continue
        if len(doc[page_id].get_text().strip()) < min_chars:
            targets.append((doc_name, page_id))
    if doc:
        doc.close()
    return targets


def all_targets(pdf_root, min_chars=TEXT_LAYER_MIN):
    """Every page in the corpus with no text layer."""
    import pymupdf
    targets = []
    for name in sorted(os.listdir(pdf_root)):
        if not name.lower().endswith(".pdf"):
            continue
        try:
            doc = pymupdf.open(os.path.join(pdf_root, name))
        except Exception:
            continue
        for page_id in range(doc.page_count):
            if len(doc[page_id].get_text().strip()) < min_chars:
                targets.append((name[:-4], page_id))
        doc.close()
    return targets


def run_ocr(targets, pdf_root, ocr_db, dpi, engine_name="rapidocr"):
    import pymupdf
    from rapidocr_onnxruntime import RapidOCR

    con = open_cache(ocr_db)
    done = cached_pages(con)
    todo = [t for t in targets if t not in done]
    print(f"targets {len(targets)}, already cached {len(targets) - len(todo)}, "
          f"to OCR {len(todo)}")
    if not todo:
        con.close()
        return 0, 0.0

    ocr = RapidOCR()
    started = time.time()
    current, doc = None, None
    written = 0

    for i, (doc_name, page_id) in enumerate(todo, 1):
        if doc_name != current:
            if doc:
                doc.close()
            current = doc_name
            doc = pymupdf.open(os.path.join(pdf_root, f"{doc_name}.pdf"))

        t0 = time.time()
        png = doc[page_id].get_pixmap(dpi=dpi).tobytes("png")
        result, _ = ocr(png)
        text = "\n".join(line[1] for line in result) if result else ""
        elapsed = time.time() - t0

        con.execute(
            "INSERT OR REPLACE INTO ocr_pages VALUES (?,?,?,?,?,?,?,?)",
            (doc_name, page_id, dpi, engine_name, text, len(text), round(elapsed, 2),
             time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
        written += 1
        # Commit as we go: OCR runs long enough that an interrupted job should
        # not throw away everything before it.
        if written % 20 == 0:
            con.commit()
            rate = (time.time() - started) / i
            eta = rate * (len(todo) - i)
            print(f"  {i}/{len(todo)}  {rate:.1f}s/page  eta {eta / 60:.1f} min",
                  flush=True)

    con.commit()
    if doc:
        doc.close()
    total = time.time() - started
    empty = con.execute("SELECT COUNT(*) FROM ocr_pages WHERE chars = 0").fetchone()[0]
    median = con.execute(
        "SELECT chars FROM ocr_pages ORDER BY chars LIMIT 1 OFFSET "
        "(SELECT COUNT(*) FROM ocr_pages) / 2").fetchone()
    print(f"done: {written} pages in {total / 60:.1f} min "
          f"({total / written:.1f}s/page); {empty} produced no text; "
          f"median {median[0] if median else 0} chars/page")
    con.close()
    return written, total


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--targets", choices=["gate2", "all"], default="gate2")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--ocr-db", default=DEFAULT_OCR_DB)
    ap.add_argument("--pdf-root", default=DEFAULT_PDF_ROOT)
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--min-chars", dest="min_chars", type=int, default=TEXT_LAYER_MIN,
                    help="OCR pages whose text layer is shorter than this "
                         "(20 = Gate 2, 100 = Phase 1B indexing)")
    ap.add_argument("--limit", type=int, default=0, help="cap pages, for a trial run")
    args = ap.parse_args()

    print(f"scanning for pages with a text layer shorter than {args.min_chars} chars")
    if args.targets == "gate2":
        targets = gate2_targets(args.db, args.pdf_root, args.min_chars)
    else:
        targets = all_targets(args.pdf_root, args.min_chars)
    if args.limit:
        targets = targets[:args.limit]

    run_ocr(targets, args.pdf_root, args.ocr_db, args.dpi)


if __name__ == "__main__":
    main()
