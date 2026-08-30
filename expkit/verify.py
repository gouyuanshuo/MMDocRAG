"""Assertions that pin down numbers the project has previously got wrong.

E24's pool figures were mis-stated twice, in ways that a prose record cannot
protect against:

    46.8%  divided image evidence ROWS (6,548) by UNIQUE images (13,999).
           Those are different units. The unique-image coverage is 46.34%
           (6,487 / 13,999).
    "每篇文档中位 29"  was the question-weighted median. Weighted by question,
           a document with 169 questions contributes its pool size 169 times, so
           the figure is pulled toward large documents. Per document the median
           is 20 and the mean 29.76.

Both survived review because they were plausible and nobody recomputed them. A
number that is only checked by reading is not checked. This module recomputes
each one from the databases and fails loudly on any drift.

A third failure was of a different kind and needed a different check. E24's
coverage story was told in prose ("2000/2000 ranked") with the 2000 written into
the script as a literal, and its headline contrast was captioned as isolating
"the two representations" when it in fact swapped the whole visual branch --
representation and retrieval architecture together. Neither error is visible to
a database recomputation, because neither is a database fact. So the E24 check
now also reads the metrics THIS RUN wrote and asserts, on them:

    coverage is a consistent numerator / denominator / ratio triple in both
    populations (all questions, and questions that have visual gold)
    all four paired comparisons exist at k=10 and k=20, each with a
    document-cluster interval
    the metric names have not drifted -- a renamed metric is a missing metric
    the word "isolat*" appears nowhere in E24's descriptions or notes

    python experiments.py verify E24
    python experiments.py verify E24 --run <run_id>

Results are written to artifacts, not merely printed, so a later run can diff
against them.
"""

import collections
import json
import os
import sqlite3
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from expkit import paths                            # noqa: E402
from expkit.results import atomic_json              # noqa: E402

DB = os.path.join(paths.REPO_ROOT, "canonical", "mmdocrag.sqlite")
COLQWEN = os.path.join(paths.REPO_ROOT, "retrieval", "colqwen_scores.sqlite")
IMG_ROOT = os.path.join("D:", os.sep, "Dataset", "MMDocRAG", "images", "images")

# The authoritative figures, independently confirmed 2026-08-28. Any drift here
# means either the database changed or a script regressed; both need a human.
EXPECTED_E24 = {
    # A. whole canonical DB
    "A.image_evidence_rows_all": 6565,
    "A.distinct_img_path_all": 6504,
    "A.doc_names_all": 223,
    # B. evaluation scope (what E24 actually ran on)
    "B.image_evidence_rows_eval": 6548,
    "B.distinct_img_path_eval": 6487,
    "B.evaluation_documents": 220,
    "B.evaluation_questions": 2000,
    # C. coverage of the original images
    "C.original_images_eval_docs": 13999,
    "C.unique_images_in_pool": 6487,
    "C.images_not_in_pool": 7512,
    # D. pool size, reported per document AND per question because they differ
    "D.pool_median_per_document": 20,
    "D.pool_min_per_document": 1,
    "D.pool_max_per_document": 262,
    "D.pool_median_per_question": 29,
    # E. ColQwen coverage inside the pool
    "E.colqwen_questions_covered": 2000,
    "E.colqwen_ranking_rows": 69842,
    "E.colqwen_length_mismatches": 0,
    "E.visual_gold_pairs_setting20": 3231,
    "E.visual_gold_missing_from_ranking": 0,
}
EXPECTED_FLOAT_E24 = {
    "C.unique_image_coverage": (0.463390, 1e-5),
    "D.pool_mean_per_document": (29.7636, 1e-3),
    "D.pool_mean_per_question": (34.9210, 1e-3),
}

# F. Coverage as recorded by the run. These are asserted against the metrics
# file, not the databases, because the failure being guarded against is a script
# that prints a stale literal while the data underneath it moved.
EXPECTED_F_E24 = {
    "F.n_evaluation_questions": 2000,
    "F.n_evaluation_questions_ranked": 2000,
    "F.n_visual_gold_questions": 1995,
    "F.n_visual_gold_questions_ranked": 1995,
    "F.questions_scored_here": 1995,
    "F.n_questions_without_visual_gold": 5,
    "F.total_visual_gold": 3231,
    "F.missing_visual_gold": 0,
}
EXPECTED_FLOAT_F_E24 = {
    "F.ranking_coverage_all_questions": (1.0, 1e-9),
    "F.ranking_coverage_visual_gold_questions": (1.0, 1e-9),
}

