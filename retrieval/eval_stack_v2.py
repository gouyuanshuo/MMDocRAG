"""E27 re-audit: honest system identities, correct denominator, clustered CIs.

This supersedes `eval_stack.py` for reporting. That script is kept unchanged so
the historical numbers stay reproducible, but it has three defects that this one
fixes, each of which moved a headline number.

    IDENTITY. It labels its baseline "paper: BGE dense". That baseline runs one
    text retriever over self-built text chunks *and* over the VLM-written image
    descriptions, which is not what the paper does: the paper pairs a text
    retriever with a genuinely visual one that reads image pixels. Retrieval
    over `img_description` is called image-description retrieval throughout;
    only the ColQwen arm is visual retrieval.

        The paper names NO version for any retriever -- Table 6 lists model
        families (DPR, ColBERT, BGE, E5, ColPali, ColQwen) and nothing more.
        Earlier revisions of this file asserted "the paper uses
        bge-large-en-v1.5" and "the paper uses ColQwen2 v0.1". Both were
        inferences of ours wearing the paper's authority, and both are removed.
        `--dense-model` selects the text retriever so bge-small and bge-large
        can both be reported; neither can be called the paper's. See
        docs/paper-baseline-audit.md.

    DENOMINATOR. It drops gold text evidence that the 8-gram mapper could not
    place on a self-built chunk (62 items) before forming the gold set, and then
    drops any question left with no gold at all. That silently reports recall
    conditional on successful mapping. Unmapped gold can never be retrieved, so
    the honest default counts it as a miss; both figures are printed here and
    the unconditional one is the headline.

    SAMPLING UNIT. It bootstraps over questions. The 396 test questions come
    from ~55 documents and questions within a document share evidence, style and
    difficulty, so question-level resampling understates the interval. The
    default here resamples documents; question-level CIs are printed alongside
    to show how much the correction matters.

Every reported system is exploratory, not confirmatory: this split has been
observed repeatedly across E1-E27 and used to choose methods.

Run:
    python -m retrieval.eval_stack_v2 --k 10
    python -m retrieval.eval_stack_v2 --k 20 --pool canonical
"""

import argparse
import collections
import hashlib
import json
import os
import platform
import sqlite3
import subprocess
import sys
import time

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retrieval.bm25 import BM25                       # noqa: E402
from retrieval.corpus import normalize, tokenize      # noqa: E402
from retrieval.dense import MODEL as DENSE_MODEL      # noqa: E402
from retrieval.dense import load as load_dense        # noqa: E402
from retrieval import dense_chunks                    # noqa: E402
from expkit.results import ExperimentResult, add_output_args  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO_ROOT, "canonical", "mmdocrag.sqlite")
DEFAULT_QUOTES = os.path.join(REPO_ROOT, "retrieval", "quotes.sqlite")
DEFAULT_COLQWEN = os.path.join(REPO_ROOT, "retrieval", "colqwen_scores.sqlite")
DEFAULT_SPLIT = os.path.join(REPO_ROOT, "manifests", "split_doc_disjoint.json")
OUT_DIR = os.path.join(REPO_ROOT, "manifests")

PAPER_QUOTA = {10: (7, 3), 15: (10, 5), 20: (12, 8)}
# k=15 does not halve, so the "balanced" arm has to be named, not implied.
BALANCED_QUOTA = {10: (5, 5), 15: (8, 7), 20: (10, 10)}
RRF_C = 60
BOOTSTRAP = 4000
SEED = 20260825
COLQWEN_LOCAL = ("vidore/colqwen2-v1.0 (local copy; the paper names no "
                 "version for any retriever)")


def rrf(*rankings):
    score = collections.defaultdict(float)
    for lst in rankings:
        for r, e in enumerate(lst):
            score[e] += 1.0 / (RRF_C + r + 1)
    return sorted(score, key=lambda e: -score[e])


