"""E29: does the retrieval gain survive the generator?

`eval_all.py` reports each arm's mean quote-selection F1 separately. Two means and
a subtraction is not a result: the arms are paired (same 600 questions, same gold,
same model, same prompt -- only the retrieved candidate block differs), and the
questions are nested inside documents. Reading "+2.9" off two aggregates ignores
both facts, and the second one matters here because one document contributes many
questions, so treating questions as independent would understate the interval.

So this scores every question in both arms, pairs them by q_id, and resamples
DOCUMENTS. The estimator is exactly `eval_all.py`'s `final_f1` -- the mean of
per-question F1 -- and the per-arm means are asserted against the numbers
`eval_all.py` printed. If the assertion fails, this file is measuring something
else and its interval is meaningless, so it refuses to report.

Scoring reuses `eval_all.strip_thinking`, `extract_citations` and `get_scores`
verbatim. Reimplementing them would make E29's F1 incomparable to every other F1
in this project, which is the whole point of routing through the published code
path.

What this can and cannot show
-----------------------------
Both arms use `gemini-3.6-flash`, which is NOT in the paper's model table, so the
absolute F1 is not comparable to any published row. Only the paired difference is
interpretable. A gold quote the retriever never surfaced is scored as a miss --
the candidate block is all the generator can cite from -- which is what makes F1
sensitive to retrieval at all.

Run:
    python eval_e29_paired.py
    python eval_e29_paired.py --metrics-out artifacts/runs/<id>/experiments/E29
"""

import argparse
import collections
import io
import json
import os
import sys

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from eval_all import strip_thinking, extract_citations, get_scores  # noqa: E402
from expkit.results import ExperimentResult, add_output_args        # noqa: E402

BOOTSTRAP = 4000
SEED = 20260829
ARMS = [
    ("paper", "dataset/evaluation_paperk10.jsonl",
     "response/gemini-3.6-flash_pure-text_quotespaperk10_response.jsonl",
     "dense text + ColQwen visual, quota 7/3 (closest local paper-style config)"),
    ("ours", "dataset/evaluation_oursk10.jsonl",
     "response/gemini-3.6-flash_pure-text_quotesoursk10_response.jsonl",
     "RRF text + RRF visual, quota 4/6 (the configuration nested CV selected)"),
]
# What eval_all.py printed for these two files. Asserted, not assumed.
EXPECTED_FINAL_F1 = {"paper": 55.2, "ours": 58.1}


