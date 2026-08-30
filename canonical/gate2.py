"""Gate 2: can self-parsed PDF text be aligned back to the official gold evidence?

Why this gate exists
--------------------
Gold evidence is pinned to (page_id, layout_id) from the benchmark authors' own
MinerU run. layout_id is an artefact of that run: parsing the PDFs ourselves
produces different blocks with different numbering, so there is no id to join
on. Any self-built chunking (Phase 4 granularity work) can therefore only be
labelled against gold by matching *text*, anchored on page_id -- which the
audit confirmed is 0-indexed and never out of bounds.

If this gate fails, Phase 4 must fall back to using the official quotes as the
retrieval unit and the granularity experiments narrow accordingly. So it has to
be answered before any chunking work starts.

Method
------
For every gold text evidence item, extract the text of its PDF page with
PyMuPDF, normalise both sides down to a bare alphanumeric character stream, and
ask whether the gold string appears inside the page. Normalising away
whitespace and punctuation is deliberate: MinerU emits LaTeX wrappers such as
`$(52\\%)$` and drops spaces ("tome,andought"), and a raw comparison would fail
on formatting noise rather than on genuine misalignment.

Failures fall back to neighbouring pages and then the whole document, which
distinguishes "we cannot find this text at all" from "page_id is off by one".

Run:
    python -m canonical.gate2
    python -m canonical.gate2 --limit 200 --pdf-root D:/Dataset/MMDocRAG/doc_pdfs/doc_pdfs
"""

import argparse
import collections
import difflib
import json
import os
import random
import re
import sqlite3
import sys
import unicodedata

# Failure examples quote raw PDF text, which routinely contains characters the
# Windows console codepage cannot encode.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO_ROOT, "canonical", "mmdocrag.sqlite")
DEFAULT_PDF_ROOT = r"D:\Dataset\MMDocRAG\doc_pdfs\doc_pdfs"

# MinerU wraps numbers and symbols in LaTeX: "$(52\%)$", "$\mathbf{46}$".
_LATEX_CMD = re.compile(r"\\[a-zA-Z]+")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# A short gold string can match by accident, so hits are reported split by
# length as well as in aggregate.
SHORT_LEN = 40

# Exact containment is far too brittle here. MinerU hallucinates glyphs into
# the gold text -- one observed item renders "62%" as
# "$\mathbf{\mathcal{G}}_{62}\%$", injecting a stray "G" -- and a single bad
# character anywhere in a 280-character string breaks a substring test
# outright. Character n-gram overlap degrades gracefully instead: one corrupt
# character costs only the N shingles that span it.
SHINGLE_N = 8


def normalize(s):
    """Reduce text to a bare lowercase alphanumeric stream."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = _LATEX_CMD.sub(" ", s)
    s = s.lower()
    return _NON_ALNUM.sub("", s)


def shingles(s, n=SHINGLE_N):
    if not s:
        return frozenset()
    if len(s) <= n:
        return frozenset({s})
    return frozenset(s[i:i + n] for i in range(len(s) - n + 1))


def coverage(gold_sh, page_sh):
    """Fraction of the gold's n-grams present in the candidate text."""
    if not gold_sh:
        return 0.0
    return len(gold_sh & page_sh) / len(gold_sh)


class OcrCache:
    """Read-only view of the OCR text produced by `python -m canonical.ocr`."""

    def __init__(self, path):
        self.rows = {}
        if not path or not os.path.exists(path):
            return
        con = sqlite3.connect(path)
        try:
            for doc_name, page_id, text in con.execute(
                    "SELECT doc_name, page_id, text FROM ocr_pages"):
                self.rows[(doc_name, page_id)] = text or ""
        except sqlite3.OperationalError:
            pass  # cache exists but has not been populated yet
        con.close()

    def get(self, doc_name, page_id):
        return self.rows.get((doc_name, page_id), "")

    def __len__(self):
        return len(self.rows)


