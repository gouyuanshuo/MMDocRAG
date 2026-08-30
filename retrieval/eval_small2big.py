"""RQ3, second half: decouple the ranking unit from the returned unit.

The granularity sweep (`eval_granularity.py`) varies one knob, and that knob is
overloaded. A chunk size decides two different things at once:

    - how precisely the retriever can score a passage. A 100-character chunk is
      scored on its own words; a 1,200-character chunk pools a relevant sentence
      with a page of unrelated text, and BM25 averages the signal away.
    - how much of the gold arrives per slot once a passage is picked.

Those pull in opposite directions, which is why a single-knob sweep tends to
come out flat: the two effects cancel. Separating them is the actual RQ3
question, and it is a routing question in the sense the proposal means -- the
unit you *search* need not be the unit you *spend budget on*.

Arms, all scored at the same token budgets so nothing wins by spending more:

    coarse-direct   rank coarse chunks, return coarse chunks     (the baseline)
    fine-direct     rank fine chunks, return fine chunks
    small-to-big    rank FINE chunks, return their coarse PARENTS

The third arm is the hypothesis: fine-grained scoring to decide *where* to look,
coarse-grained units to decide *what to send*. Deduplicated, because two fine
chunks often share a parent -- and that deduplication is itself a saving, since
the budget then holds more distinct regions.

Parenthood is recovered by content, not by construction: the two corpora are
built independently from the same PyMuPDF blocks, so a fine chunk's parent is
the coarse chunk on the same page sharing the most character 8-grams with it.
Mapping rate is reported rather than assumed.

Run:
    python -m retrieval.eval_small2big
    python -m retrieval.eval_small2big --fine retrieval/quotes_t100.sqlite \
        --coarse retrieval/quotes_t1200.sqlite
"""

import argparse
import collections
import os
import sys

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from canonical.gate2 import normalize as g2_normalize, shingles      # noqa: E402
from retrieval.bm25 import BM25                                      # noqa: E402
from retrieval.corpus import tokenize                                # noqa: E402
from retrieval.eval_granularity import (BUDGETS, DEFAULT_DB, SEED,   # noqa: E402
                                        TAUS, load_gold, paired)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARMS = ("coarse-direct", "fine-direct", "small-to-big")
MAX_PREFIX = 400


def load_corpus(path):
    import sqlite3
    con = sqlite3.connect(path)
    rows = con.execute(
        "SELECT doc_name, page_id, text, n_tok FROM chunks "
        "ORDER BY doc_name, page_id, idx").fetchall()
    con.close()
    by_doc = collections.OrderedDict()
    for doc, pid, text, ntok in rows:
        by_doc.setdefault(doc, []).append((pid, text or "", ntok or 0))
    return by_doc


def prepare(items):
    texts = [t for _, t, _ in items]
    return {"pid": [p for p, _, _ in items],
            "tok": [n for _, _, n in items],
            "sh": [shingles(g2_normalize(t)) for t in texts],
            "bm": BM25([tokenize(t.lower()) for t in texts])}


def parent_map(fine, coarse):
    """fine index -> coarse index, by shingle overlap within the same page."""
    by_page = collections.defaultdict(list)
    for j, p in enumerate(coarse["pid"]):
        by_page[p].append(j)
    out, hit = [], 0
    for i, p in enumerate(fine["pid"]):
        best, best_ov = None, 0
        fs = fine["sh"][i]
        if fs:
            for j in by_page.get(p, ()):
                ov = len(fs & coarse["sh"][j])
                if ov > best_ov:
                    best, best_ov = j, ov
        out.append(best)
        hit += best is not None
    return out, hit


