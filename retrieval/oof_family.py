"""Audit the eight E27/E40 OOF comparisons as one exploratory Holm family."""
import argparse
import csv
import json
import os
from pathlib import Path

import numpy as np

from expkit import paths
from expkit.results import ExperimentResult, add_output_args
from retrieval.ablation import holm
from router.phase3_cells import cluster_boot


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default=os.environ.get("MMDOCRAG_RUN_ID"))
    add_output_args(ap)
    a = ap.parse_args()
    if not a.run:
        ap.error("pass --run with BOTH E27 and E40; latest is deliberately not used")
    root = Path(paths.run_dir(a.run))
    cells, inputs = {}, []
    for eid in ("E27", "E40"):
        for p in (root/"experiments"/eid).rglob("metrics.json"):
            m = json.loads(p.read_text(encoding="utf-8"))
            c = m.get("config", {})
            if c.get("analysis") != "nested_cv":
                continue
            key = (eid, c["pool"], c["k"])
            if key in cells:
                raise ValueError(f"Duplicate OOF cell: {key}")
            csv_path = p.with_name("per_question.csv")
            with csv_path.open(encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.DictReader(fh))
            uids = [r["question_uid"] for r in rows]
            if len(set(uids)) != len(uids) or len(rows) != c["n_questions"]:
                raise ValueError("OOF prediction identities/counts disagree")
            d = np.array([float(r["delta_vs_E"]) for r in rows])
            docs = [r["doc_name"] for r in rows]
            point, lo, hi, pval, nd = cluster_boot(d, docs, np.random.default_rng(20260905), n_boot=10000)
            cells[key] = dict(delta=point, lo=lo, hi=hi, p_raw=pval,
                              n_questions=len(rows), n_documents=nd,
                              gold_total=sum(int(r["n_gold_total"]) for r in rows),
                              gold_unmapped=sum(int(r["n_gold_unmapped"]) for r in rows))
            inputs += [str(p), str(csv_path)]
    expected = {(e, p, k) for e in ("E27", "E40") for p in ("canonical", "selfbuilt") for k in (10, 20)}
    if set(cells) != expected:
        raise ValueError(f"Incomplete family. Missing: {expected-set(cells)}")
    keys = sorted(cells)
    adjusted = holm([cells[k]["p_raw"] for k in keys])
    with ExperimentResult("E41", a.metrics_out, title="OOF comparison family audit") as res:
        res.config(analysis="oof_family_audit", sample_unit="document", source_run=a.run,
                   family_size=8, bootstrap=10000, seed=20260905,
                   status="exploratory post-hoc multiplicity sensitivity", selection_rerun=False)
        for key, pv in zip(keys, adjusted):
            v = cells[key]
            reject = pv < 0.05 and (v["lo"] > 0 or v["hi"] < 0)
            print(key, v, "Holm p", float(pv), "reject", reject)
            res.metric("delta:" + ":".join(map(str, key)), v["delta"], ci=(v["lo"], v["hi"]),
                       p_raw=v["p_raw"], p_holm=float(pv), significant=bool(reject),
                       pool=key[1], k=key[2], original_experiment=key[0],
                       n_questions=v["n_questions"], n_documents=v["n_documents"],
                       n_gold_total=v["gold_total"], n_gold_mapped=v["gold_total"]-v["gold_unmapped"],
                       n_gold_unmapped=v["gold_unmapped"], n_gold_dropped=0)
        res.data_file(*inputs)
        res.note("Family specified for this audit after historical results were observed. "
                 "This is sensitivity to multiplicity, not retrospective preregistration. "
                 "Intervals condition on saved OOF policies; they do not refit the selection algorithm.")


if __name__ == "__main__":
    main()
