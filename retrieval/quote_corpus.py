"""Build a realistic-scale, self-built quote-level corpus from the 220 PDFs.

Why this exists
---------------
Every quote-granularity result so far ran on `canonical_evidence`, which is the
union of the questions' candidate lists. That pool holds 86 text and 29 image
quotes per document against the paper's 536 and 63 -- 16% of the text side and
46% of the image side -- and every item is in it only because it was some
question's gold or hard negative. E19, the budget-allocation experiment, is the
result most sensitive to that: the optimal text/image split depends directly on
the pool's composition, and the sampled pool is 3.2:1 where the real one is
8.5:1.

Fixing the dominant half means building the text side ourselves at full scale.

Chunking
--------
PyMuPDF's raw blocks are over-segmented for this purpose: 16 per page with a
median of 66 characters, where the official quotes run about 280. So blocks are
merged greedily in reading order up to a target size, breaking early on a large
vertical gap (a real layout boundary) rather than mid-paragraph.

`--target-chars` is deliberately a parameter and not a constant: sweeping it is
exactly the granularity axis RQ3 needs, so the same builder serves Phase 4.

Pages with no text layer contribute their cached OCR text instead, chunked to
the same target.

Gold mapping
------------
Self-built chunks carry no official `layout_id`, so gold is transferred by the
character 8-gram matcher Gate 2 validated at 98.63%: each official gold text
quote is assigned to the chunk covering the most of its shingles. Coverage is
reported rather than assumed, and a quote whose best chunk covers too little is
recorded as unmapped instead of being silently attached.

    ASYMMETRY, STATED. Only the text side is rebuilt. Image quotes stay as the
    official 6,565 with their VLM descriptions, because a self-built image
    region would have no text representation at all and would distort the pool
    in a different direction. The result is a pool of roughly 18:1 text:image
    against the true 8.5:1 -- so this corpus and the canonical one bracket the
    real composition from either side, which makes running the allocation
    experiment on both more informative than either alone.

Run:
    python -m retrieval.quote_corpus
    python -m retrieval.quote_corpus --target-chars 800 --out retrieval/quotes_coarse.sqlite
"""

import argparse
import os
import sqlite3
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from canonical.gate2 import normalize as g2_normalize, shingles  # noqa: E402
from retrieval.corpus import normalize, tokenize                 # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PDF_ROOT = r"D:\Dataset\MMDocRAG\doc_pdfs\doc_pdfs"
DEFAULT_DB = os.path.join(REPO_ROOT, "canonical", "mmdocrag.sqlite")
DEFAULT_OCR = os.path.join(REPO_ROOT, "canonical", "ocr_cache.sqlite")
DEFAULT_OUT = os.path.join(REPO_ROOT, "retrieval", "quotes.sqlite")

TARGET_CHARS = 300      # median official text quote is ~280 characters
GAP_RATIO = 1.8         # vertical gap this many times the median line gap = break
MIN_CHARS = 40          # below this a chunk is a header or stray artefact
COVER_MIN = 0.50        # a gold quote must be at least half covered to map

SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id   TEXT PRIMARY KEY,          -- doc:page:index
    doc_name   TEXT NOT NULL,
    page_id    INTEGER NOT NULL,
    idx        INTEGER NOT NULL,
    text       TEXT,
    n_chars    INTEGER,
    n_tok      INTEGER,
    source     TEXT                        -- 'layer' or 'ocr'
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks (doc_name);