# G. The four paired comparisons, by their exact metric labels. A comparison
# that has been renamed is reported as MISSING rather than silently skipped:
# name drift is the specific way a check like this rots.
VISUAL_BRANCH_LABEL = ("visual branch: BM25+BGE RRF over VLM descriptions "
                       "- ColQwen over raw images")
COMPLEMENTARITY_LABEL = ("fusion complementarity: RRF(BM25 descriptions, "
                         "ColQwen) - ColQwen alone")
E24_COMPARISONS = [
    ("ColQwen - BM25",
     "single-retriever contrast; architecture held fixed"),
    ("ColQwen - BGE",
     "single-retriever contrast; architecture held fixed"),
    (VISUAL_BRANCH_LABEL,
     "whole-branch swap: representation AND architecture change together"),
    (COMPLEMENTARITY_LABEL,
     "fused arm contains ColQwen; measures complementarity only"),
]

# Wording that must not come back. "isolates the two representations" was the
# caption on a contrast that moved two variables at once. The ban is on the
# affirmative claim, not on the word: the corrected text has to be able to say
# "NOT an isolated representation effect", so a bare substring match on
# "isolat" would forbid the correction along with the error.
E24_BANNED_WORDING = (
    "isolates the two representations",
    "isolates the representation",
    "isolates representation",
    "isolating the two representations",
    "isolates a representation",
    "pure representation comparison",
    "纯表示比较",
)

# ...and the positive form, which is the part that actually protects the reader.
# Banning a phrase only stops one way of saying it; requiring the correct
# framing stops the claim from going missing altogether.
E24_REQUIRED_WORDING = (
    "complete visual-branch comparison",
    "not an isolated representation effect",
)


