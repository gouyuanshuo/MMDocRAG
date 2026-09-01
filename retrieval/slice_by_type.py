"""Where the static retrieval improvement lands, sliced by question class.

Why this script exists
----------------------
The proposal's Experiment 2 asks for the headline retrieval result broken out
by question type. E27 reports one number per (pool, k): the out-of-fold
nested-CV configuration against the closest local paper-style baseline. A
single number cannot say whether the gain is spread across the corpus or comes
from one kind of question, and "our configuration is better" is a much weaker
statement if it is better only where the baseline was already strong.

What the proposal asked for and what the data can supply
-------------------------------------------------------
The proposal names five classes: pure text, pure visual, cross-modal,
cross-page, unanswerable. Two of them cannot be evaluated here, and that is a
property of MMDocRAG rather than of this code:

  * PURE TEXT has n = 1 in the evaluation split. It is printed for completeness
    and never tested; no interval over one question means anything.
  * UNANSWERABLE does not exist. No question in the split is labelled
    unanswerable and every question carries gold evidence, so the class has no
    members to slice.

What remains is three partitions, all with usable support: evidence modality
(cross-modal against pure visual), gold page span (single-page against
cross-page), and the corpus's own `question_type` label.

Statistical protocol, fixed before looking at any slice
------------------------------------------------------
1. The comparison inside every slice is the same one E27 publishes: the
   out-of-fold nested-CV selection minus the paper-style baseline E. Selection
   happens on the full corpus in document-grouped folds exactly as in E27, so
   the slicing never touches model selection -- it only partitions the
   already-computed out-of-fold vector. Slicing before selection would let a
   slice choose its own configuration and the numbers would no longer be E27's.
2. Every interval is a document-cluster bootstrap. Questions nest inside
   documents in every slice, and a slice can hold many questions from few
   documents, so the document count is printed beside every interval and is the
   number that governs the width.
3. The family is declared here, not after the fact: every slice with at least
   100 questions and 20 documents, at both k, tested against zero. Holm-Bonferroni
   runs over that whole family. Between-slice contrasts form a second, separate
   family for the same reason.
4. The heterogeneity question -- "does this improvement depend on the question
   class?" -- is answered by the CONTRAST between the two halves of a partition,
   not by noting that one half is significant and the other is not. The contrast
   is bootstrapped over documents so that a document contributing questions to
   both halves is resampled as one unit.

This split has been observed repeatedly since E9 and was used to choose methods.
Everything here is EXPLORATORY, and the script says so in its own output.

Run:
    python -m retrieval.slice_by_type --pool selfbuilt
"""

import argparse
import collections
import json
import os
import sqlite3
import sys

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from expkit.results import ExperimentResult, add_output_args        # noqa: E402
from retrieval.eval_stack_v2 import (build, PAPER_QUOTA,            # noqa: E402
                                     DEFAULT_DB, DEFAULT_QUOTES,
                                     DEFAULT_COLQWEN)
from retrieval.nested_cv import CONFIGS, document_folds, score      # noqa: E402
from retrieval.ablation import holm                                 # noqa: E402

BOOT = 4000
SEED = 20260831
MIN_Q = 100          # a slice below either threshold is described, never tested
MIN_DOC = 20


# ---------------------------------------------------------------- classes
def question_classes(db_path):
    """Three partitions of the evaluation split, keyed by question_uid."""
    con = sqlite3.connect(db_path)
    rows = con.execute(
        "SELECT question_uid, question_type, evidence_modality_type "
        "FROM questions WHERE split = 'evaluation'").fetchall()
    span = dict(con.execute(
        "SELECT q.question_uid, COUNT(DISTINCT e.page_id) "
        "FROM questions q "
        "JOIN question_gold_evidence g ON g.question_uid = q.question_uid "
        "JOIN canonical_evidence e     ON e.evidence_id  = g.evidence_id "
        "WHERE q.split = 'evaluation' AND g.setting = '20' "
        "GROUP BY q.question_uid").fetchall())
    con.close()

    modality, qtype, pages = {}, {}, {}
    for quid, qt, em in rows:
        try:
            mods = json.loads(em) if em else []
        except (ValueError, TypeError):
            mods = [em] if em else []
        has_text = "text" in mods
        has_vis = any(m != "text" for m in mods)
        modality[quid] = ("cross-modal" if (has_text and has_vis)
                          else "pure text" if has_text
                          else "pure visual" if has_vis else "unlabelled")
        qtype[quid] = qt or "unlabelled"
        n = span.get(quid)
        # A question whose gold spans no page at all cannot be placed in this
        # partition; it is held out of the page partition rather than guessed
        # into one, and the count is printed.
        pages[quid] = ("single-page" if n == 1 else
                       "cross-page" if (n or 0) > 1 else "no page span")
    return {"evidence modality": modality,
            "gold page span": pages,
            "question type": qtype}


