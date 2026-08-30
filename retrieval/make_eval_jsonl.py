"""Emit an evaluation JSONL in the official schema, with OUR retrieved quotes.

Why this shape rather than a new generation script
--------------------------------------------------
`inference_api.py` reads `text_quotes` / `img_quotes` from the official
evaluation file and `eval_all.py` scores the responses against `gold_quotes`.
If the retrieved evidence is written into that same schema, both official
scripts run completely unchanged, and the end-to-end number is produced by the
same code path that reproduces the paper's published metrics bit-for-bit. A
bespoke generator would have re-implemented citation parsing and scoring, and
any divergence there would be indistinguishable from a real effect.

The canonical pool is used deliberately: its retrieval units *are* the official
quotes, so a citation maps one-to-one onto an official quote id and
quote-selection F1 keeps exactly the meaning it has in the paper. On the
self-built pool a "quote" is a chunk we invented, and F1 would silently become a
different quantity.

The denominator, again
----------------------
`gold_quotes` must list ALL gold for the question, not just the gold that
retrieval happened to surface. Listing only retrieved gold would measure "given
what you were shown, did you cite it correctly" -- which is precisely the
quantity that is blind to retrieval quality, and would guarantee a null result
no matter how much better the retrieval got. Gold that was not retrieved is
therefore emitted under a sentinel id that appears in no shown quote, so the
generator cannot cite it and it scores as a false negative. That is what makes
retrieval quality propagate into F1.

Both denominators are recorded in the sidecar so the conditional version can be
reported separately as a diagnostic.

    BLEU / ROUGE ARE NOT COMPARABLE HERE and must not be reported. The reference
    `answer_interleaved` embeds the official local quote numbering, and this file
    renumbers the quotes. Only quote-selection precision / recall / F1 carry over.

Run:
    python -m retrieval.make_eval_jsonl --config paper --n 100 --k 10
    python -m retrieval.make_eval_jsonl --config ours  --n 100 --k 10
"""

import argparse
import collections
import json
import os
import random
import sqlite3
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retrieval.eval_stack_v2 import (DEFAULT_COLQWEN, DEFAULT_DB,      # noqa: E402
                                     DEFAULT_QUOTES, PAPER_QUOTA, build)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO_ROOT, "retrieval", "e2e")
SUBSET_MANIFEST = os.path.join(REPO_ROOT, "manifests", "e29_subset.json")
SEED = 20260825

# Retriever pair and quota per configuration. "ours" uses the quota the nested
# CV inner loop selected at k=10 in all five folds.
CONFIGS = {
    "paper": {"text": "dense", "visual": "colqwen", "quota": None},
    "ours":  {"text": "rrf",   "visual": "rrf",     "quota": {10: (4, 6), 15: (7, 8), 20: (9, 11)}},
}