CREATE TABLE IF NOT EXISTS gold_map (
    evidence_id TEXT PRIMARY KEY,          -- official gold text evidence
    chunk_id    TEXT,                      -- best-covering self-built chunk
    coverage    REAL,
    n_chunks_50 INTEGER                    -- how many chunks cover >=50% of it
);
"""


def page_chunks(page, target, gap_ratio=GAP_RATIO):
    """Merge PyMuPDF blocks in reading order into ~target-sized chunks."""
    blocks = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        txt = " ".join(s["text"] for l in b.get("lines", []) for s in l.get("spans", []))
        txt = txt.strip()
        if txt:
            blocks.append((b["bbox"], txt))
    if not blocks:
        return []
    blocks.sort(key=lambda x: (round(x[0][1], 1), x[0][0]))   # top-to-bottom

    gaps = [blocks[i][0][1] - blocks[i - 1][0][3] for i in range(1, len(blocks))]
    med_gap = sorted(g for g in gaps if g >= 0)
    med_gap = med_gap[len(med_gap) // 2] if med_gap else 0.0
    brk = max(med_gap * gap_ratio, 6.0)

    out, cur, prev_bottom = [], [], None
    for (x0, y0, x1, y1), txt in blocks:
        big_gap = prev_bottom is not None and (y0 - prev_bottom) > brk
        if cur and (big_gap or sum(len(t) for t in cur) >= target):
            out.append(" ".join(cur))
            cur = []
        cur.append(txt)
        prev_bottom = y1
    if cur:
        out.append(" ".join(cur))
    return [c for c in (s.strip() for s in out) if len(c) >= MIN_CHARS]


def split_text(text, target):
    """Chunk a flat string (OCR output has no layout to respect)."""
    words, out, cur = text.split(), [], []
    for w in words:
        cur.append(w)
        if sum(len(x) + 1 for x in cur) >= target:
            out.append(" ".join(cur))
            cur = []
    if cur:
        out.append(" ".join(cur))
    return [c for c in out if len(c) >= MIN_CHARS]


def build(pdf_root, ocr_db, out_path, target):
    import pymupdf

    ocr = {}
    if os.path.exists(ocr_db):
        c = sqlite3.connect(ocr_db)
        ocr = {(d, p): t or "" for d, p, t in
               c.execute("SELECT doc_name, page_id, text FROM ocr_pages")}
        c.close()
    print(f"OCR cache: {len(ocr)} pages")

    if os.path.exists(out_path):
        os.remove(out_path)
    con = sqlite3.connect(out_path)
    con.executescript(SCHEMA)

    names = sorted(n for n in os.listdir(pdf_root) if n.lower().endswith(".pdf"))
    rows, n_ocr_pages = [], 0
    for i, name in enumerate(names, 1):
        doc_name = name[:-4]
        try:
            d = pymupdf.open(os.path.join(pdf_root, name))
        except Exception as exc:
            print(f"[warn] {doc_name}: {exc}")
            continue
        idx = 0
        for pid in range(d.page_count):
            cs = page_chunks(d[pid], target)
            src = "layer"
            if not cs:
                recognised = ocr.get((doc_name, pid), "")
                if recognised:
                    cs, src, n_ocr_pages = split_text(recognised, target), "ocr", n_ocr_pages + 1
            for c in cs:
                t = normalize(c)
                rows.append((f"{doc_name}:{pid}:{idx}", doc_name, pid, idx,
                             t, len(t), len(tokenize(t)), src))
                idx += 1
        d.close()
        if len(rows) >= 5000:
            con.executemany("INSERT OR REPLACE INTO chunks VALUES (?,?,?,?,?,?,?,?)", rows)
            con.commit()
            rows = []
        if i % 50 == 0:
            print(f"  {i}/{len(names)} pdfs", flush=True)
    if rows:
        con.executemany("INSERT OR REPLACE INTO chunks VALUES (?,?,?,?,?,?,?,?)", rows)
    con.commit()

    n, docs, avg, med = con.execute(
        "SELECT COUNT(*), COUNT(DISTINCT doc_name), AVG(n_chars), "
        "(SELECT n_chars FROM chunks ORDER BY n_chars "
        " LIMIT 1 OFFSET (SELECT COUNT(*) FROM chunks)/2) FROM chunks").fetchone()
    print(f"\nchunks {n} over {docs} documents  ->  {n/docs:.0f}/doc")
    print(f"  chars: mean {avg:.0f}, median {med}   (official text quotes: ~280)")
    print(f"  pages served by OCR: {n_ocr_pages}")
    return con


def map_gold(con, db_path, cover_min=COVER_MIN):
    """Transfer official gold text evidence onto self-built chunks."""
    src = sqlite3.connect(db_path)
    gold = src.execute("""
        SELECT DISTINCT e.evidence_id, e.doc_name, e.page_id, e.text
        FROM canonical_evidence e
        WHERE e.type = 'text' AND e.text IS NOT NULL AND e.text <> ''
          AND e.evidence_id IN (SELECT evidence_id FROM question_gold_evidence)
    """).fetchall()
    src.close()
    print(f"\nmapping {len(gold)} official gold text quotes onto chunks...")

    by_doc = {}
    for cid, doc, pid, text in con.execute(
            "SELECT chunk_id, doc_name, page_id, text FROM chunks"):
        by_doc.setdefault(doc, []).append((cid, pid, shingles(g2_normalize(text))))

    out, unmapped, spans = [], 0, 0
    for eid, doc, pid, text in gold:
        gsh = shingles(g2_normalize(text))
        if not gsh:
            unmapped += 1
            continue
        cands = by_doc.get(doc, [])
        # Same page first: page_id is the reliable anchor. Fall back to the whole
        # document, because a quote occasionally sits one page off.
        best, best_cov, n50 = None, 0.0, 0
        for scope in ([c for c in cands if c[1] == pid], cands):
            for cid, _, csh in scope:
                cov = len(gsh & csh) / len(gsh)
                if cov >= 0.5:
                    n50 += 1
                if cov > best_cov:
                    best, best_cov = cid, cov
            if best_cov >= cover_min:
                break
        if best_cov >= cover_min:
            out.append((eid, best, round(best_cov, 4), n50))
            if n50 > 1:
                spans += 1
        else:
            out.append((eid, None, round(best_cov, 4), n50))
            unmapped += 1

    con.executemany("INSERT OR REPLACE INTO gold_map VALUES (?,?,?,?)", out)
    con.commit()
    n = len(out)
    print(f"  mapped   : {n - unmapped}/{n} ({(n - unmapped)/n:.2%}) at coverage >= {cover_min}")
    print(f"  unmapped : {unmapped}")
    print(f"  gold quotes spanning >1 chunk: {spans} "
          f"({spans/n:.1%})  -- chunk size is near quote size, so this stays small")
    covs = sorted(c for _, _, c, _ in out)
    print(f"  coverage percentiles: p05={covs[len(covs)//20]:.2f} "
          f"p25={covs[len(covs)//4]:.2f} median={covs[len(covs)//2]:.2f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pdf-root", default=DEFAULT_PDF_ROOT)
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--ocr-db", default=DEFAULT_OCR)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--target-chars", type=int, default=TARGET_CHARS,
                    help="chunk size target; sweeping this is the RQ3 granularity axis")
    ap.add_argument("--no-gold-map", action="store_true",
                    help="skip gold transfer. retrieval/eval_granularity.py scores "
                         "coverage against the official gold directly and never "
                         "reads gold_map, so the sweep arms do not need it -- and "
                         "at very fine targets the mapping is both the slow step "
                         "and a misleading number, since no single small chunk can "
                         "cover half of a 334-character quote")
    args = ap.parse_args()
    con = build(args.pdf_root, args.ocr_db, args.out, args.target_chars)
    if not args.no_gold_map:
        map_gold(con, args.db)
    con.close()
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