def measure_e24(db=DB, colqwen=COLQWEN, img_root=IMG_ROOT,
                run_id=None, artifact_root=None):
    """Recompute every contested figure. Pure measurement, no assertions."""
    m, notes = {}, []
    if not os.path.exists(db):
        raise SystemExit(f"canonical DB missing: {db}")
    con = sqlite3.connect(db)
    one = lambda s: con.execute(s).fetchone()[0]                    # noqa: E731

    m["A.image_evidence_rows_all"] = one(
        "SELECT COUNT(*) FROM canonical_evidence WHERE type <> 'text'")
    m["A.distinct_img_path_all"] = one(
        "SELECT COUNT(DISTINCT img_path) FROM canonical_evidence WHERE type <> 'text'")
    m["A.doc_names_all"] = one("SELECT COUNT(DISTINCT doc_name) FROM canonical_evidence")

    eval_docs = {d for d, in con.execute(
        "SELECT DISTINCT doc_name FROM questions WHERE split = 'evaluation'")}
    img_rows = [(d, p) for d, p in con.execute(
        "SELECT doc_name, img_path FROM canonical_evidence WHERE type <> 'text'")
        if d in eval_docs]
    m["B.image_evidence_rows_eval"] = len(img_rows)
    m["B.distinct_img_path_eval"] = len({p for _, p in img_rows})
    m["B.evaluation_documents"] = len(eval_docs)
    m["B.evaluation_questions"] = one(
        "SELECT COUNT(*) FROM questions WHERE split = 'evaluation'")

    # C -- unique images, not evidence rows. This is the distinction that the
    # 46.8% figure collapsed.
    if os.path.isdir(img_root):
        files = os.listdir(img_root)
        by_len = sorted(eval_docs, key=len, reverse=True)
        total = sum(1 for f in files if any(f.startswith(d) for d in by_len))
    else:
        total = None
        notes.append(f"image root not readable ({img_root}); C figures skipped")
    uniq = len({os.path.basename(p or "") for _, p in img_rows if p})
    m["C.original_images_eval_docs"] = total
    m["C.unique_images_in_pool"] = uniq
    m["C.images_not_in_pool"] = (total - uniq) if total else None
    m["C.unique_image_coverage"] = (uniq / total) if total else None
    # kept deliberately, labelled, so nobody re-derives it by accident
    m["C.WRONG_evidence_row_ratio"] = (len(img_rows) / total) if total else None

    per_doc = collections.Counter(d for d, _ in img_rows)
    sizes = [per_doc[d] for d in sorted(eval_docs)]
    m["D.pool_median_per_document"] = int(statistics.median(sizes))
    m["D.pool_mean_per_document"] = round(statistics.mean(sizes), 4)
    m["D.pool_min_per_document"] = min(sizes)
    m["D.pool_max_per_document"] = max(sizes)
    q_docs = [d for d, in con.execute(
        "SELECT doc_name FROM questions WHERE split = 'evaluation'")]
    weighted = [per_doc[d] for d in q_docs]
    m["D.pool_median_per_question"] = int(statistics.median(weighted))
    m["D.pool_mean_per_question"] = round(statistics.mean(weighted), 4)

    q_doc = dict(con.execute(
        "SELECT question_uid, doc_name FROM questions WHERE split = 'evaluation'"))
    gold = con.execute("""
        SELECT g.question_uid, g.evidence_id
        FROM question_gold_evidence g
        JOIN canonical_evidence e ON e.evidence_id = g.evidence_id
        JOIN questions q          ON q.question_uid = g.question_uid
        WHERE q.split = 'evaluation' AND g.setting = '20' AND e.type <> 'text'
    """).fetchall()
    con.close()

    if os.path.exists(colqwen):
        cq = sqlite3.connect(colqwen)
        m["E.colqwen_questions_covered"] = cq.execute(
            "SELECT COUNT(DISTINCT question_uid) FROM ranking").fetchone()[0]
        m["E.colqwen_ranking_rows"] = cq.execute(
            "SELECT COUNT(*) FROM ranking").fetchone()[0]
        lengths = dict(cq.execute(
            "SELECT question_uid, COUNT(*) FROM ranking GROUP BY question_uid"))
        ranked = collections.defaultdict(set)
        for u, e in cq.execute("SELECT question_uid, evidence_id FROM ranking"):
            ranked[u].add(e)
        cq.close()
        m["E.colqwen_length_mismatches"] = sum(
            1 for u, d in q_doc.items() if lengths.get(u, 0) != per_doc[d])
        m["E.visual_gold_pairs_setting20"] = len(gold)
        m["E.visual_gold_missing_from_ranking"] = sum(
            1 for u, e in gold if e not in ranked.get(u, ()))
    else:
        notes.append(f"ColQwen rankings missing ({colqwen}); E figures skipped")
        for key in ("E.colqwen_questions_covered", "E.colqwen_ranking_rows",
                    "E.colqwen_length_mismatches", "E.visual_gold_pairs_setting20",
                    "E.visual_gold_missing_from_ranking"):
            m[key] = None

    # ---- F/G: what the run actually recorded -----------------------------
    m["_run"] = _e24_run_metrics(run_id, artifact_root, m, notes)
    return m, notes


def _e24_run_metrics(run_id, artifact_root, m, notes):
    """Pull E24's metrics out of a run and fold the coverage triple into `m`.

    Deliberately reads only the run's metrics.json. Reading `experiments.py`'s
    prose instead is how a claim about four cells once got made on evidence for
    two; the same trap applies to a coverage figure.
    """
    try:
        resolved = paths.resolve_run(run_id, artifact_root)
        blocks = [b for b in _load_run_metrics(resolved, artifact_root)
                  if b.get("experiment") == "E24"]
    except SystemExit as exc:
        notes.append(f"no run metrics to check ({exc})")
        return None
    if not blocks:
        notes.append(f"run {run_id or 'latest'} contains no E24 metrics block; "
                     f"F/G checks will FAIL rather than skip")
        return {"run_id": run_id, "by_name": {}, "text": "", "found": False}

    by_name, texts = {}, []
    for b in blocks:
        for met in b.get("metrics", []):
            by_name[met["name"]] = met
            if met.get("desc"):
                texts.append(str(met["desc"]))
        texts.extend(str(n) for n in (b.get("notes") or []))
    blob = "\n".join(texts)

    for name in ("n_evaluation_questions", "n_evaluation_questions_ranked",
                 "ranking_coverage_all_questions", "n_visual_gold_questions",
                 "n_visual_gold_questions_ranked",
                 "ranking_coverage_visual_gold_questions",
                 "questions_scored_here", "n_questions_without_visual_gold",
                 "total_visual_gold", "missing_visual_gold"):
        met = by_name.get(name)
        m[f"F.{name}"] = met.get("value") if met else None
    return {"run_id": blocks[0].get("run_id") or run_id, "by_name": by_name,
            "text": blob, "found": True,
            "paths": sorted({b.get("_path") for b in blocks})}