def pick_subset(rows, n, seed=SEED):
    """Document-stratified sample: spread across documents, not clustered."""
    by_doc = collections.defaultdict(list)
    for r in rows:
        by_doc[r["doc"]].append(r["quid"])
    rng = random.Random(seed)
    for d in by_doc:
        by_doc[d].sort()
        rng.shuffle(by_doc[d])
    docs = sorted(by_doc)
    rng.shuffle(docs)
    out, i = [], 0
    # round-robin over documents so every document contributes before any
    # document contributes twice -- keeps the document-cluster bootstrap honest
    while len(out) < n:
        progressed = False
        for d in docs:
            if i < len(by_doc[d]):
                out.append(by_doc[d][i])
                progressed = True
                if len(out) >= n:
                    break
        if not progressed:
            break
        i += 1
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--quotes", default=DEFAULT_QUOTES)
    ap.add_argument("--colqwen", default=DEFAULT_COLQWEN)
    ap.add_argument("--config", required=True, choices=sorted(CONFIGS))
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--n", type=int, default=600,
                    help="size of the FROZEN subset; 0 = all questions. Sized so "
                         "the retrieval delta itself clears significance: the "
                         "document-cluster CI half-width scales as "
                         "0.0144*sqrt(2000/n), and the effect is +0.054, so "
                         "n>~555 is needed before a downstream null is "
                         "interpretable rather than merely underpowered.")
    ap.add_argument("--limit", type=int, default=0,
                    help="emit only the first LIMIT questions of the frozen "
                         "subset. The subset is stored in round-robin document "
                         "order, so any prefix is itself document-stratified and "
                         "a pilot's generations are reusable when scaling up.")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    k = args.k
    cfg = CONFIGS[args.config]
    quota = cfg["quota"][k] if cfg["quota"] else PAPER_QUOTA[k]

    con = sqlite3.connect(args.db)
    ev = {e: (t, txt, desc, img) for e, t, txt, desc, img in con.execute(
        "SELECT evidence_id, type, text, img_description, img_path "
        "FROM canonical_evidence")}
    # answer_interleaved is setting-dependent (3,890/4,055 questions differ
    # between the 15- and 20-quote settings) and lives in its own table.
    meta = {u: (qid, doc, dom, q, emt, qt, ans, ai, old) for u, qid, doc, dom, q,
            emt, qt, ans, ai, old in con.execute(
        "SELECT q.question_uid, q.q_id, q.doc_name, q.domain, q.question, "
        "q.evidence_modality_type, q.question_type, q.answer_short, "
        "s.answer_interleaved, q.old_id "
        "FROM questions q LEFT JOIN question_settings s "
        "  ON s.question_uid = q.question_uid AND s.setting = '20' "
        "WHERE q.split='evaluation'")}
    con.close()

    rows, _ = build(args.db, args.quotes, args.colqwen, "canonical")
    if args.n:
        if os.path.exists(SUBSET_MANIFEST):
            keep = set(json.load(open(SUBSET_MANIFEST, encoding="utf-8"))["quids"])
            print(f"reusing frozen subset: {len(keep)} questions")
        else:
            ordered = pick_subset(rows, args.n)
            keep = set(ordered)
            os.makedirs(os.path.dirname(SUBSET_MANIFEST), exist_ok=True)
            json.dump({"n": len(keep), "seed": SEED, "k": k,
                       "stratification": "round-robin over documents",
                       "quids": sorted(keep), "quids_ordered": ordered},
                      open(SUBSET_MANIFEST, "w", encoding="utf-8"), indent=2)
            print(f"froze new subset: {len(keep)} questions -> {SUBSET_MANIFEST}")
        order = {q: i for i, q in enumerate(
            json.load(open(SUBSET_MANIFEST, encoding="utf-8"))["quids_ordered"])}
        rows = sorted((r for r in rows if r["quid"] in keep),
                      key=lambda r: order[r["quid"]])
        if args.limit:
            rows = rows[:args.limit]
            print(f"pilot prefix: first {len(rows)} of the frozen subset")

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = args.out or os.path.join(
        OUT_DIR, f"eval_{args.config}_k{k}_n{len(rows)}.jsonl")
    side_path = out_path.replace(".jsonl", "_sidecar.json")

    n_gold_total = n_gold_shown = 0
    side = []
    with open(out_path, "w", encoding="utf-8") as fh:
        for r in rows:
            quid = r["quid"]
            t_ids = r["rank"][cfg["text"]]["text"][:quota[0]]
            i_ids = r["rank"][cfg["visual"]]["visual"][:quota[1]]
            qid, doc, dom, question, emt, qtype, ans, ai, old = meta[quid]

            text_quotes, img_quotes, local = [], [], {}
            for n, e in enumerate(t_ids, 1):
                local[e] = f"text{n}"
                text_quotes.append({"quote_id": f"text{n}", "type": "text",
                                    "text": ev[e][1] or ""})
            for n, e in enumerate(i_ids, 1):
                local[e] = f"image{n}"
                img_quotes.append({"quote_id": f"image{n}", "type": ev[e][0],
                                   "img_path": ev[e][3] or "",
                                   "img_description": ev[e][2] or ""})

            gold_local, missed = [], 0
            for g in sorted(r["gold_mapped"]):
                if g in local:
                    gold_local.append(local[g])
                else:
                    # sentinel: no shown quote carries this id, so it can never
                    # be cited and scores as a false negative
                    missed += 1
                    gold_local.append(
                        f"{'image' if ev[g][0] != 'text' else 'text'}{900 + missed}")
            n_gold_total += len(gold_local)
            n_gold_shown += len(gold_local) - missed

            fh.write(json.dumps({
                "q_id": qid, "doc_name": doc, "domain": dom, "question": question,
                "evidence_modality_type": json.loads(emt) if isinstance(emt, str)
                and emt.startswith("[") else emt,
                "question_type": qtype,
                "text_quotes": text_quotes, "img_quotes": img_quotes,
                "gold_quotes": gold_local,
                "answer_short": ans,
                "answer_interleaved": ai,     # kept for schema parity; NOT scorable
                "old_id": old,
            }, ensure_ascii=False) + "\n")
            side.append({"q_id": qid, "question_uid": quid, "doc_name": doc,
                         "n_gold_total": len(gold_local),
                         "n_gold_retrieved": len(gold_local) - missed})

    json.dump({"config": args.config, "k": k, "quota": list(quota),
               "text_retriever": cfg["text"], "visual_retriever": cfg["visual"],
               "pool": "canonical", "n_questions": len(rows),
               "n_documents": len({r["doc"] for r in rows}),
               "n_gold_total": n_gold_total, "n_gold_retrieved": n_gold_shown,
               "retrieval_recall_check": round(n_gold_shown / max(n_gold_total, 1), 4),
               "bleu_rouge_valid": False,
               "note": "gold_quotes includes unretrieved gold under sentinel ids "
                       "so F1 is unconditional on retrieval",
               "rows": side},
              open(side_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    print(f"config={args.config}  text={cfg['text']} visual={cfg['visual']} "
          f"quota {quota[0]}/{quota[1]}")
    print(f"questions {len(rows)} over {len({r['doc'] for r in rows})} documents")
    print(f"gold items {n_gold_total}, of which retrieved {n_gold_shown} "
          f"({n_gold_shown / max(n_gold_total, 1):.4f})  <- matches the recall "
          f"this config scores")
    print(f"wrote {out_path}")
    print(f"wrote {side_path}")


if __name__ == "__main__":
    main()