def sha1_file(path, cap=64 << 20):
    h = hashlib.sha1()
    if not os.path.exists(path):
        return "missing"
    with open(path, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b or h.block_size and fh.tell() > cap:
                break
            h.update(b)
    return h.hexdigest()[:16]


def build(db_path, quotes_db, colqwen_db, pool, dense_model=DENSE_MODEL,
          keep_scores=False, top_keep=None):
    """Per-question ranked lists, gold and identity.

    `keep_scores` additionally records the descending first-pass scores of
    each single retriever (top `top_keep or 32` of each branch) plus the
    branch pool sizes. Phase 3 needs them: a cascade router may only look at
    what the retriever it has already paid for produced, so its features have
    to come from this pass rather than from a second one. `top_keep` truncates
    the stored rankings, which is safe only when it is at least the largest
    quota that will ever be sliced off them -- the caller asserts that.

    Both are off by default and change nothing about what is ranked, so the
    E27 numbers this function produces are unaffected.
    """
    con = sqlite3.connect(db_path)
    imgs = con.execute(
        "SELECT evidence_id, doc_name, img_description FROM canonical_evidence "
        "WHERE type <> 'text' ORDER BY doc_name, evidence_id").fetchall()
    qs = con.execute(
        "SELECT question_uid, doc_name, question FROM questions "
        "WHERE split = 'evaluation' ORDER BY question_uid").fetchall()
    gold_rows = con.execute("""
        SELECT g.question_uid, g.evidence_id, e.type
        FROM question_gold_evidence g
        JOIN canonical_evidence e ON e.evidence_id = g.evidence_id
        JOIN questions q          ON q.question_uid = g.question_uid
        WHERE q.split = 'evaluation' AND g.setting = '20'
    """).fetchall()
    con.close()

    P, Q = load_dense("vlm", dense_model)
    if pool == "selfbuilt":
        qc = sqlite3.connect(quotes_db)
        chunks = collections.OrderedDict()
        for cid, doc, text in qc.execute(
                "SELECT chunk_id, doc_name, text FROM chunks "
                "ORDER BY doc_name, page_id, idx"):
            chunks.setdefault(doc, []).append((cid, text or ""))
        gmap = {e: c for e, c in qc.execute(
            "SELECT evidence_id, chunk_id FROM gold_map WHERE chunk_id IS NOT NULL")}
        qc.close()
        Z = dense_chunks.load(quotes_db, dense_model)
        cvec = {str(c): i for i, c in enumerate(Z["cids"])}
        cvecs = Z["vecs"]
    else:
        con2 = sqlite3.connect(db_path)
        chunks = collections.OrderedDict()
        for eid, doc, text in con2.execute(
                "SELECT evidence_id, doc_name, text FROM canonical_evidence "
                "WHERE type = 'text' ORDER BY doc_name, evidence_id"):
            chunks.setdefault(doc, []).append((eid, normalize(text or "")))
        con2.close()
        gmap = {e: e for doc in chunks for e, _ in chunks[doc]}
        cvec = {str(e): i for i, e in enumerate(P["eids"])}
        cvecs = P["vecs"]
    ivec = {str(e): i for i, e in enumerate(P["eids"])}
    ivecs = P["vecs"]
    qvec = {str(u): v for u, v in zip(Q["quids"], Q["vecs"])}

    colq = collections.defaultdict(list)
    if os.path.exists(colqwen_db):
        cq = sqlite3.connect(colqwen_db)
        for quid, eid in cq.execute(
                "SELECT question_uid, evidence_id FROM ranking ORDER BY question_uid, rank"):
            colq[quid].append(eid)
        cq.close()

    img_by_doc = collections.OrderedDict()
    for eid, doc, desc in imgs:
        img_by_doc.setdefault(doc, []).append((eid, normalize(desc or "")))

    # Gold is kept in two forms. `mapped` is what a retriever can possibly
    # return; `total` is what the question actually asks for. Unconditional
    # recall divides by `total`, so a mapping failure is a miss, not an excuse.
    gold = collections.defaultdict(
        lambda: {"text": set(), "visual": set(), "n_text_total": 0,
                 "n_unmapped": 0})
    for quid, eid, etype in gold_rows:
        g = gold[quid]
        if etype == "text":
            g["n_text_total"] += 1
            cid = gmap.get(eid)
            if cid is None:
                g["n_unmapped"] += 1
            else:
                g["text"].add(cid)
        else:
            g["visual"].add(eid)

    idx = {}
    for doc in chunks:
        t_ids = [c for c, _ in chunks[doc]]
        i_ids = [e for e, _ in img_by_doc.get(doc, [])]
        idx[doc] = {
            "text": (BM25([tokenize(t) for _, t in chunks[doc]]), t_ids,
                     np.asarray([cvec[c] for c in t_ids]) if t_ids else None),
            "visual": (BM25([tokenize(t) for _, t in img_by_doc.get(doc, [])]),
                       i_ids,
                       np.asarray([ivec[e] for e in i_ids]) if i_ids else None),
        }

    rows, timing = [], collections.defaultdict(float)
    n_no_gold = 0
    for quid, doc, question in qs:
        if doc not in idx or quid not in gold:
            continue
        g = gold[quid]
        # NB: a question whose gold is entirely unmapped is retained with
        # recall 0, not discarded. Discarding it is what inflated the old number.
        if g["n_text_total"] + len(g["visual"]) == 0:
            n_no_gold += 1
            continue
        qt = tokenize((question or "").lower())
        qv = qvec[quid]
        ranked = {r: {} for r in ("bm25", "dense", "rrf", "colqwen")}
        scores = {}
        for kind, bank in (("text", cvecs), ("visual", ivecs)):
            bm, ids, vrows = idx[doc][kind]
            if not ids:
                for r in ranked.values():
                    r[kind] = []
                if keep_scores:
                    scores[kind] = {"n_pool": 0, "bm25": np.zeros(0),
                                    "dense": np.zeros(0)}
                continue
            t0 = time.perf_counter()
            order, bs = bm.rank(qt)
            ranked["bm25"][kind] = [ids[i] for i in order]
            timing["bm25_" + kind] += time.perf_counter() - t0
            t0 = time.perf_counter()
            sims = bank[vrows] @ qv
            d_order = np.lexsort((np.arange(len(ids)), -sims))
            ranked["dense"][kind] = [ids[i] for i in d_order]
            timing["dense_" + kind] += time.perf_counter() - t0
            if keep_scores:
                cap = top_keep or 32
                scores[kind] = {
                    "n_pool": len(ids),
                    "bm25": np.asarray(bs[order][:cap], dtype=np.float32),
                    "dense": np.asarray(sims[d_order][:cap], dtype=np.float32),
                }
            t0 = time.perf_counter()
            ranked["rrf"][kind] = rrf(ranked["bm25"][kind], ranked["dense"][kind])
            timing["rrf_" + kind] += time.perf_counter() - t0
        # ColQwen scores exist only for image evidence. Audited 2026-08-28 and
        # asserted by `python experiments.py verify E24`: the index covers 100%
        # of every document's image pool (coverage 1.000 on all 2,000 questions,
        # zero length mismatches) and no visual gold is absent from the full
        # ranking, so this arm is not handicapped relative to the description
        # arms. Pool size per DOCUMENT is median 20 / mean 29.76; the median 29
        # quoted earlier was the question-weighted figure, which is a different
        # quantity. The pool covers 6,487 of 13,999 unique evaluation images
        # (46.34%) -- a limit that applies to every arm equally. Present in the
        # ranking is not the same as entering top-k.
        ranked["colqwen"]["visual"] = [e for e in colq.get(quid, [])
                                       if e in set(idx[doc]["visual"][1])]
        ranked["colqwen"]["text"] = ranked["dense"]["text"]

        if top_keep is not None:
            for r in ranked:
                for kind in ranked[r]:
                    ranked[r][kind] = ranked[r][kind][:top_keep]

        rows.append({
            "quid": quid, "doc": doc, "rank": ranked,
            "gold_mapped": g["text"] | g["visual"],
            "n_total": g["n_text_total"] + len(g["visual"]),
            "n_unmapped": g["n_unmapped"],
            "gold_text": set(g["text"]), "gold_visual": set(g["visual"]),
            "n_text_total": g["n_text_total"],
            "has_colqwen": bool(ranked["colqwen"]["visual"]),
            **({"scores": scores} if keep_scores else {}),
        })
    return rows, {"n_no_gold": n_no_gold, "timing": timing,
                  "n_text_units": sum(len(v) for v in chunks.values()),
                  "n_docs_pool": len(chunks), "n_img_units": len(imgs)}


# ---- systems ---------------------------------------------------------------
# (label, text retriever, visual retriever, quota family)
def systems(k):
    pa = PAPER_QUOTA[k]
    ba = BALANCED_QUOTA[k]
    return [
        ("A  dense-only, paper quota %d/%d" % pa, "dense", "dense", pa),
        ("B  dense-only, balanced %d/%d" % ba, "dense", "dense", ba),
        ("C  RRF(bm25,dense), paper quota %d/%d" % pa, "rrf", "rrf", pa),
        ("D  RRF(bm25,dense), balanced %d/%d" % ba, "rrf", "rrf", ba),
        ("E  dense text + ColQwen visual, paper %d/%d" % pa, "dense", "colqwen", pa),
        ("E2 dense text + ColQwen visual, balanced %d/%d" % ba, "dense", "colqwen", ba),
        ("F  BM25-only, paper quota %d/%d" % pa, "bm25", "bm25", pa),
        ("G  RRF text + ColQwen visual, balanced %d/%d" % ba, "rrf", "colqwen", ba),
    ]


def recall(row, tr, vr, quota, conditional=False):
    a, b = quota
    got = set(row["rank"][tr]["text"][:a]) | set(row["rank"][vr]["visual"][:b])
    hit = len(row["gold_mapped"] & got)
    den = len(row["gold_mapped"]) if conditional else row["n_total"]
    return hit / den if den else 0.0


def vec(rows, tr, vr, quota, conditional=False):
    return np.asarray([recall(r, tr, vr, quota, conditional) for r in rows])


def cluster_ci(a, b, docs, rng, n_boot=BOOTSTRAP):
    """Paired bootstrap resampling DOCUMENTS, not questions."""
    d = a - b
    by_doc = collections.defaultdict(list)
    for i, doc in enumerate(docs):
        by_doc[doc].append(i)
    keys = sorted(by_doc)
    sd = np.array([d[by_doc[k]].sum() for k in keys])
    sn = np.array([len(by_doc[k]) for k in keys], dtype=float)
    pick = rng.integers(0, len(keys), size=(n_boot, len(keys)))
    means = sd[pick].sum(axis=1) / sn[pick].sum(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return d.mean(), lo, hi, len(keys)


def question_ci(a, b, rng, n_boot=BOOTSTRAP):
    d = a - b
    idx = rng.integers(0, len(d), size=(n_boot, len(d)))
    lo, hi = np.percentile(d[idx].mean(axis=1), [2.5, 97.5])
    return d.mean(), lo, hi


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--quotes", default=DEFAULT_QUOTES)
    ap.add_argument("--colqwen", default=DEFAULT_COLQWEN)
    ap.add_argument("--split", default=DEFAULT_SPLIT)
    ap.add_argument("--pool", default="selfbuilt", choices=("selfbuilt", "canonical"))
    # The paper names its text retriever only as "BGE", with no version. This
    # project has run bge-small throughout; models/bge-large-en-v1.5 is the
    # closest local stand-in for the scale the paper is likely to have used.
    # Swapping it is a flag rather than an edit so both can be reported.
    ap.add_argument("--dense-model", default=DENSE_MODEL,
                    help="sentence-transformers model or local path for the "
                         "dense text arm (default: %(default)s). Vectors must "
                         "already be built for it by retrieval.dense and "
                         "retrieval.dense_chunks.")
    ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--eval-split", default="test", choices=("test", "all"))
    ap.add_argument("--dump", action="store_true", help="write manifest + per-question csv")
    add_output_args(ap)
    args = ap.parse_args()
    k = args.k

    rows, meta = build(args.db, args.quotes, args.colqwen, args.pool,
                       args.dense_model)
    split = json.load(open(args.split, encoding="utf-8"))["doc_to_split"]
    if args.eval_split == "test":
        rows = [r for r in rows if split.get(r["doc"]) == "test"]

    n_q = len(rows)
    n_docs = len({r["doc"] for r in rows})
    n_gold = sum(r["n_total"] for r in rows)
    n_unmapped = sum(r["n_unmapped"] for r in rows)
    n_colq = sum(r["has_colqwen"] for r in rows)

    print("=" * 86)
    print(f"E27 RE-AUDIT  pool={args.pool}  k={k}  split={args.eval_split}  "
          f"(EXPLORATORY)")
    print("=" * 86)
    print(f"text units {meta['n_text_units']} over {meta['n_docs_pool']} docs; "
          f"image-description units {meta['n_img_units']}")
    print(f"questions {n_q} over {n_docs} documents")
    print(f"gold items {n_gold}; unmapped (counted as miss) {n_unmapped} "
          f"({n_unmapped/max(n_gold,1):.2%}); questions dropped for zero gold "
          f"{meta['n_no_gold']}")
    print(f"questions with ColQwen rankings: {n_colq}/{n_q}")
    print(f"text retriever: BM25 (own) / dense {args.dense_model}")
    print(f"visual retriever: {COLQWEN_LOCAL}")
    print("image-description arms run BM25/dense over VLM text, NOT pixels")

    sysdef = systems(k)
    docs = [r["doc"] for r in rows]
    rng = np.random.default_rng(SEED)
    uncond = {lab: vec(rows, tr, vr, q) for lab, tr, vr, q in sysdef}
    cond = {lab: vec(rows, tr, vr, q, True) for lab, tr, vr, q in sysdef}

    print()
    print(f"{'system':<44}{'uncond':>9}{'cond':>9}")
    print("-" * 62)
    for lab, _, _, _ in sysdef:
        print(f"{lab:<44}{uncond[lab].mean():>9.4f}{cond[lab].mean():>9.4f}")

    # gold-composition breakdown
    grp = {"text-only": [r for r in rows if not r["gold_visual"]],
           "visual-only": [r for r in rows if r["n_text_total"] == 0],
           "both": [r for r in rows if r["gold_visual"] and r["n_text_total"]]}
    print()
    print("by gold composition (unconditional recall)")
    print(f"{'system':<44}" + "".join(f"{g + ' (' + str(len(v)) + ')':>18}"
                                      for g, v in grp.items()))
    for lab, tr, vr, q in sysdef:
        line = f"{lab:<44}"
        for g, v in grp.items():
            line += f"{vec(v, tr, vr, q).mean() if v else float('nan'):>18.4f}"
        print(line)

    comparisons = [
        ("D - A   full stack vs dense-only baseline", "D", "A"),
        ("D - E   full stack vs closest paper-style", "D", "E"),
        ("G - E   best local hybrid vs paper-style", "G", "E"),
        ("B - A   quota alone", "B", "A"),
        ("C - A   fusion alone", "C", "A"),
        ("D - C   quota on top of fusion", "D", "C"),
        ("D - B   fusion on top of quota", "D", "B"),
        ("E - A   ColQwen visual vs image-description", "E", "A"),
        ("E2 - E  quota on paper-style hybrid", "E2", "E"),
    ]
    lut = {lab.split()[0]: lab for lab, _, _, _ in sysdef}
    print()
    print("=" * 96)
    print("PAIRED DELTAS  --  document-cluster bootstrap vs question bootstrap")
    print("=" * 96)
    print(f"{'comparison':<44}{'delta':>9}{'doc-cluster 95% CI':>26}"
          f"{'question 95% CI':>24}")
    print("-" * 96)
    out = []
    for label, x, y in comparisons:
        a, b = uncond[lut[x]], uncond[lut[y]]
        d, lo, hi, nd = cluster_ci(a, b, docs, rng)
        _, qlo, qhi = question_ci(a, b, rng)
        star = "*" if (lo > 0 or hi < 0) else " "
        print(f"{label:<44}{d:>+9.4f}"
              f"{'[' + format(lo, '+.4f') + ',' + format(hi, '+.4f') + ']' + star:>26}"
              f"{'[' + format(qlo, '+.4f') + ',' + format(qhi, '+.4f') + ']':>24}")
        out.append({"comparison": label, "delta": d, "doc_lo": lo, "doc_hi": hi,
                    "q_lo": qlo, "q_hi": qhi, "n_docs": nd, "n_questions": n_q})
    print("-" * 96)
    print(f"* = document-cluster CI excludes zero. {len(comparisons)} comparisons "
          f"at k={k}; with 3 budgets x 2 pools a Bonferroni-style reading would "
          f"require roughly 0.05/{len(comparisons)*6:.0f} per test.")

    print()
    print("retrieval cost (total seconds over all scored questions, CPU)")
    for kk in sorted(meta["timing"]):
        print(f"  {kk:<16}{meta['timing'][kk]:>8.2f}s")
    print("  ColQwen: 4.49 GB VRAM, indexed offline in E24; not re-run here")

    if args.dump:
        os.makedirs(OUT_DIR, exist_ok=True)
        tag = f"e27_{args.pool}_k{k}_{args.eval_split}"
        try:
            commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).decode().strip()
            dirty = bool(subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=REPO_ROOT).decode().strip())
        except Exception:
            commit, dirty = "unknown", "unknown"
        man = {
            "experiment": "E27 re-audit", "status": "EXPLORATORY",
            "pool": args.pool, "k": k, "eval_split": args.eval_split,
            "quota_paper": list(PAPER_QUOTA[k]), "quota_balanced": list(BALANCED_QUOTA[k]),
            "git_commit": commit, "git_dirty": dirty, "seed": SEED,
            "bootstrap": BOOTSTRAP, "rrf_c": RRF_C,
            "text_retrievers": ["BM25 (retrieval/bm25.py, k1=1.5 b=0.75)",
                                args.dense_model],
            "visual_retriever": COLQWEN_LOCAL,
            "image_representation_for_bm25_dense": "VLM img_description text (NOT pixels)",
            "paper_models_not_reproduced": [
                "the paper states no version for any retriever, so no "
                "local model can be claimed to match it; only the model "
                "family (BGE, ColQwen) is known"],
            "n_questions": n_q, "n_documents": n_docs, "n_gold": n_gold,
            "n_unmapped_gold_counted_as_miss": n_unmapped,
            "n_questions_dropped_zero_gold": meta["n_no_gold"],
            "n_text_units": meta["n_text_units"], "n_image_units": meta["n_img_units"],
            # Units matter here and were previously mixed: 6,504 is the
            # distinct-img_path count over the WHOLE 223-document DB, while
            # 13,999 counts images belonging to the 220 EVALUATION documents.
            # Dividing one by the other produced the wrong 46.8%/54% pair.
            "image_pool_note": (
                "evaluation scope: 6,487 unique images in pool out of 13,999 "
                "attributable to the 220 evaluation documents = 46.34% unique-image "
                "coverage; 7,512 never enter either pool. Pool size per document: "
                "median 20, mean 29.76 (question-weighted median is 29 -- a "
                "different quantity). Whole-DB figures, not comparable to the "
                "above: 6,565 image evidence rows / 6,504 distinct img_path over "
                "223 documents."),
            "image_pool_counts": {
                "eval_image_evidence_rows": 6548,
                "eval_unique_images_in_pool": 6487,
                "eval_original_images": 13999,
                "eval_unique_coverage": 0.4634,
                "whole_db_image_rows": 6565,
                "whole_db_distinct_img_path": 6504,
                "whole_db_documents": 223,
                "verified_by": "python experiments.py verify E24"},
            "files": {f: sha1_file(os.path.join(REPO_ROOT, f)) for f in (
                "canonical/mmdocrag.sqlite", "retrieval/quotes.sqlite",
                "retrieval/colqwen_scores.sqlite",
                "manifests/split_doc_disjoint.json")},
            "python": platform.python_version(), "platform": platform.platform(),
            "systems": {lab: {"text": tr, "visual": vr, "quota": list(q),
                              "recall_uncond": float(uncond[lab].mean()),
                              "recall_cond": float(cond[lab].mean())}
                        for lab, tr, vr, q in sysdef},
            "comparisons": out,
            "command": " ".join(sys.argv),
        }
        with open(os.path.join(OUT_DIR, tag + ".json"), "w", encoding="utf-8") as fh:
            json.dump(man, fh, indent=2, ensure_ascii=False)
        with open(os.path.join(OUT_DIR, tag + "_perquestion.csv"),
                  "w", encoding="utf-8") as fh:
            heads = [lab.split()[0] for lab, _, _, _ in sysdef]
            fh.write("question_uid,doc_name,split,n_gold_total,n_unmapped,"
                     "n_gold_visual," + ",".join(heads) + "\n")
            for i, r in enumerate(rows):
                fh.write(f"{r['quid']},{r['doc']},{split.get(r['doc'],'?')},"
                         f"{r['n_total']},{r['n_unmapped']},{len(r['gold_visual'])},"
                         + ",".join(f"{uncond[lut[h]][i]:.4f}" for h in heads) + "\n")
        print(f"\nwrote {os.path.join(OUT_DIR, tag + '.json')} and _perquestion.csv")

    # ---- structured output ------------------------------------------------
    with ExperimentResult("E27", args.metrics_out,
                          title="静态检索配置的改进（单切分，exploratory）") as res:
        res.config(analysis="single_split", grouping="document", oof=False,
                   unmapped_gold="counted as miss",
                   pool=args.pool, k=k, seed=SEED, bootstrap=BOOTSTRAP,
                   rrf_c=RRF_C, eval_split=args.eval_split, sample_unit="document",
                   quota_paper=f"{PAPER_QUOTA[k][0]}/{PAPER_QUOTA[k][1]}",
                   quota_balanced=f"{BALANCED_QUOTA[k][0]}/{BALANCED_QUOTA[k][1]}",
                   n_questions=n_q, n_documents=n_docs, n_gold=n_gold,
                   n_unmapped_gold_counted_as_miss=n_unmapped,
                   dense_model=args.dense_model, visual_retriever=COLQWEN_LOCAL,
                   status="EXPLORATORY")
        res.data_file(args.db, args.quotes, args.colqwen, args.split)
        for lab, tr, vr, q in sysdef:
            res.metric(f"recall_uncond[{lab.split()[0]}]", float(uncond[lab].mean()),
                       system=lab, text_retriever=tr, visual_retriever=vr,
                       quota=f"{q[0]}/{q[1]}", denominator="unconditional")
            res.metric(f"recall_cond[{lab.split()[0]}]", float(cond[lab].mean()),
                       system=lab, denominator="conditional-on-mapped (diagnostic only)")
        for o in out:
            res.metric("delta: " + o["comparison"], o["delta"],
                       ci=(o["doc_lo"], o["doc_hi"]),
                       question_ci_low=o["q_lo"], question_ci_high=o["q_hi"],
                       comparison=o["comparison"], n_documents=o["n_docs"])
        res.per_question([
            {"question_uid": r["quid"], "doc_name": r["doc"],
             "split": split.get(r["doc"], "?"), "n_gold_total": r["n_total"],
             "n_gold_unmapped": r["n_unmapped"], "n_gold_visual": len(r["gold_visual"]),
             **{f"recall[{lab.split()[0]}]": float(uncond[lab][i])
                for lab, _, _, _ in sysdef}}
            for i, r in enumerate(rows)])
        res.note("EXPLORATORY: this split was observed repeatedly across E1-E27 "
                 "and used to choose methods. Generalisation is supported only "
                 "by E28's document-grouped OOF protocol.")
        res.note(f"{len(comparisons)} comparisons at k={k}; across 3 budgets x 2 "
                 f"pools a Bonferroni reading needs ~0.05/{len(comparisons) * 6:.0f}.")
    if args.metrics_out:
        print()
        print(f"wrote metrics to {args.metrics_out}")


if __name__ == "__main__":
    main()