# ---------------------------------------------------------------- statistics
def _by_doc(docs):
    by = collections.defaultdict(list)
    for i, d in enumerate(docs):
        by[d].append(i)
    keys = sorted(by)
    return keys, [np.asarray(by[k]) for k in keys]


def slice_ci(d, docs, mask, rng, n_boot=BOOT):
    """Document-cluster bootstrap of the mean of `d` over `mask`.

    Documents are the resampling unit even inside a slice: a slice can hold
    forty questions from six documents, and treating those forty as independent
    would report an interval the data cannot support.
    """
    keys, idx = _by_doc(docs)
    sums = np.array([d[i][m].sum() for i, m in zip(idx, mask)])
    cnts = np.array([int(m.sum()) for m in mask], dtype=float)
    live = cnts > 0
    sums, cnts = sums[live], cnts[live]
    if not len(cnts):
        return 0.0, 0.0, 0.0, 1.0, 0
    p = rng.integers(0, len(cnts), size=(n_boot, len(cnts)))
    den = np.maximum(cnts[p].sum(axis=1), 1e-9)
    m = sums[p].sum(axis=1) / den
    lo, hi = np.percentile(m, [2.5, 97.5])
    tail = min((m <= 0).mean(), (m >= 0).mean())
    return (sums.sum() / cnts.sum(), lo, hi,
            max(2.0 * tail, 1.0 / n_boot), int(len(cnts)))


def contrast_ci(d, docs, mask_a, mask_b, rng, n_boot=BOOT):
    """Bootstrap of (mean over A) - (mean over B), resampling DOCUMENTS.

    One document supplies questions to both halves, so the halves are not
    independent samples. Resampling documents and recomputing both halves
    inside each resample is what keeps that dependence in the interval.
    """
    keys, idx = _by_doc(docs)
    sa = np.array([d[i][m].sum() for i, m in zip(idx, mask_a)])
    ca = np.array([int(m.sum()) for m in mask_a], dtype=float)
    sb = np.array([d[i][m].sum() for i, m in zip(idx, mask_b)])
    cb = np.array([int(m.sum()) for m in mask_b], dtype=float)
    p = rng.integers(0, len(keys), size=(n_boot, len(keys)))
    da = np.maximum(ca[p].sum(axis=1), 1e-9)
    db = np.maximum(cb[p].sum(axis=1), 1e-9)
    m = sa[p].sum(axis=1) / da - sb[p].sum(axis=1) / db
    lo, hi = np.percentile(m, [2.5, 97.5])
    tail = min((m <= 0).mean(), (m >= 0).mean())
    point = sa.sum() / max(ca.sum(), 1e-9) - sb.sum() / max(cb.sum(), 1e-9)
    return point, lo, hi, max(2.0 * tail, 1.0 / n_boot)


