"""Freeze the E36 GPU cascade for paired generation, without making API calls."""
import argparse
import csv
import json
import sqlite3
from pathlib import Path

from expkit.cache_identity import file_hash
from expkit.results import atomic_json
from expkit.paths import REPO_ROOT
from router import actions as A
from retrieval.eval_stack_v2 import DEFAULT_DB, BALANCED_QUOTA


def emit(row, question, evidence, action, quota):
    """Official quote schema, with every unretrieved gold retained as a miss."""
    if row["n_unmapped"]:
        raise ValueError("E39 requires fully mapped canonical gold")
    out = {k: question[k] for k in ("q_id", "doc_name", "question", "domain",
                                    "question_type", "answer_short")}
    out["question_uid"] = row["quid"]
    out["text_quotes"], out["img_quotes"] = [], []
    local = {}
    for branch, retriever, count in zip(("text", "visual"), action, quota):
        for i, eid in enumerate(row["rank"][retriever][branch][:count], 1):
            ev = evidence[eid]
            label = f"{'text' if branch == 'text' else 'image'}{i}"
            local[eid] = label
            quote = dict(quote_id=label, type=ev["type"])
            if branch == "text":
                quote["text"] = ev["text"] or ""
                out["text_quotes"].append(quote)
            else:
                quote.update(img_description=ev["img_description"] or "",
                             img_path=ev["img_path"] or "")
                out["img_quotes"].append(quote)
    out["gold_quotes"] = [local.get(eid, f"{'text' if evidence[eid]['type']=='text' else 'image'}_unretrieved_{i}")
                          for i, eid in enumerate(sorted(row["gold_mapped"]), 1)]
    if len(out["gold_quotes"]) != row["n_total"]:
        raise ValueError("Gold denominator changed while preparing generation")
    return out


def prepare(router_dir, out_dir, subset, margin):
    router_dir, out = Path(router_dir), Path(out_dir)
    if (out / "plan.json").exists():
        raise ValueError("Plan already exists; use a new output directory")
    payload = json.loads((router_dir / "metrics.json").read_text(encoding="utf-8"))
    c = payload["config"]
    want = dict(pool="canonical", k=10, policy="B", features="shape+firstpass",
                quota="5/5", cheap_action=A.action_label(("dense", "bm25")),
                expensive_action=A.action_label(("rrf", "colqwen")))
    if any(c.get(k) != v for k, v in want.items()):
        raise ValueError(f"Not the frozen E36 GPU cascade: expected {want}")
    with (router_dir / "per_question.csv").open(encoding="utf-8-sig", newline="") as fh:
        decisions = list(csv.DictReader(fh))
    by_uid = {r["question_uid"]: r for r in decisions}
    if len(by_uid) != len(decisions):
        raise ValueError("Duplicate router decision")
    rows, _ = A.load("canonical", 10, c["dense_model"])
    if set(by_uid) != {r["quid"] for r in rows}:
        raise ValueError("Router decision set does not cover the evaluation population")
    frozen = json.loads(Path(subset).read_text(encoding="utf-8"))
    uids = frozen["quids_ordered"]
    if len(uids) != len(set(uids)) or set(uids) != set(frozen["quids"]):
        raise ValueError("Invalid frozen subset")
    row_map = {r["quid"]: r for r in rows}
    db = sqlite3.connect(Path(DEFAULT_DB).resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    questions = {r["question_uid"]: dict(r) for r in db.execute("SELECT * FROM questions")}
    evidence = {r["evidence_id"]: dict(r) for r in db.execute("SELECT * FROM canonical_evidence")}
    db.close()
    cheap, expensive = ("dense", "bm25"), ("rrf", "colqwen")
    arms = {name: [] for name in ("static", "routed", "cheap")}
    upgraded = []
    for uid in uids:
        r, d = row_map[uid], by_uid[uid]
        if d["doc_name"] != r["doc"] or d["escalate_at_B015"] not in ("0", "1"):
            raise ValueError("Invalid decision identity or non-Boolean mask")
        escalation = d["escalate_at_B015"] == "1"
        upgraded.append(escalation)
        for name, action in (("static", expensive), ("cheap", cheap),
                             ("routed", expensive if escalation else cheap)):
            arms[name].append(emit(r, questions[uid], evidence, action, BALANCED_QUOTA[10]))
    out.mkdir(parents=True, exist_ok=True)
    for name, records in arms.items():
        path = out / f"evaluation_e39_{name}.jsonl"
        path.write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in records), encoding="utf-8")
    n = len(uids)
    plan = dict(experiment="E39", status="prepared_not_generated", exploratory=True,
                n_questions=n, n_documents=len({row_map[u]["doc"] for u in uids}),
                pool="canonical", k=10, quota=[5, 5], budget_population=0.15,
                n_escalated_subset=sum(upgraded), escalation_rate_subset=sum(upgraded)/n,
                n_escalated_population=sum(int(r["escalate_at_B015"]) for r in decisions),
                n_population=len(decisions),
                cheap_action=list(cheap), expensive_action=list(expensive),
                dense_model=c["dense_model"],
                primary_comparison="routed - static quote-selection F1",
                noninferiority_margin_f1_points=margin,
                margin_status="proposed; must be justified and approved before generation",
                decision_rule="lower bound of paired document-bootstrap two-sided 95% CI > -margin",
                secondary="cheap arm diagnoses whether routing adds value; no same-quality claim from CI crossing zero",
                api_calls_made=0, candidate_pair_requests=2*n,
                model=None, thinking=None,
                approval_needed="model, explicit thinking configuration, token budget, noninferiority margin",
                existing_E29_responses_reusable=False,
                reuse_reason="E29 uses different retrievers/quotas; shared q_id does not identify a request",
                cpu_passes_static=A.cost(expensive)["cpu_passes"],
                gpu_passes_static=1,
                cascade_passes_subset=A.cascade_cost(cheap, expensive, sum(upgraded)/n),
                gold_total=sum(len(r["gold_quotes"]) for r in arms["static"]),
                sources={str(p): file_hash(p) for p in
                         [router_dir/"metrics.json", router_dir/"per_question.csv", Path(subset)]},
                datasets={name: dict(path=str(out/f"evaluation_e39_{name}.jsonl"),
                                     sha256=file_hash(out/f"evaluation_e39_{name}.jsonl"))
                          for name in arms})
    atomic_json(str(out/"plan.json"), plan)
    plan["artifact_bytes_before_final_plan_write"] = sum(p.stat().st_size for p in out.iterdir() if p.is_file())
    atomic_json(str(out/"plan.json"), plan)
    print(json.dumps({k:v for k,v in plan.items() if k not in ("sources", "datasets")}, ensure_ascii=False, indent=2))
    return plan


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--router-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--subset", default=str(Path(REPO_ROOT)/"manifests/e29_subset.json"))
    ap.add_argument("--proposed-margin", type=float, default=2.0)
    a = ap.parse_args()
    if not 0 < a.proposed_margin < 100:
        ap.error("margin must be in F1 points, between 0 and 100")
    prepare(a.router_dir, a.out, a.subset, a.proposed_margin)


if __name__ == "__main__":
    main()
