"""OCR the figure and table crops, so image quotes have a text surrogate we built.

The release stores each image quote with a VLM-written description
(`img_description`), but not the OCR text the paper also used -- that arm exists
in their response files and nowhere else. Without it there is no way to ask the
question this project needs answered:

    How much of an image quote's retrievability comes from *understanding* the
    figure, versus merely reading the characters printed on it?

That question matters because Phase 1B found no modality gap at page
granularity: a figure sits on a text-rich page, so BM25 finds the page through
the surrounding prose. At quote granularity the figure is cut away from that
prose and has to stand on its own text surrogate. If the VLM description
retrieves far better than the OCR of the same crop, then visual understanding
carries retrievable information that character extraction does not -- which is
the mechanism that would make a visual retriever (ColPali/ColQwen) worth its
cost, and the mechanism RQ1b rests on.

Spot-checking the two surrogates on the same crops shows the shape of it: a
chart whose OCR reads "68M C6M USA C4M Europe 2M" has a description reading
"comparison chart showing early-stage entry valuations for venture capital
investments"; an icon OCRs to nothing at all.

Resumable, cached by evidence_id. Run:
    python -m retrieval.ocr_quotes
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
DEFAULT_OUT = os.path.join(REPO_ROOT, "retrieval", "quote_ocr.sqlite")
DEFAULT_IMG_ROOT = r"D:\Dataset\MMDocRAG\images"

SCHEMA = """
CREATE TABLE IF NOT EXISTS quote_ocr (
    evidence_id TEXT PRIMARY KEY,
    img_path    TEXT,
    text        TEXT,
    chars       INTEGER,
    seconds     REAL,
    created     TEXT
);
"""


def targets(db_path):
    con = sqlite3.connect(db_path)
    rows = con.execute(
        "SELECT evidence_id, img_path FROM canonical_evidence "
        "WHERE type <> 'text' AND img_path IS NOT NULL AND img_path <> '' "
        "ORDER BY evidence_id").fetchall()
    con.close()
    return rows


def run(rows, img_root, out_path):
    from rapidocr_onnxruntime import RapidOCR

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    con = sqlite3.connect(out_path)
    con.executescript(SCHEMA)
    done = {r[0] for r in con.execute("SELECT evidence_id FROM quote_ocr")}
    todo = [r for r in rows if r[0] not in done]
    print(f"image quotes {len(rows)}, cached {len(rows) - len(todo)}, to OCR {len(todo)}")
    if not todo:
        con.close()
        return

    ocr = RapidOCR()
    started, written, missing = time.time(), 0, 0
    for i, (eid, path) in enumerate(todo, 1):
        full = os.path.join(img_root, path.replace("/", os.sep))
        t0 = time.time()
        if not os.path.exists(full):
            missing += 1
            text = ""
        else:
            try:
                result, _ = ocr(full)
                text = " ".join(line[1] for line in result) if result else ""
            except Exception:
                # A handful of crops are degenerate (1px strips, CMYK). Record
                # the empty result rather than aborting a multi-hour run.
                text = ""
        con.execute("INSERT OR REPLACE INTO quote_ocr VALUES (?,?,?,?,?,?)",
                    (eid, path, text, len(text), round(time.time() - t0, 2),
                     time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
        written += 1
        if written % 100 == 0:
            con.commit()
            rate = (time.time() - started) / i
            print(f"  {i}/{len(todo)}  {rate:.2f}s/img  "
                  f"eta {rate * (len(todo) - i) / 60:.1f} min", flush=True)
    con.commit()

    n, empty, med = con.execute(
        "SELECT COUNT(*), SUM(chars = 0), "
        "(SELECT chars FROM quote_ocr ORDER BY chars "
        " LIMIT 1 OFFSET (SELECT COUNT(*) FROM quote_ocr)/2) FROM quote_ocr").fetchone()
    total = time.time() - started
    print(f"\ndone: {written} crops in {total/60:.1f} min ({total/written:.2f}s each)")
    print(f"cached {n} total; {empty} produced no text ({empty/n:.1%}); "
          f"median {med} chars")
    if missing:
        print(f"[warn] {missing} image file(s) not found on disk")
    con.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--img-root", default=DEFAULT_IMG_ROOT)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    rows = targets(args.db)
    run(rows[:args.limit] if args.limit else rows, args.img_root, args.out)


if __name__ == "__main__":
    main()
