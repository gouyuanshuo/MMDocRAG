"""Build the page-level retrieval corpus from the 220 source PDFs.

Why the page is the unit
------------------------
Gold evidence is annotated at `(doc_name, page_id, layout_id)`, but `layout_id`
is an artefact of the authors' MinerU run and cannot be reproduced from the PDF
-- self-built chunks only align to gold by fuzzy text matching (Gate 2). The
page, by contrast, is exact: `page_id` was verified 0-indexed with no
out-of-range values, so "did the retriever return the page hosting this gold
evidence" is a question with an unambiguous answer.

It is also the unit the comparable literature evaluates. MMDocIR Task 1 is
multimodal *page* retrieval; M3DocRAG, MoLoRAG and MMLongBench-Doc all retrieve
pages. Reporting page recall keeps this project's numbers on the same axis as
theirs. Finer granularity is Phase 4's subject, and it builds on this layer
rather than replacing it.

Page text = embedded text layer + OCR, concatenated
---------------------------------------------------
Same rule as canonical/gate2.py. A page can carry a thin text layer (a running
header) while its real content sits in a figure only OCR can read, so replacing
one with the other loses evidence either way. The OCR cache only contains pages
canonical.ocr judged text-poor, so its mere presence is the condition to append.

Run:
    python -m retrieval.corpus
    python -m retrieval.corpus --no-ocr      # text-layer-only ablation
"""

import argparse
import os
import re
import sqlite3
import sys
import unicodedata

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PDF_ROOT = r"D:\Dataset\MMDocRAG\doc_pdfs\doc_pdfs"
DEFAULT_OCR_DB = os.path.join(REPO_ROOT, "canonical", "ocr_cache.sqlite")
DEFAULT_OUT = os.path.join(REPO_ROOT, "retrieval", "pages.sqlite")

SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    doc_name   TEXT    NOT NULL,
    page_id    INTEGER NOT NULL,
    text       TEXT,               -- normalised, tokeniser-ready
    n_tok      INTEGER,
    layer_len  INTEGER,            -- chars from the PDF's own text layer
    ocr_len    INTEGER,            -- chars added by OCR (0 if none)
    PRIMARY KEY (doc_name, page_id)
);
CREATE INDEX IF NOT EXISTS idx_pages_doc ON pages (doc_name);
"""

_LATEX = re.compile(r"\\[a-zA-Z]+")
_WS = re.compile(r"\s+")
# Keep alphanumerics and the interior punctuation that carries meaning in these
# documents: 10-K item numbers, decimals, hyphenated compounds.
_TOKEN = re.compile(r"[a-z0-9]+(?:[.\-][a-z0-9]+)*")


def normalize(s):
    """NFKC, strip LaTeX commands MinerU emits, collapse whitespace, lowercase."""
    s = unicodedata.normalize("NFKC", s)
    s = _LATEX.sub(" ", s)
    return _WS.sub(" ", s).strip().lower()


def tokenize(s):
    return _TOKEN.findall(s)


def load_ocr(path):
    if not os.path.exists(path):
        return {}
    con = sqlite3.connect(path)
    out = {(d, p): t or "" for d, p, t in
           con.execute("SELECT doc_name, page_id, text FROM ocr_pages")}
    con.close()
    return out


def build(pdf_root, ocr_db, out_path, use_ocr=True):
    import pymupdf

    ocr = load_ocr(ocr_db) if use_ocr else {}
    print(f"OCR cache: {len(ocr)} pages" if ocr else "OCR NOT used (ablation)")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    con = sqlite3.connect(out_path)
    con.executescript(SCHEMA)

    names = sorted(n for n in os.listdir(pdf_root) if n.lower().endswith(".pdf"))
    rows, n_pages, n_ocr_used, empty = [], 0, 0, 0
    for i, name in enumerate(names, 1):
        doc_name = name[:-4]
        try:
            doc = pymupdf.open(os.path.join(pdf_root, name))
        except Exception as exc:
            print(f"[warn] {doc_name}: cannot open ({exc}), skipped")
            continue
        for pid in range(doc.page_count):
            layer = doc[pid].get_text()
            extra = ocr.get((doc_name, pid), "")
            if extra:
                n_ocr_used += 1
            text = normalize(layer + "\n" + extra if extra else layer)
            toks = tokenize(text)
            if not toks:
                empty += 1
            rows.append((doc_name, pid, text, len(toks),
                         len(layer.strip()), len(extra.strip())))
            n_pages += 1
        doc.close()
        if len(rows) >= 2000:
            con.executemany("INSERT OR REPLACE INTO pages VALUES (?,?,?,?,?,?)", rows)
            con.commit()
            rows = []
        if i % 50 == 0:
            print(f"  {i}/{len(names)} pdfs, {n_pages} pages", flush=True)
    if rows:
        con.executemany("INSERT OR REPLACE INTO pages VALUES (?,?,?,?,?,?)", rows)
    con.commit()

    tot, docs, mean_tok = con.execute(
        "SELECT COUNT(*), COUNT(DISTINCT doc_name), AVG(n_tok) FROM pages").fetchone()
    thin = con.execute("SELECT COUNT(*) FROM pages WHERE n_tok < 20").fetchone()[0]
    print(f"\ncorpus: {docs} documents, {tot} pages")
    print(f"  pages augmented by OCR : {n_ocr_used}")
    print(f"  mean tokens per page   : {mean_tok:.0f}")
    print(f"  pages with < 20 tokens : {thin} ({thin/tot:.1%})")
    print(f"  pages with no tokens   : {empty}")
    print(f"wrote {out_path}")
    con.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pdf-root", default=DEFAULT_PDF_ROOT)
    ap.add_argument("--ocr-db", default=DEFAULT_OCR_DB)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--no-ocr", action="store_true",
                    help="build from the PDF text layer alone, for the ablation "
                         "that shows what OCR is worth to retrieval")
    args = ap.parse_args()
    build(args.pdf_root, args.ocr_db, args.out, use_ocr=not args.no_ocr)


if __name__ == "__main__":
    main()