def fill(order, toks, budget, limit, parents=None, pack="prefix"):
    """Take units in rank order until the budget is exhausted.

    Two rules, because they answer different questions. Under "prefix" the walk
    stops at the first unit that does not fit, which charges coarse granularities
    a quantisation loss -- a 400-token chunk cannot enter a budget with 300 left,
    and the remainder is forfeited. Under "greedy" that unit is skipped and
    packing continues, which removes the loss but no longer respects rank order.
    An advantage that survives "greedy" is about ranking; one that disappears was
    about how tightly the units tile the budget.
    """
    picked, spent, seen = [], 0, set()
    for r in range(min(len(order), limit)):
        i = int(order[r])
        if parents is not None:
            i = parents[i]
            if i is None or i in seen:
                continue
        elif i in seen:
            continue
        if toks[i] > budget - spent:
            if pack == "prefix":
                break
            continue
        seen.add(i)
        picked.append(i)
        spent += toks[i]
    return picked, spent


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--fine", default=os.path.join(REPO_ROOT, "retrieval",
                                                   "quotes_t100.sqlite"))
    ap.add_argument("--coarse", default=os.path.join(REPO_ROOT, "retrieval",
                                                     "quotes_t600.sqlite"))
    ap.add_argument("--pack", default="prefix", choices=("prefix", "greedy"))
    args = ap.parse_args()

    print(f"packing rule: {args.pack}")
    print(f"fine   : {os.path.basename(args.fine)}")
    print(f"coarse : {os.path.basename(args.coarse)}")
    fine_c, coarse_c = load_corpus(args.fine), load_corpus(args.coarse)
    by_q = load_gold(args.db)
    q_by_doc = collections.defaultdict(list)
    for quid, rec in by_q.items():
        q_by_doc[rec["doc"]].append(quid)

    cov = {a: {b: {} for b in BUDGETS} for a in ARMS}
    used = {a: {b: [] for b in BUDGETS} for a in ARMS}
    spent = {a: {b: [] for b in BUDGETS} for a in ARMS}
    n_fine, n_parented = 0, 0

    for d, (doc, quids) in enumerate(q_by_doc.items(), 1):
        if doc not in fine_c or doc not in coarse_c:
            continue
        F, C = prepare(fine_c[doc]), prepare(coarse_c[doc])
        parents, hit = parent_map(F, C)
        n_fine += len(parents)
        n_parented += hit

        for quid in quids:
            rec = by_q[quid]
            gsh = {e: shingles(g2_normalize(t)) for e, t in rec["gold"].items()}
            gsh = {k: v for k, v in gsh.items() if v}
            if not gsh:
                continue
            q = tokenize(rec["q"].lower())
            of, _ = F["bm"].rank(q)
            oc, _ = C["bm"].rank(q)

            for arm in ARMS:
                for b in BUDGETS:
                    if arm == "coarse-direct":
                        pick, sp = fill(oc, C["tok"], b, MAX_PREFIX, pack=args.pack)
                        src = C
                    elif arm == "fine-direct":
                        pick, sp = fill(of, F["tok"], b, MAX_PREFIX, pack=args.pack)
                        src = F
                    else:
                        pick, sp = fill(of, C["tok"], b, MAX_PREFIX, parents, args.pack)
                        src = C
                    union = set()
                    for i in pick:
                        union |= src["sh"][i]
                    for eid, g in gsh.items():
                        cov[arm][b][(quid, eid)] = len(g & union) / len(g)
                    used[arm][b].append(len(pick))
                    spent[arm][b].append(sp)
        if d % 50 == 0:
            print(f"  {d}/{len(q_by_doc)} documents", flush=True)

    print()
    print(f"fine chunks with a parent: {n_parented}/{n_fine} "
          f"({n_parented/max(n_fine,1):.2%})")

    keys = sorted(set.intersection(*[set(cov[a][b].keys())
                                     for a in ARMS for b in BUDGETS]))
    quids = sorted({q for q, _ in keys})
    print(f"scored on {len(keys)} gold text quotes over {len(quids)} questions")

    for tau in TAUS:
        print()
        print("=" * 76)
        print(f"COVERAGE >= {tau} AT EQUAL TOKEN BUDGET")
        print("=" * 76)
        print(f"{'budget':<10}" + "".join(f"{a:>16}" for a in ARMS)
              + f"{'s2b - coarse':>16}")
        print("-" * 76)
        for b in BUDGETS:
            line = f"{b:<10}"
            vals = {}
            for a in ARMS:
                v = np.array([cov[a][b][k] for k in keys])
                vals[a] = np.mean(v >= tau)
                line += f"{vals[a]:>16.3f}"
            line += f"{vals['small-to-big'] - vals['coarse-direct']:>+16.3f}"
            print(line)

    rng = np.random.default_rng(SEED)
    print()
    print("=" * 76)
    print("PAIRED BOOTSTRAP vs coarse-direct  (B=2000, clustered by question)")
    print("=" * 76)
    for tau in TAUS:
        print(f"  coverage >= {tau}")
        for b in BUDGETS:
            line = f"    {b:<8}"
            for arm in ("fine-direct", "small-to-big"):
                obs, lo, hi = paired(cov["coarse-direct"][b], cov[arm][b],
                                     keys, quids, tau, rng)
                star = "*" if (lo > 0 or hi < 0) else " "
                line += f"  {arm:>13} {obs:>+.3f} [{lo:>+.3f},{hi:>+.3f}]{star}"
            print(line)
    print("* = 95% CI excludes zero")

    print()
    print("mean units retrieved per query")
    print(f"{'budget':<10}" + "".join(f"{a:>16}" for a in ARMS))
    for b in BUDGETS:
        print(f"{b:<10}" + "".join(f"{np.mean(used[a][b]):>16.1f}" for a in ARMS))


if __name__ == "__main__":
    main()