def check_e24(measured):
    """Compare against the authoritative values. Returns per-key check rows."""
    rows = []
    for key, want in EXPECTED_E24.items():
        got = measured.get(key)
        rows.append({"key": key, "expected": want, "measured": got,
                     "ok": got == want,
                     "status": "skipped" if got is None else
                               ("pass" if got == want else "FAIL")})
    for key, (want, tol) in EXPECTED_FLOAT_E24.items():
        got = measured.get(key)
        ok = got is not None and abs(got - want) <= tol
        rows.append({"key": key, "expected": want, "measured": got, "ok": ok,
                     "tolerance": tol,
                     "status": "skipped" if got is None else
                               ("pass" if ok else "FAIL")})
    rows.extend(_check_e24_run(measured))
    return rows


def _add(rows, key, ok, expected, got):
    rows.append({"key": key, "expected": expected, "measured": got,
                 "ok": bool(ok), "status": "pass" if ok else "FAIL"})


def _check_e24_run(measured):
    """F/G: assertions against the run's own metrics.

    A missing metrics block is a FAIL, never a skip. "Not measured" and "measured
    and correct" must not print the same way, or the check stops being one.
    """
    rows = []
    run = measured.get("_run")
    if not run or not run.get("found"):
        _add(rows, "F.metrics_block_present", False, "present",
             "MISSING -- run has no E24 metrics.json")
        for key in EXPECTED_F_E24:
            _add(rows, key, False, EXPECTED_F_E24[key], "MISSING")
        for key in EXPECTED_FLOAT_F_E24:
            _add(rows, key, False, EXPECTED_FLOAT_F_E24[key][0], "MISSING")
        for label, _why in E24_COMPARISONS:
            for k in (10, 20):
                _add(rows, f"G.paired[{label}]@{k}", False, "present", "MISSING")
        return rows

    _add(rows, "F.metrics_block_present", True, "present", "present")
    for key, want in EXPECTED_F_E24.items():
        got = measured.get(key)
        _add(rows, key, got == want, want, "MISSING" if got is None else got)
    for key, (want, tol) in EXPECTED_FLOAT_F_E24.items():
        got = measured.get(key)
        _add(rows, key, got is not None and abs(got - want) <= tol, want,
             "MISSING" if got is None else got)

    # Internal consistency: the ratio must equal its own numerator/denominator,
    # and the two populations must add up. A coverage number that does not
    # divide its own counts is either stale or computed on a different set.
    for ratio, num, dend in (
            ("F.ranking_coverage_all_questions",
             "F.n_evaluation_questions_ranked", "F.n_evaluation_questions"),
            ("F.ranking_coverage_visual_gold_questions",
             "F.n_visual_gold_questions_ranked", "F.n_visual_gold_questions")):
        r, n, d = (measured.get(ratio), measured.get(num), measured.get(dend))
        ok = None not in (r, n, d) and d and abs(r - n / d) <= 1e-9
        _add(rows, f"consistency[{ratio} == {num}/{dend}]", ok, "consistent",
             f"{r} vs {n}/{d}" if None not in (r, n, d) else "MISSING")

    n_all = measured.get("F.n_evaluation_questions")
    n_vg = measured.get("F.n_visual_gold_questions")
    n_no = measured.get("F.n_questions_without_visual_gold")
    ok = None not in (n_all, n_vg, n_no) and n_all - n_vg == n_no
    _add(rows, "consistency[all - visual_gold == without_visual_gold]", ok,
         "consistent", f"{n_all} - {n_vg} != {n_no}" if not ok else "consistent")

    n_scored = measured.get("F.questions_scored_here")
    _add(rows, "consistency[scored == visual_gold_questions]",
         n_scored is not None and n_scored == n_vg, n_vg,
         "MISSING" if n_scored is None else n_scored)

    # The DB and the run must agree about how much gold there is. If they do
    # not, one of them is describing a different pool.
    db_gold = measured.get("E.visual_gold_pairs_setting20")
    run_gold = measured.get("F.total_visual_gold")
    _add(rows, "consistency[run total_visual_gold == DB gold pairs]",
         db_gold is not None and db_gold == run_gold, db_gold,
         "MISSING" if run_gold is None else run_gold)

    # Every metric that carries a ratio must also carry its counts, so a reader
    # never has to reconstruct the denominator from prose.
    for name in ("ranking_coverage_all_questions",
                 "ranking_coverage_visual_gold_questions"):
        met = run["by_name"].get(name) or {}
        _add(rows, f"F.{name}.has_numerator_and_denominator",
             met.get("numerator") is not None and met.get("denominator") is not None,
             "numerator+denominator",
             "present" if met.get("denominator") is not None else "MISSING")

    # G: the four comparisons, at both budgets, each with a document-cluster CI.
    for label, _why in E24_COMPARISONS:
        for k in (10, 20):
            name = f"paired_delta[{label}]@{k}"
            met = run["by_name"].get(name)
            _add(rows, f"G.paired[{label}]@{k}", met is not None,
                 "present", "present" if met else "MISSING")
            has_ci = bool(met and met.get("ci_low") is not None
                          and met.get("ci_high") is not None)
            _add(rows, f"G.paired[{label}]@{k}.doc_cluster_ci", has_ci,
                 "ci present", "present" if has_ci else "MISSING")
            _add(rows, f"G.paired[{label}]@{k}.bootstrap_unit",
                 bool(met) and met.get("bootstrap_unit") == "document",
                 "document", (met or {}).get("bootstrap_unit") or "MISSING")

    # Wording regression guard, in both directions.
    blob = (run.get("text") or "").lower()
    hit = [w for w in E24_BANNED_WORDING if w in blob]
    _add(rows, "wording[no 'isolates representation' claim]",
         not hit, "absent", ", ".join(hit) if hit else "absent")
    for want in E24_REQUIRED_WORDING:
        _add(rows, f"wording[says '{want}']", want in blob, "present",
             "present" if want in blob else "MISSING")

    vb = run["by_name"].get(f"paired_delta[{VISUAL_BRANCH_LABEL}]@10") or {}
    desc = str(vb.get("desc") or "").lower()
    _add(rows, "wording[visual-branch metric carries the correction]",
         "not an isolated representation effect" in desc, "present",
         "present" if "not an isolated representation effect" in desc
         else "MISSING")
    return rows


