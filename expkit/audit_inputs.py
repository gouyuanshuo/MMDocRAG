"""Read-only checks of cached data; never rerun OCR or overwrite a database."""
import argparse
import collections
import json
import sqlite3
from pathlib import Path

from expkit.results import ExperimentResult, add_output_args
from expkit.paths import REPO_ROOT


def connect(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)


def canonical_audit(root):
    from canonical.build import SOURCES
    db = root / "canonical/mmdocrag.sqlite"
    with connect(db) as con:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        mapped = {(u, s, local): eid for u, s, local, eid in con.execute(
            "SELECT question_uid,setting,local_quote_id,evidence_id FROM question_candidates")}
        stored = set(con.execute(
            "SELECT question_uid,setting,local_quote_id,evidence_id FROM question_gold_evidence"))
        total = misses = 0
        seen = set()
        for split, setting, rel in SOURCES:
            with (root / rel).open(encoding="utf-8") as fh:
                for line in fh:
                    r = json.loads(line)
                    uid = f"{split}:{r['q_id']}"
                    for local in r["gold_quotes"]:
                        total += 1
                        eid = mapped.get((uid, str(setting), local))
                        item = (uid, str(setting), local, eid)
                        misses += eid is None or item not in stored
                        seen.add(item)
        if misses or seen != stored:
            raise ValueError(f"canonical gold/source mismatch: {misses} misses; "
                             f"{len(stored - seen)} unexpected stored rows")
        return dict(n_questions=con.execute("SELECT COUNT(*) FROM questions").fetchone()[0],
                    n_documents=con.execute("SELECT COUNT(DISTINCT doc_name) FROM questions").fetchone()[0],
                    n_gold_total=total, n_gold_mapped=total-misses, n_gold_dropped=0,
                    gold_mapping_rate=(total-misses)/total)


def ocr_audit(root):
    with connect(root / "retrieval/pages.sqlite") as con:
        n, before, after, docs = con.execute(
            "SELECT COUNT(*),SUM(layer_len=0),SUM(layer_len+ocr_len=0),"
            "COUNT(DISTINCT doc_name) FROM pages").fetchone()
    with connect(root / "canonical/ocr_cache.sqlite") as con:
        cached = con.execute("SELECT COUNT(*) FROM ocr_pages").fetchone()[0]
    return dict(n_pages=n, n_documents=docs, pages_with_zero_raw_chars_before=before,
                pages_with_zero_raw_chars_after=after, cached_ocr_pages=cached)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--experiment", choices=("E4", "E5", "E7"), required=True)
    add_output_args(ap)
    a = ap.parse_args()
    root = Path(REPO_ROOT)
    values = ocr_audit(root) if a.experiment == "E7" else canonical_audit(root)
    print(json.dumps(values, ensure_ascii=False, indent=2))
    with ExperimentResult(a.experiment, a.metrics_out, title="Cached input audit") as res:
        res.config(analysis="cached_input_audit", recomputed_from_saved_inputs=True,
                   reran_ocr=False, **values)
        for key, value in values.items():
            res.metric(key, value)
        files = ([root / "retrieval/pages.sqlite", root / "canonical/ocr_cache.sqlite"]
                 if a.experiment == "E7" else [root / "canonical/mmdocrag.sqlite"])
        res.data_file(*(str(p) for p in files))
        res.note("Read-only integrity/coverage audit. Reuses existing extraction; "
                 "does not claim to regenerate OCR or document parsing.")


if __name__ == "__main__":
    main()
