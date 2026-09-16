"""Score a frozen E39 pair using document resampling and a predeclared margin."""
import argparse
import json
from pathlib import Path

import numpy as np

from eval_e29_paired import score_arm, load_jsonl
from expkit.cache_identity import file_hash
from expkit.results import ExperimentResult, add_output_args


def paired_interval(delta, docs, *, n_boot=10000, seed=20260905):
    if len(delta) != len(docs) or not len(delta) or n_boot < 100:
        raise ValueError("Need aligned nonempty pairs and at least 100 bootstrap draws")
    d = np.asarray(delta, dtype=float)
    if not np.isfinite(d).all():
        raise ValueError("Nonfinite score")
    keys = sorted(set(docs))
    if len(keys) < 2:
        raise ValueError("Need at least two documents")
    docs = np.asarray(docs)
    sums = np.array([d[docs == k].sum() for k in keys])
    counts = np.array([(docs == k).sum() for k in keys])
    pick = np.random.default_rng(seed).integers(0, len(keys), (n_boot, len(keys)))
    boot = sums[pick].sum(axis=1)/counts[pick].sum(axis=1)
    lo, hi = np.quantile(boot, [0.025, 0.975])
    return float(d.mean()), float(lo), float(hi)


def noninferior(ci_low, margin):
    if not np.isfinite(margin) or margin <= 0:
        raise ValueError("Margin must be positive and declared before generation")
    return bool(ci_low > -margin)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--static-responses", required=True)
    ap.add_argument("--routed-responses", required=True)
    add_output_args(ap)
    a = ap.parse_args()
    plan = json.loads(Path(a.plan).read_text(encoding="utf-8"))
    if (plan.get("status") != "approved_before_generation" or not plan.get("model")
            or plan.get("thinking") is None):
        raise ValueError("Approve/freeze the model, thinking and margin BEFORE generation")
    scored, docmaps, totals = {}, {}, {}
    reference = None
    for name, response in (("static", a.static_responses), ("routed", a.routed_responses)):
        dataset = plan["datasets"][name]
        if file_hash(dataset["path"]) != dataset["sha256"]:
            raise ValueError("Frozen input file changed")
        gold = load_jsonl(dataset["path"])
        design = {r["q_id"]: (r["doc_name"], r["question"], len(r["gold_quotes"])) for r in gold}
        if (len(design) != plan["n_questions"] or len(design) != len(gold)
                or len({r["doc_name"] for r in gold}) != plan["n_documents"]
                or sum(len(r["gold_quotes"]) for r in gold) != plan["gold_total"]):
            raise ValueError("Frozen sampling counts or gold denominator differ")
        if reference is not None and design != reference:
            raise ValueError("Pair questions or gold denominators differ")
        reference = design
        responses = load_jsonl(response)
        if any(r.get("model") != plan["model"] for r in responses):
            raise ValueError("Response model differs from the frozen plan")
        values, docs, _, _ = score_arm(dataset["path"], response)
        scored[name], docmaps[name] = values, docs
        totals[name] = sum(r.get("total_tok") or 0 for r in responses)
    if docmaps["static"] != docmaps["routed"]:
        raise ValueError("Pair identities/documents differ")
    ids = sorted(scored["static"])
    docs = [docmaps["static"][q] for q in ids]
    delta = [100*(scored["routed"][q] - scored["static"][q]) for q in ids]
    point, lo, hi = paired_interval(delta, docs)
    margin = plan["noninferiority_margin_f1_points"]
    passed = noninferior(lo, margin)
    print(f"routed - static: {point:+.3f} F1 points; document 95% CI [{lo:+.3f},{hi:+.3f}]")
    print(f"{len(ids)} questions / {len(set(docs))} documents; margin={margin}; noninferiority={passed}")
    with ExperimentResult("E39", a.metrics_out, title="GPU cascade paired citation F1") as res:
        res.config(pool="canonical", k=10, sample_unit="document", n_questions=len(ids),
                   n_documents=len(set(docs)), model=plan["model"], thinking=plan["thinking"],
                   n_gold_total=plan["gold_total"], n_gold_dropped=0, bootstrap=10000,
                   seed=20260905, margin_f1_points=margin, family="one primary comparison",
                   analysis="exploratory; fixed OOF decisions", answer_correctness_measured=False)
        res.metric("delta_quote_f1_routed_minus_static", point, ci=(lo, hi), unit="F1 points")
        res.metric("noninferiority_passed", int(passed))
        for name in scored:
            res.metric(f"quote_f1_{name}", 100*np.mean(list(scored[name].values())))
            res.metric(f"successful_response_total_tok_{name}", totals[name],
                       desc="successful responses only; reconcile failures/retries with API log")
        res.per_question([dict(question_uid=f"evaluation:{q}", doc_name=docmaps["static"][q],
                               delta_f1_points=d) for q, d in zip(ids, delta)])
        res.data_file(a.plan, a.static_responses, a.routed_responses)
        res.note("CI crossing zero never establishes equal quality. Noninferiority is relative "
                 "to the margin fixed before generation; this endpoint measures citations.")


if __name__ == "__main__":
    main()