# ---------------------------------------------------------------------------
# E27: the 2x2 main-result matrix
# ---------------------------------------------------------------------------
# E27's headline is four out-of-fold cells: two candidate pools x two evidence
# budgets. The registry used to run only two of them, so a reader saw a claim
# about four and evidence for two -- and the missing pair was filled in from the
# prose `result` string, which is a memory of an older run, not a measurement.
#
# This check therefore reads ONLY a run's metrics.json files. It never looks at
# `experiments.py`'s result text. If a cell was not measured in that run, it is
# missing, and a missing cell is an exit-1 failure rather than a gap the reader
# is left to notice.
E27_CELLS = [("selfbuilt", 10), ("selfbuilt", 20),
             ("canonical", 10), ("canonical", 20)]

E27_REQUIRED_METRICS = {
    "recall_paper_style_E": "baseline (closest local paper-style hybrid)",
    "recall_surrogate_A": "baseline (local BGE-small surrogate)",
    "recall_nested_cv_oof": "ours (out-of-fold selected pipeline)",
    "delta: nested-CV - paper-style (E)": "delta vs paper-style baseline",
    "delta: nested-CV - surrogate (A)": "delta vs surrogate baseline",
}

E27_REQUIRED_CONFIG = {
    "analysis": "nested_cv",
    "grouping": "document",
    "oof": True,
    "folds": 5,
    "sample_unit": "document",
    "unmapped_gold": "counted as miss",
    "n_questions": 2000,
}