class PdfText:
    """Lazily extracted, cached per-page text and shingles for one document.

    Pages with no embedded text layer fall back to the OCR cache, so a scanned
    page is compared against recognised text rather than an empty string.
    """

    def __init__(self, path, doc_name=None, ocr=None):
        import pymupdf
        self.doc = pymupdf.open(path)
        self.doc_name = doc_name
        self.ocr = ocr
        self.page_count = self.doc.page_count
        self._pages = {}
        self._shingles = {}
        self._all_sh = None
        self.ocr_used = set()

    def page(self, idx):
        if idx < 0 or idx >= self.page_count:
            return ""
        if idx not in self._pages:
            raw = self.doc[idx].get_text()
            if self.ocr is not None:
                recognised = self.ocr.get(self.doc_name, idx)
                if recognised:
                    # Concatenate rather than replace. A page can carry a thin
                    # text layer -- a running header, a page number -- while its
                    # real content sits in a figure only OCR can read. Replacing
                    # would throw away the header text that some gold evidence is
                    # actually drawn from. No threshold is applied here: the
                    # cache only contains pages that canonical.ocr already judged
                    # to have too little text, so its presence is the condition.
                    raw = raw + "\n" + recognised
                    self.ocr_used.add(idx)
            self._pages[idx] = normalize(raw)
        return self._pages[idx]

    def page_shingles(self, idx):
        if idx < 0 or idx >= self.page_count:
            return frozenset()
        if idx not in self._shingles:
            self._shingles[idx] = shingles(self.page(idx))
        return self._shingles[idx]

    def whole_shingles(self):
        if self._all_sh is None:
            acc = set()
            for i in range(self.page_count):
                acc |= self.page_shingles(i)
            self._all_sh = frozenset(acc)
        return self._all_sh

    def close(self):
        self.doc.close()


def gold_text_rows(con, limit, seed):
    rows = con.execute("""
        SELECT e.evidence_id, e.doc_name, e.page_id, e.layout_id, e.text
        FROM canonical_evidence e
        WHERE e.type = 'text'
          AND e.evidence_id IN (SELECT evidence_id FROM question_gold_evidence)
        ORDER BY e.doc_name, e.page_id, e.evidence_id
    """).fetchall()
    if limit and limit < len(rows):
        random.Random(seed).shuffle(rows)
        rows = rows[:limit]
    # Group by document so each PDF is opened exactly once.
    rows.sort(key=lambda r: (r[1], r[2]))
    return rows


def run(db_path, pdf_root, limit, seed, neighbours, examples, overlap, ocr_db):
    con = sqlite3.connect(db_path)
    rows = gold_text_rows(con, limit, seed)
    ocr = OcrCache(ocr_db)
    if len(ocr):
        print(f"[ocr] {len(ocr)} cached page(s) available from {ocr_db}")
    else:
        print("[ocr] no OCR cache; scanned pages will score as empty")

    stats = collections.Counter()
    fail_examples = []
    offset_hist = collections.Counter()
    empty_pages = 0
    ratios = []

    current_doc, pdf = None, None
    missing_pdf = set()

    for eid, doc_name, page_id, layout_id, text in rows:
        if doc_name != current_doc:
            if pdf:
                pdf.close()
            current_doc, pdf = doc_name, None
            path = os.path.join(pdf_root, f"{doc_name}.pdf")
            if os.path.exists(path):
                try:
                    pdf = PdfText(path, doc_name=doc_name, ocr=ocr)
                except Exception as exc:  # corrupt / unreadable PDF
                    stats["pdf_error"] += 1
                    missing_pdf.add(f"{doc_name} ({exc})")
            else:
                missing_pdf.add(doc_name)

        if pdf is None:
            stats["no_pdf"] += 1
            continue

        gold = normalize(text)
        stats["total"] += 1
        if not gold:
            stats["empty_gold"] += 1
            continue

        bucket = "short" if len(gold) < SHORT_LEN else "long"
        gold_sh = shingles(gold)
        page = pdf.page(page_id)
        if not page:
            empty_pages += 1

        from_ocr = page_id in pdf.ocr_used
        if from_ocr:
            stats["page_from_ocr"] += 1
        cov = coverage(gold_sh, pdf.page_shingles(page_id))
        where, offset = "exact_page", 0

        if cov < overlap:
            # page_id off by a little? Search outward, nearest first.
            for delta in range(1, neighbours + 1):
                for cand in (page_id - delta, page_id + delta):
                    c = coverage(gold_sh, pdf.page_shingles(cand))
                    if c > cov:
                        cov, where, offset = c, "neighbour_page", cand - page_id
                if cov >= overlap:
                    break

        if cov < overlap:
            c = coverage(gold_sh, pdf.whole_shingles())
            if c > cov:
                cov, where, offset = c, "elsewhere_in_doc", "far"

        ratios.append(cov)
        if cov >= overlap:
            stats[f"hit_{where}"] += 1
            stats[f"hit_{bucket}"] += 1
            if from_ocr:
                stats["hit_via_ocr"] += 1
            offset_hist[offset] += 1
        else:
            stats["miss"] += 1
            stats[f"miss_{bucket}"] += 1
            stats["miss_no_text_layer" if not page else "miss_text_present"] += 1
            if len(fail_examples) < examples:
                fail_examples.append({
                    "evidence_id": eid, "doc_name": doc_name, "page_id": page_id,
                    "layout_id": layout_id, "gold_len": len(gold),
                    "page_len": len(page), "best_coverage": round(cov, 3),
                    "gold_head": text[:160].replace("\n", " "),
                })

    if pdf:
        pdf.close()
    con.close()

    return stats, fail_examples, offset_hist, missing_pdf, ratios, empty_pages