def load_jsonl(path):
    with io.open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def score_arm(gold_path, resp_path):
    """Per-question F1, keyed by q_id, using eval_all's own scorers."""
    gold = {r["q_id"]: r for r in load_jsonl(gold_path)}
    resp = {r["q_id"]: r for r in load_jsonl(resp_path)}
    f1, docs, missing = {}, {}, []
    for qid, g in gold.items():
        r = resp.get(qid)
        if r is None or not r.get("response"):
            missing.append(qid)
            continue
        _p, _r, f = get_scores(g["gold_quotes"],
                               extract_citations(strip_thinking(r["response"]))[2])
        f1[qid] = f
        docs[qid] = g["doc_name"]
    return f1, docs, missing, len(gold)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bootstrap", type=int, default=BOOTSTRAP)
    add_output_args(ap)
    args = ap.parse_args()

    scored, docs_of, per_arm = {}, {}, {}
    print("=" * 84)
    print("E29 PAIRED: retrieval configuration -> generation quality")
    print("=" * 84)
    for name, gold_path, resp_path, desc in ARMS:
        f1, docs, missing, n_gold = score_arm(gold_path, resp_path)
        scored[name] = f1
        docs_of.update(docs)
        mean = 100.0 * sum(f1.values()) / len(f1)
        per_arm[name] = {"mean_f1": mean, "n": len(f1), "n_gold": n_gold,
                         "missing": missing, "desc": desc}
        want = EXPECTED_FINAL_F1[name]
        agree = abs(mean - want) < 0.05
        print(f"  {name:<6} n={len(f1)}/{n_gold}  mean F1 = {mean:.2f}"
              f"   eval_all printed {want}   "
              f"{'MATCH' if agree else '*** MISMATCH ***'}")
        print(f"         {desc}")
        if not agree:
            raise SystemExit(
                f"\nRefusing to report. This file's estimator does not reproduce "
                f"eval_all.py's final_f1 for the {name} arm ({mean:.2f} vs {want}). "
                f"An interval around a different quantity than the headline is "
                f"worse than no interval.")

    common = sorted(set(scored["paper"]) & set(scored["ours"]))
    only_p = sorted(set(scored["paper"]) - set(scored["ours"]))
    only_o = sorted(set(scored["ours"]) - set(scored["paper"]))
    print()
    print(f"  paired on {len(common)} questions "
          f"(paper-only {len(only_p)}, ours-only {len(only_o)})")
    if only_p or only_o:
        print("  NOTE: unpaired questions are excluded from the paired test only; "
              "each arm's mean above still uses everything that arm scored.")

    by_doc = collections.defaultdict(list)
    for qid in common:
        by_doc[docs_of[qid]].append(qid)
    doc_keys = sorted(by_doc)
    idx = {q: i for i, q in enumerate(common)}
    a = np.array([scored["ours"][q] for q in common])
    b = np.array([scored["paper"][q] for q in common])
    d = a - b
    doc_rows = [np.array([idx[q] for q in by_doc[k]]) for k in doc_keys]

    delta = 100.0 * d.mean()
    rng = np.random.default_rng(SEED)
    pick = rng.integers(0, len(doc_keys), size=(args.bootstrap, len(doc_keys)))
    boot = np.empty(args.bootstrap)
    sums = np.array([d[r].sum() for r in doc_rows])
    cnts = np.array([len(r) for r in doc_rows])
    for i in range(args.bootstrap):
        p = pick[i]
        boot[i] = 100.0 * sums[p].sum() / cnts[p].sum()
    lo, hi = np.percentile(boot, [2.5, 97.5])
    # Two-sided bootstrap p, floored at the resolution the design can resolve.
    p_two = 2.0 * min((boot <= 0).mean(), (boot >= 0).mean())
    p_two = max(p_two, 1.0 / args.bootstrap)
    sig = lo > 0 or hi < 0

    # A question-level interval is computed only as a contrast. Note it is NOT
    # automatically the narrower of the two: on this data it comes out slightly
    # WIDER. Clustering is used here because the sampling unit is the document,
    # not because it reliably produces a more conservative number -- whether it
    # widens or narrows depends on the within-document correlation of the paired
    # difference, and asserting the direction in advance would be a guess.
    qpick = rng.integers(0, len(common), size=(args.bootstrap, len(common)))
    qboot = 100.0 * d[qpick].mean(axis=1)
    qlo, qhi = np.percentile(qboot, [2.5, 97.5])

    wins = int((d > 0).sum())
    losses = int((d < 0).sum())
    ties = int((d == 0).sum())

    print()
    print("-" * 84)
    print(f"  ours - paper           {delta:+.2f} F1 points")
    print(f"  document-cluster 95%   [{lo:+.2f}, {hi:+.2f}]"
          f"   {'excludes zero' if sig else 'CROSSES ZERO'}")
    print(f"  bootstrap p (2-sided)  {p_two:.4f}"
          f"{'  (at the 1/B floor)' if p_two <= 1.0 / args.bootstrap else ''}")
    print(f"  resampling unit        {len(doc_keys)} documents, "
          f"{len(common)} questions")
    print(f"  per-question wins      {wins} better / {losses} worse / {ties} equal")
    print("-" * 84)
    wider = "wider" if (qhi - qlo) > (hi - lo) else "narrower"
    print(f"  [question-level 95%    [{qlo:+.2f}, {qhi:+.2f}]  <- NOT the result: "
          f"wrong sampling unit.")
    print(f"   ignoring nesting]      Here it happens to be {wider} than the "
          f"clustered one. The")
    print(f"                          clustered interval is used because "
          f"questions nest in")
    print(f"                          documents, not because it is the more "
          f"conservative number.")
    print("-" * 84)
    print()
    print("READING THIS")
    print("  Both arms use gemini-3.6-flash, which is NOT in the paper's model")
    print("  table. The absolute F1 is therefore not comparable to any published")
    print("  row; only the paired difference above is interpretable.")
    if not sig:
        print("  The interval crosses zero. With 600 questions in "
              f"{len(doc_keys)} documents this")
        print("  is a POWER statement, not evidence of no effect -- do not write it")
        print("  up as a trend.")

    with ExperimentResult("E29", args.metrics_out,
                          title="端到端：检索改进能否传导到生成质量") as res:
        res.config(model="gemini-3.6-flash", mode="pure-text", k=10,
                   n_questions=len(common), sample_unit="document",
                   n_documents=len(doc_keys), bootstrap=args.bootstrap,
                   estimator="mean of per-question F1 (eval_all.final_f1)",
                   scorer="eval_all.extract_citations + get_scores",
                   comparable_to_paper=False)
        for name in ("paper", "ours"):
            res.metric(f"final_f1_{name}", per_arm[name]["mean_f1"],
                       unit="F1 points", desc=per_arm[name]["desc"],
                       n_scored=per_arm[name]["n"])
        res.metric("delta_final_f1[ours - paper]", delta, ci=(lo, hi),
                   unit="F1 points", bootstrap_unit="document",
                   n_documents=len(doc_keys), p_two_sided=p_two,
                   desc="paired difference; same questions, gold, model and prompt "
                        "-- only the retrieved candidate block differs")
        res.metric("delta_final_f1_question_bootstrap", delta, ci=(qlo, qhi),
                   unit="F1 points", bootstrap_unit="question",
                   desc="WRONG SAMPLING UNIT, recorded only as a contrast. "
                        "Do not cite. On this data it is not the narrower of "
                        "the two, so it is wrong for the reason that questions "
                        "nest in documents -- not for being over-confident.")
        res.metric("questions_better", wins, unit="questions")
        res.metric("questions_worse", losses, unit="questions")
        res.metric("questions_equal", ties, unit="questions")
        res.per_question([
            {"question_uid": q, "doc_name": docs_of[q],
             "f1_paper": scored["paper"][q], "f1_ours": scored["ours"][q],
             "delta": scored["ours"][q] - scored["paper"][q]} for q in common])
        res.note("Both arms use gemini-3.6-flash, which is not in the paper's "
                 "model table. Absolute F1 is not comparable to any published "
                 "row; only the paired difference is interpretable.")
        res.note("Per-arm means were asserted against eval_all.py's printed "
                 f"final_f1 ({EXPECTED_FINAL_F1}) before any interval was "
                 "computed.")
    if args.metrics_out:
        print(f"\nwrote metrics to {args.metrics_out}")


if __name__ == "__main__":
    main()