def _load_run_metrics(run_id, artifact_root=None):
    """Every metrics.json under a run, tagged with the experiment it was filed
    under. The experiment id comes from the file, not from the directory name."""
    rdir = paths.run_dir(run_id, artifact_root)
    root = os.path.join(rdir, "experiments")
    if not os.path.isdir(root):
        raise SystemExit(f"run {run_id} has no experiments/ directory: {rdir}")
    blocks = []
    for base, _dirs, files in os.walk(root):
        if "metrics.json" not in files:
            continue
        p = os.path.join(base, "metrics.json")
        with open(p, encoding="utf-8") as fh:
            b = json.load(fh)
        b["_path"] = paths.rel(p)
        blocks.append(b)
    return blocks


def measure_e27(run_id=None, artifact_root=None):
    run_id = paths.resolve_run(run_id, artifact_root)
    blocks = [b for b in _load_run_metrics(run_id, artifact_root)
              if b.get("experiment") == "E27"
              and (b.get("config") or {}).get("analysis") == "nested_cv"]
    cells = {}
    for b in blocks:
        cfg = b.get("config") or {}
        key = (cfg.get("pool"), cfg.get("k"))
        by_name = {m["name"]: m for m in b.get("metrics", [])}
        cells[key] = {"config": cfg, "metrics": by_name, "path": b["_path"],
                      "status": b.get("status")}
    return {"run_id": run_id, "cells": cells, "n_blocks": len(blocks)}, []


def check_e27(measured):
    rows = []
    cells = measured["cells"]

    def add(key, ok, expected, got, status=None):
        rows.append({"key": key, "expected": expected, "measured": got,
                     "ok": bool(ok),
                     "status": status or ("pass" if ok else "FAIL")})

    add("matrix.n_cells", len(cells) >= 4, 4, len(cells))
    for pool, k in E27_CELLS:
        tag = f"{pool}/k={k}"
        cell = cells.get((pool, k))
        if cell is None:
            # A missing cell is the failure this check exists for. Everything
            # downstream of it is reported as absent rather than skipped, so the
            # output cannot be misread as "not applicable".
            add(f"cell[{tag}].present", False, "present", "MISSING")
            for name in E27_REQUIRED_METRICS:
                add(f"cell[{tag}].{name}", False, "present", "MISSING")
            add(f"cell[{tag}].delta_has_doc_cluster_ci", False, "present", "MISSING")
            continue
        add(f"cell[{tag}].present", True, "present", "present")
        cfg = cell["config"]
        for ck, cv in E27_REQUIRED_CONFIG.items():
            add(f"cell[{tag}].config.{ck}", cfg.get(ck) == cv, cv, cfg.get(ck))
        add(f"cell[{tag}].status_ok", cell["status"] == "ok", "ok", cell["status"])
        for name in E27_REQUIRED_METRICS:
            m = cell["metrics"].get(name)
            add(f"cell[{tag}].{name}", m is not None and m.get("value") is not None,
                "present", "present" if m else "MISSING")
        d = cell["metrics"].get("delta: nested-CV - paper-style (E)")
        add(f"cell[{tag}].delta_has_doc_cluster_ci",
            bool(d and d.get("ci_low") is not None and d.get("ci_high") is not None),
            "ci present", "present" if (d and d.get("ci_low") is not None) else "MISSING")
    return rows