def report(stats, fail_examples, offset_hist, missing_pdf, ratios, empty_pages,
           threshold, overlap):
    total = stats["total"]
    hits = (stats["hit_exact_page"] + stats["hit_neighbour_page"]
            + stats["hit_elsewhere_in_doc"])
    pct = hits / total * 100 if total else 0.0
    same_page_pct = stats["hit_exact_page"] / total * 100 if total else 0.0

    print("=" * 70)
    print("GATE 2  self-parsed PDF text  ->  official gold evidence")
    print("=" * 70)
    print(f"gold text evidence tested   : {total}")
    if stats["no_pdf"]:
        print(f"skipped, no PDF             : {stats['no_pdf']}")
    if stats["empty_gold"]:
        print(f"skipped, empty gold text    : {stats['empty_gold']}")
    print()
    print(f"  found on the stated page  : {stats['hit_exact_page']:>6}  ({same_page_pct:.2f}%)")
    print(f"  found on a nearby page    : {stats['hit_neighbour_page']:>6}")
    print(f"  found elsewhere in the doc: {stats['hit_elsewhere_in_doc']:>6}")
    print(f"  not found at all          : {stats['miss']:>6}")
    print(f"     of which page has no text layer (needs OCR): "
          f"{stats['miss_no_text_layer']:>5}")
    print(f"     of which page HAS text but no match        : "
          f"{stats['miss_text_present']:>5}")
    print()
    if stats["page_from_ocr"]:
        print(f"  items served by OCR text  : {stats['page_from_ocr']:>6}  "
              f"(of which matched: {stats['hit_via_ocr']})")
    print(f"  by length  hit short(<{SHORT_LEN}c): {stats['hit_short']:>6}   miss: {stats['miss_short']}")
    print(f"             hit long       : {stats['hit_long']:>6}   miss: {stats['miss_long']}")
    if empty_pages:
        print(f"  pages that extracted empty: {empty_pages} (likely scanned, needs OCR)")

    if offset_hist:
        top = [(k, v) for k, v in offset_hist.most_common(6)]
        print(f"  page offset distribution  : {top}")
    if missing_pdf:
        print(f"  documents without a usable PDF: {len(missing_pdf)} {sorted(missing_pdf)[:5]}")
    if ratios:
        srt = sorted(ratios)
        def pctl(p):
            return srt[min(len(srt) - 1, int(len(srt) * p))]
        print()
        print(f"  n-gram coverage (n={SHINGLE_N}) percentiles:")
        print(f"    p01={pctl(.01):.3f}  p05={pctl(.05):.3f}  p10={pctl(.10):.3f}  "
              f"p25={pctl(.25):.3f}  median={pctl(.50):.3f}")
        # Where the pass rate would land at other per-item cutoffs, so the
        # 0.80 default can be seen to be a plateau rather than a lucky pick.
        marks = [0.60, 0.70, 0.80, 0.90, 0.95, 0.99]
        line = "  ".join(
            f"{m:.2f}:{sum(1 for r in srt if r >= m) / len(srt) * 100:5.1f}%" for m in marks)
        print(f"    pass rate by cutoff  {line}")

    if fail_examples:
        print()
        print("-- failure examples --")
        for ex in fail_examples:
            print(f"  {ex['doc_name'][:34]:<34} page={ex['page_id']:<4} "
                  f"gold_len={ex['gold_len']:<5} page_len={ex['page_len']:<6} "
                  f"cov={ex['best_coverage']}{'  [NO TEXT LAYER]' if ex['page_len']==0 else ''}")
            print(f"      {ex['gold_head']}")

    # Items sitting on a page with no extractable text layer are blocked by the
    # PDF tooling, not by the matching method: MinerU ran OCR, PyMuPDF alone
    # does not. Reporting both figures separates "our alignment approach does
    # not work" from "we have not added OCR yet".
    ocr_blocked = stats["miss_no_text_layer"]
    reachable = total - ocr_blocked
    adj = hits / reachable * 100 if reachable else 0.0

    print()
    print("=" * 70)
    print(f"GATE 2  per-item overlap>={overlap:.2f}, need {threshold:.0f}%")
    print(f"  raw (PyMuPDF only)            : {pct:.2f}%  ({hits}/{total})")
    print(f"  excluding OCR-blocked pages   : {adj:.2f}%  ({hits}/{reachable}), "
          f"{ocr_blocked} items on pages with no text layer")
    passed = pct >= threshold
    print("  PASS" if passed else "  FAIL")
    if not passed and adj >= threshold:
        print(f"  -> the matching method holds ({adj:.2f}%); the shortfall is the "
              f"missing OCR pass, not the alignment approach")
    if passed and same_page_pct < threshold:
        print(f"  note: only {same_page_pct:.2f}% matched on the stated page; the rest "
              f"needed a neighbour/document search")
    print("=" * 70)
    return passed, pct, same_page_pct


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--pdf-root", default=DEFAULT_PDF_ROOT)
    ap.add_argument("--limit", type=int, default=0,
                    help="sample this many items (0 = all gold text evidence)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--neighbours", type=int, default=2,
                    help="how many pages either side to search on a page miss")
    ap.add_argument("--examples", type=int, default=8)
    ap.add_argument("--ocr-db", default=os.path.join(REPO_ROOT, "canonical", "ocr_cache.sqlite"),
                    help="OCR cache built by `python -m canonical.ocr`")
    ap.add_argument("--overlap", type=float, default=0.80,
                    help="per-item n-gram coverage needed to count as aligned")
    ap.add_argument("--threshold", type=float, default=95.0,
                    help="percent of items that must align for the gate to pass")
    ap.add_argument("--no-manifest", action="store_true")
    args = ap.parse_args()

    out = run(args.db, args.pdf_root, args.limit, args.seed,
              args.neighbours, args.examples, args.overlap, args.ocr_db)
    passed, pct, same_page_pct = report(*out, threshold=args.threshold,
                                        overlap=args.overlap)
    stats, fail_examples = out[0], out[1]

    if not args.no_manifest:
        sys.path.insert(0, REPO_ROOT)
        import manifest
        path = manifest.write(
            "canonical/gate2",
            data_files=[args.db],
            extra={"pdf_root": args.pdf_root, "limit": args.limit,
                   "seed": args.seed, "neighbours": args.neighbours,
                   "threshold": args.threshold},
            results={"alignable_pct": round(pct, 3),
                     "same_page_pct": round(same_page_pct, 3),
                     "gate2_pass": passed, **dict(stats)},
        )
        print("manifest:", os.path.relpath(path, REPO_ROOT))
        fail_path = os.path.join(REPO_ROOT, "manifests", "canonical",
                                 "gate2_failures.json")
        with open(fail_path, "w", encoding="utf-8") as fh:
            json.dump(fail_examples, fh, ensure_ascii=False, indent=2)

    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