def oof_delta(rows, k, folds, seed):
    """E27's out-of-fold selected recall minus the paper-style baseline E.

    Reproduces nested_cv's selection exactly: the inner loop maximises mean
    recall over the training folds across every (text retriever, visual
    retriever, quota) candidate, and the winner scores the held-out fold. The
    slicing downstream never re-selects.
    """
    docs = np.asarray([r["doc"] for r in rows])
    fold, _load = document_folds(docs.tolist(), folds)
    cand = {}
    for tr, vr in CONFIGS:
        for a in range(k + 1):
            cand[(tr, vr, a)] = score(rows, tr, vr, (a, k - a))
    ref_E = score(rows, "dense", "colqwen", PAPER_QUOTA[k])
    selected = np.zeros(len(rows))
    picks = []
    for f in range(folds):
        inner, outer = fold != f, fold == f
        best, best_v = None, -1.0
        for key, v in cand.items():
            m = v[inner].mean()
            if m > best_v:
                best, best_v = key, m
        selected[outer] = cand[best][outer]
        picks.append(best)
    return selected, ref_E, docs, picks


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--quotes", default=DEFAULT_QUOTES)
    ap.add_argument("--colqwen", default=DEFAULT_COLQWEN)
    ap.add_argument("--pool", default="selfbuilt",
                    choices=("selfbuilt", "canonical"))
    ap.add_argument("--ks", default="10,20")
    ap.add_argument("--folds", type=int, default=5)
    add_output_args(ap)
    args = ap.parse_args()
    ks = [int(x) for x in args.ks.split(",")]

    rows, meta = build(args.db, args.quotes, args.colqwen, args.pool)
    parts = question_classes(args.db)
    quids = [r["quid"] for r in rows]
    # A question the partitions do not cover would be silently excluded from
    # every slice while still counting in the headline, so the mismatch is
    # reported rather than absorbed.
    unknown = sum(1 for q in quids if q not in parts["evidence modality"])
    if unknown:
        print(f"WARNING: {unknown} question(s) carry no class label and are "
              f"absent from every slice below.")

    rng = np.random.default_rng(SEED)

    print("=" * 92)
    print(f"WHERE THE STATIC IMPROVEMENT LANDS   pool={args.pool}  "
          f"folds={args.folds}")
    print("=" * 92)
    print(f"questions {len(rows)}, documents "
          f"{len({r['doc'] for r in rows})}, "
          f"unmapped gold counted as miss "
          f"{sum(r['n_unmapped'] for r in rows)}, "
          f"questions with no gold dropped upstream {meta['n_no_gold']}")
    print("Comparison in every slice: out-of-fold nested-CV selection minus the")
    print("closest local paper-style baseline E (dense text + ColQwen visual,")
    print("paper quota). Selection is done once on the whole corpus in")
    print("document-grouped folds; slices never re-select.")
    print()

    # ---- describe the partitions before testing anything -----------------
    print("PARTITIONS  (support decides what can be tested, and is fixed here)")
    print("-" * 92)
    testable = {}
    for pname, lookup in parts.items():
        counts = collections.Counter(lookup.get(q, "unlabelled") for q in quids)
        docs_of = collections.defaultdict(set)
        for q, r in zip(quids, rows):
            docs_of[lookup.get(q, "unlabelled")].add(r["doc"])
        print(f"  {pname}")
        for lab, n in counts.most_common():
            nd = len(docs_of[lab])
            ok = n >= MIN_Q and nd >= MIN_DOC
            if ok:
                testable.setdefault(pname, []).append(lab)
            print(f"      {lab:<24} {n:>5} questions  {nd:>4} documents   "
                  f"{'tested' if ok else 'DESCRIBED ONLY (below threshold)'}")
    print("-" * 92)
    print("  'pure text' has one question in this split and 'unanswerable' has")
    print("  none, so two of the proposal's five classes are unevaluable here.")
    print("  That is a property of MMDocRAG, not a gap in this analysis.")
    print()

    # ---- the declared family --------------------------------------------
    jobs = []
    for k in ks:
        for pname, labs in testable.items():
            for lab in labs:
                jobs.append((k, pname, lab))
    print(f"DECLARED FAMILY: {len(jobs)} slice tests "
          f"({len(testable)} partitions x their testable levels x {len(ks)} k). "
          f"Holm-Bonferroni over all of them.")
    print()

    results, deltas_by_k = [], {}
    for k in ks:
        selected, ref_E, docs, picks = oof_delta(rows, k, args.folds, SEED)
        d = selected - ref_E
        deltas_by_k[k] = (d, docs)
        _keys, idx = _by_doc(docs)
        for pname, labs in testable.items():
            lookup = parts[pname]
            for lab in labs:
                flag = np.array([lookup.get(q) == lab for q in quids])
                mask = [flag[i] for i in idx]
                pt, lo, hi, pv, nd = slice_ci(d, docs, mask, rng)
                results.append({"k": k, "partition": pname, "level": lab,
                                "delta": pt, "lo": lo, "hi": hi, "p": pv,
                                "n_questions": int(flag.sum()),
                                "n_documents": nd})

    adj = holm([r["p"] for r in results])
    for r, a in zip(results, adj):
        r["p_holm"] = a

    print("SLICE TESTS  (delta > 0 means the selected configuration wins there)")
    print("-" * 92)
    print(f"{'k':>3}  {'partition':<18}{'level':<22}{'n_q':>5}{'n_doc':>6}  "
          f"{'delta':>8}  {'95% CI':>19}  {'p_holm':>7}")
    print("-" * 92)
    for r in results:
        star = "*" if r["p_holm"] < 0.05 and (r["lo"] > 0 or r["hi"] < 0) else " "
        print(f"{r['k']:>3}  {r['partition']:<18}{r['level']:<22}"
              f"{r['n_questions']:>5}{r['n_documents']:>6}  "
              f"{r['delta']:>+8.4f}  [{r['lo']:>+7.4f},{r['hi']:>+7.4f}]{star} "
              f"{r['p_holm']:>7.4f}")
    print("-" * 92)
    print("  * = survives Holm at 0.05 AND has an interval clear of zero. An")
    print("    interval touching zero is not called significant however small")
    print("    the raw p is.")
    print()

    # ---- heterogeneity: the contrast, which is the actual question -------
    print("HETEROGENEITY  (is the gain DIFFERENT between the halves?)")
    print("-" * 92)
    print("  Comparing 'A is significant, B is not' is not a test of difference.")
    print("  These are the contrasts, bootstrapped over documents so a document")
    print("  contributing to both halves is resampled once.")
    print()
    contrasts = []
    binary = [(p, ls) for p, ls in testable.items() if len(ls) == 2]
    for k in ks:
        d, docs = deltas_by_k[k]
        _keys, idx = _by_doc(docs)
        for pname, labs in binary:
            lookup = parts[pname]
            fa = np.array([lookup.get(q) == labs[0] for q in quids])
            fb = np.array([lookup.get(q) == labs[1] for q in quids])
            pt, lo, hi, pv = contrast_ci(d, docs, [fa[i] for i in idx],
                                         [fb[i] for i in idx], rng)
            contrasts.append({"k": k, "partition": pname,
                              "levels": f"{labs[0]} - {labs[1]}",
                              "delta": pt, "lo": lo, "hi": hi, "p": pv})
    cadj = holm([c["p"] for c in contrasts]) if contrasts else []
    for c, a in zip(contrasts, cadj):
        c["p_holm"] = a
    print(f"{'k':>3}  {'partition':<18}{'contrast':<36}  {'delta':>8}  "
          f"{'95% CI':>19}  {'p_holm':>7}")
    print("-" * 92)
    for c in contrasts:
        star = "*" if c["p_holm"] < 0.05 and (c["lo"] > 0 or c["hi"] < 0) else " "
        print(f"{c['k']:>3}  {c['partition']:<18}{c['levels']:<36}  "
              f"{c['delta']:>+8.4f}  [{c['lo']:>+7.4f},{c['hi']:>+7.4f}]{star} "
              f"{c['p_holm']:>7.4f}")
    print("-" * 92)
    print(f"  Second declared family: {len(contrasts)} contrasts, Holm applied")
    print("  separately. A contrast whose interval covers zero means this study")
    print("  cannot show the improvement depends on that class -- which is not")
    print("  the same as showing it does not.")
    print()
    print("EXPLORATORY. This split has been observed since E9 and was used to")
    print("choose methods, so none of these intervals is a confirmatory test.")

    with ExperimentResult("E37", args.metrics_out,
                          title="静态提升按题型切片：模态、跨页、题型") as res:
        res.config(pool=args.pool, ks=ks, folds=args.folds,
                   comparison="out-of-fold nested-CV selection - paper-style E",
                   sample_unit="document", bootstrap=BOOT,
                   family_size=len(jobs), contrast_family_size=len(contrasts),
                   correction="Holm-Bonferroni, two separate families",
                   status="exploratory",
                   unevaluable_classes="pure text (n=1), unanswerable (n=0)")
        res.metric("n_questions", len(rows), unit="questions")
        res.metric("n_documents", len({r["doc"] for r in rows}),
                   unit="documents")
        for r in results:
            res.metric(
                f"delta_k{r['k']}_{r['partition']}_{r['level']}".replace(" ", "_"),
                r["delta"], unit="recall", ci=[r["lo"], r["hi"]],
                p=r["p_holm"], n=r["n_questions"],
                n_documents=r["n_documents"],
                desc="out-of-fold selected minus paper-style E, this slice only")
        for c in contrasts:
            res.metric(
                f"contrast_k{c['k']}_{c['partition']}".replace(" ", "_"),
                c["delta"], unit="recall", ci=[c["lo"], c["hi"]],
                p=c["p_holm"],
                desc=f"difference in improvement, {c['levels']}")
        if args.metrics_out:
            os.makedirs(args.metrics_out, exist_ok=True)
            csv_path = os.path.join(args.metrics_out, "per_question.csv")
            with open(csv_path, "w", encoding="utf-8") as fh:
                fh.write("question_uid,doc_name,modality,page_span,"
                         "question_type," +
                         ",".join(f"delta_k{k}" for k in ks) + "\n")
                for i, (q, r) in enumerate(zip(quids, rows)):
                    fh.write(
                        f"{q},{r['doc']},"
                        f"{parts['evidence modality'].get(q)},"
                        f"{parts['gold page span'].get(q)},"
                        f"\"{parts['question type'].get(q)}\"," +
                        ",".join(f"{deltas_by_k[k][0][i]:.6f}" for k in ks)
                        + "\n")


if __name__ == "__main__":
    main()