def _print_e27_matrix(measured):
    print()
    print("E27 MAIN-RESULT MATRIX  (read from this run's metrics.json only)")
    print("-" * 100)
    print(f"{'pool':<12}{'k':>4}{'baseline E':>13}{'baseline A':>13}"
          f"{'ours (OOF)':>13}{'delta vs E':>13}{'doc-cluster 95% CI':>28}")
    print("-" * 100)
    for pool, k in E27_CELLS:
        cell = measured["cells"].get((pool, k))
        if cell is None:
            print(f"{pool:<12}{k:>4}{'MISSING':>13}{'MISSING':>13}"
                  f"{'MISSING':>13}{'MISSING':>13}{'MISSING':>28}")
            continue
        m = cell["metrics"]
        e = m.get("recall_paper_style_E", {}).get("value")
        a = m.get("recall_surrogate_A", {}).get("value")
        o = m.get("recall_nested_cv_oof", {}).get("value")
        d = m.get("delta: nested-CV - paper-style (E)", {})
        ci = ("[%+.4f,%+.4f]%s" % (d["ci_low"], d["ci_high"],
                                   "*" if d.get("significant") else " ")
              if d.get("ci_low") is not None else "—")
        print(f"{pool:<12}{k:>4}{e:>13.4f}{a:>13.4f}{o:>13.4f}"
              f"{d.get('value', float('nan')):>+13.4f}{ci:>28}")
    print("-" * 100)
    print("* = document-cluster 95% CI excludes zero. Every question is scored")
    print("under a configuration selected without it (document-grouped 5-fold,")
    print("out-of-fold); unmapped gold counts as a miss.")


CHECKS = {
    "E24": (measure_e24, check_e24),
    "E27": (measure_e27, check_e27),
}


