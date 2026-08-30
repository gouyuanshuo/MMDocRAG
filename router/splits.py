"""Freeze a document-disjoint train/val/test split of the evaluation set.

Why not the official split
--------------------------
The official dev and evaluation sets share 144 documents: 74.6% of evaluation
questions come from a document the dev set has already shown. Evidence style is
extremely consistent inside one document -- a 10-K is tables end to end, a
research report is figures end to end -- so a router trained across that overlap
can score well by recognising the document rather than by reading the question.
That inflates exactly the capability being measured.

This split therefore partitions by `doc_name`, so no document contributes
questions to more than one side.

Balancing
---------
Documents carry between 1 and 27 questions, so assigning documents uniformly
would not give balanced question counts. Documents are packed greedily, largest
first, into whichever split is furthest below its target share -- the standard
longest-processing-time heuristic. Packing runs per domain so the domain mix is
preserved rather than left to chance.

Two domains cannot be stratified: Government and News have exactly one document
each (3 and 2 questions). Each lands wholly in one split; the manifest records
which, and they are too small to draw conclusions from either way.

The result is written to manifests/ as JSON and is meant to be frozen: every
Phase 1A.5 / 2 / 3 experiment reads the same file, so numbers stay comparable
across runs.

Run:
    python -m router.splits --write
"""

import argparse
import collections
import json
import os
import sqlite3
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO_ROOT, "router", "outcomes.sqlite")
DEFAULT_OUT = os.path.join(REPO_ROOT, "manifests", "split_doc_disjoint.json")

SHARES = {"train": 0.60, "val": 0.20, "test": 0.20}


def load_docs(db_path, setting):
    con = sqlite3.connect(db_path)
    rows = con.execute(
        "SELECT doc_name, domain, q_id FROM questions WHERE setting = ? "
        "ORDER BY q_id", (setting,)).fetchall()
    con.close()
    docs = collections.OrderedDict()
    for doc, domain, q_id in rows:
        d = docs.setdefault(doc, {"domain": domain, "q_ids": []})
        d["q_ids"].append(q_id)
        # A document has one domain; assert rather than silently keep the first.
        if d["domain"] != domain:
            raise ValueError(f"{doc}: two domains, {d['domain']!r} and {domain!r}")
    return docs


def pack(docs, shares):
    """Greedy longest-processing-time packing, per domain."""
    by_domain = collections.OrderedDict()
    for doc, info in docs.items():
        by_domain.setdefault(info["domain"], []).append(doc)

    assign, totals = {}, {k: 0 for k in shares}
    for domain, names in by_domain.items():
        # Largest documents first: they are the ones that can unbalance a split,
        # so place them while there is still room to compensate.
        # Ties break on the document name, which keeps the packing deterministic
        # without needing a random seed.
        names.sort(key=lambda n: (-len(docs[n]["q_ids"]), n))
        dom_totals = {k: 0 for k in shares}
        dom_size = sum(len(docs[n]["q_ids"]) for n in names)
        for name in names:
            size = len(docs[name]["q_ids"])
            # Deficit against this domain's own target, so each domain is
            # split ~60/20/20 rather than only the corpus as a whole.
            target = lambda k: shares[k] * dom_size
            pick = min(shares, key=lambda k: (dom_totals[k] - target(k), k))
            assign[name] = pick
            dom_totals[pick] += size
            totals[pick] += size
    return assign, totals


def report(docs, assign, totals):
    n_q = sum(len(v["q_ids"]) for v in docs.values())
    print(f"{'split':<8}{'docs':>7}{'questions':>11}{'share':>9}{'target':>9}")
    for k in SHARES:
        d = sum(1 for v in assign.values() if v == k)
        print(f"{k:<8}{d:>7}{totals[k]:>11}{totals[k] / n_q:>8.1%}{SHARES[k]:>9.0%}")
    print(f"{'TOTAL':<8}{len(docs):>7}{n_q:>11}")

    print(f"\n{'domain':<45}{'train':>7}{'val':>6}{'test':>6}")
    per = collections.defaultdict(lambda: collections.Counter())
    for doc, info in docs.items():
        per[info["domain"]][assign[doc]] += len(info["q_ids"])
    for domain in sorted(per, key=lambda d: -sum(per[d].values())):
        c = per[domain]
        print(f"{domain:<45}{c['train']:>7}{c['val']:>6}{c['test']:>6}")

    overlap = collections.Counter(assign.values())
    assert sum(overlap.values()) == len(docs), "every document must be assigned once"
    print("\ndocument-disjoint: every doc_name appears in exactly one split")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--setting", default="20",
                    help="which gold file defines the question set; both "
                         "settings cover the same questions, so the split is shared")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--write", action="store_true",
                    help="write the manifest; without it, only report")
    args = ap.parse_args()

    docs = load_docs(args.db, args.setting)
    assign, totals = pack(docs, SHARES)
    report(docs, assign, totals)

    if not args.write:
        print(f"\n(dry run -- pass --write to freeze it to {os.path.relpath(args.out, REPO_ROOT)})")
        return

    if os.path.exists(args.out):
        print(f"\n[stop] {args.out} already exists. This split is meant to be "
              f"frozen; delete it deliberately if you really mean to re-cut it.")
        return

    payload = {
        "name": "doc_disjoint_v1",
        "description": "Document-disjoint 60/20/20 split of the MMDocRAG "
                       "evaluation set, packed largest-document-first within "
                       "each domain.",
        "shares": SHARES,
        "built_from": {"db": os.path.relpath(args.db, REPO_ROOT),
                       "setting": args.setting},
        "deterministic": "no RNG; ties break on document name",
        "counts": {k: totals[k] for k in SHARES},
        "doc_to_split": {d: assign[d] for d in sorted(docs)},
        "q_id_to_split": {str(q): assign[d]
                          for d, v in docs.items() for q in v["q_ids"]},
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=False)
    print(f"\nfrozen -> {os.path.relpath(args.out, REPO_ROOT)}")


if __name__ == "__main__":
    main()