def run(exp_id, outdir=None, artifact_root=None, run_id=None):
    exp_id = exp_id.upper()
    if exp_id not in CHECKS:
        raise SystemExit(f"no verification defined for {exp_id}. "
                         f"Available: {', '.join(sorted(CHECKS))}")
    measure, check = CHECKS[exp_id]
    try:
        measured, notes = measure(run_id=run_id, artifact_root=artifact_root)
    except TypeError:
        measured, notes = measure()
    rows = check(measured)

    n_fail = sum(1 for r in rows if r["status"] == "FAIL")
    n_skip = sum(1 for r in rows if r["status"] == "skipped")
    n_pass = sum(1 for r in rows if r["status"] == "pass")

    print("=" * 88)
    print(f"VERIFY {exp_id}   pass {n_pass}   FAIL {n_fail}   skipped {n_skip}")
    print("=" * 88)
    for note in notes:
        print(f"[note] {note}")
    if exp_id == "E24":
        rb = measured.get("_run") or {}
        print(f"[source] A-E recomputed from the databases; F/G read from "
              f"run {rb.get('run_id') or run_id or 'latest'}")
        for p in (rb.get("paths") or []):
            print(f"[source] {p}")
    width = max(len(r["key"]) for r in rows)
    print(f"{'check':<{width + 2}}{'expected':>14}{'measured':>14}   status")
    print("-" * 88)
    for r in rows:
        exp_s = (f"{r['expected']:.6f}" if isinstance(r["expected"], float)
                 else str(r["expected"]))
        got_s = ("—" if r["measured"] is None else
                 (f"{r['measured']:.6f}" if isinstance(r["measured"], float)
                  else str(r["measured"])))
        mark = {"pass": "ok", "FAIL": "**FAIL**", "skipped": "skip"}[r["status"]]
        print(f"{r['key']:<{width + 2}}{exp_s:>14}{got_s:>14}   {mark}")
    print("-" * 88)
    if exp_id == "E27":
        _print_e27_matrix(measured)
        payload = {
            "experiment": exp_id,
            "run_id": measured.get("run_id"),
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "FAIL" if n_fail else ("partial" if n_skip else "pass"),
            "counts": {"pass": n_pass, "fail": n_fail, "skipped": n_skip},
            "source": "this run's metrics.json only; experiments.py prose not read",
            "cells": {f"{p}/k={k}": {
                "config": measured["cells"][(p, k)]["config"],
                "metrics": {n: {kk: vv for kk, vv in m.items() if kk != "name"}
                            for n, m in measured["cells"][(p, k)]["metrics"].items()},
                "metrics_path": measured["cells"][(p, k)]["path"],
            } for p, k in E27_CELLS if (p, k) in measured["cells"]},
            "missing_cells": [f"{p}/k={k}" for p, k in E27_CELLS
                              if (p, k) not in measured["cells"]],
            "checks": rows,
        }
        outdir = outdir or os.path.join(paths.artifact_root(artifact_root), "verify")
        os.makedirs(outdir, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        hist = os.path.join(outdir, f"{exp_id}_{stamp}.json")
        atomic_json(hist, payload)
        atomic_json(os.path.join(outdir, f"{exp_id}_latest.json"), payload)
        print()
        print(f"wrote {paths.rel(hist)}")
        print(f"wrote {paths.rel(os.path.join(outdir, exp_id + '_latest.json'))}")
        return payload, n_fail

    print(f"WRONG figure kept for reference: evidence-row ratio = "
          f"{measured.get('C.WRONG_evidence_row_ratio')!r} (this is the 46.8% "
          f"that mixed evidence rows with unique images; do not cite it)")
    print()
    print("Correct wording:")
    print("  池覆盖：6,487 / 13,999 = 46.34% 的唯一图片（不是 46.8%）")
    print("  池规模：按文档中位 20、均值 29.8；按问题加权中位 29、均值 34.9")
    print("  ColQwen：完整排序了当前池内全部图片证据，视觉 gold 无索引覆盖缺失；")
    print("           但「在完整 ranking 中」不等于「进入 top-k」——")
    print("           E24 实测 ColQwen Recall@10≈0.820、Recall@20≈0.929。")
    print("  视觉分支比较：BM25+BGE RRF over VLM descriptions vs ColQwen over raw")
    print("           images 同时改变了表示（像素→VLM 文字）与检索架构（单个"
          "后交互检索器→两个检索器 RRF 融合），")
    print("           因此是完整的视觉分支比较，不是被隔离出来的表示效应。")
    print("           可支持的说法：在当前不完整的图片池中、紧预算 k=10 下，")
    print("           完整的 description-RRF 分支检索更好；")
    print("           不可支持的说法：VLM 文字表示优于像素表示。")

    run_block = measured.pop("_run", None) or {}
    payload = {
        "experiment": exp_id,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "FAIL" if n_fail else ("partial" if n_skip else "pass"),
        "counts": {"pass": n_pass, "fail": n_fail, "skipped": n_skip},
        "notes": notes,
        "metrics_run_id": run_block.get("run_id"),
        "metrics_paths": run_block.get("paths"),
        "measured": measured,
        "checks": rows,
        "correct_wording": {
            "visual_branch_comparison": (
                "visual branch comparison: ColQwen over raw images vs BM25+BGE "
                "RRF over VLM descriptions. This changes both representation and "
                "retrieval architecture. It is a complete visual-branch "
                "comparison, not an isolated representation effect."),
            "deprecated_wording": ("'isolates the two representations' -- the "
                                   "contrast moves two variables at once"),
            "supportable_claim": ("in this incomplete image pool, at the tight "
                                  "k=10 budget, the complete description-RRF "
                                  "branch retrieves better than the ColQwen "
                                  "branch"),
            "unsupportable_claim": ("VLM text representations beat pixel "
                                    "representations"),
            "unique_image_coverage": "6,487 / 13,999 = 46.34%",
            "deprecated_figure": "46.8% (evidence rows / unique images -- unit mismatch)",
            "pool_size": "per document median 20, mean 29.8; per question median 29, mean 34.9",
            "colqwen": ("ranks 100% of the in-pool image evidence and no visual gold "
                        "is absent from the full ranking; being in the ranking is NOT "
                        "the same as entering top-k -- ColQwen Recall@10 approx 0.820, "
                        "Recall@20 approx 0.929"),
        },
    }
    outdir = outdir or os.path.join(paths.artifact_root(artifact_root), "verify")
    os.makedirs(outdir, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    hist = os.path.join(outdir, f"{exp_id}_{stamp}.json")
    atomic_json(hist, payload)
    latest = os.path.join(outdir, f"{exp_id}_latest.json")
    atomic_json(latest, payload)
    print()
    print(f"wrote {paths.rel(hist)}")
    print(f"wrote {paths.rel(latest)}")
    return payload, n_fail
