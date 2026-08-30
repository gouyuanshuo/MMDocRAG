"""Phase 3 features, grouped by WHEN they become available and what they cost.

E23 is the reason the groups are kept apart rather than concatenated: on 1,211
training rows a 384-dimensional question embedding turned a real R^2 of +0.11
into -0.07 simply by drowning eleven informative dimensions. Any Phase 3
negative result would be uninterpretable unless the low-dimensional groups were
also fitted on their own.

The other reason is honesty about cost. A router that decides *which* retriever
to run may only look at things that exist before any retriever has run. A
cascade router that decides whether to *escalate* may additionally look at what
its own cheap first pass produced -- and only at that pass, never at the one it
is deciding whether to pay for. The groups encode that distinction so a policy
cannot quietly consume a feature it has not paid for.

    shape      pool sizes of the document being searched. Free: known from the
               index, no retrieval and no model call.
    qtext      surface statistics of the question string. Free.
    emb        384-d BGE question embedding. Charged as a fixed per-query model
               call, not as a pass over the pool: its cost does not scale with
               the document and it is shared with the dense retriever when that
               retriever is chosen. Reported as a separate group so its effect
               is visible.
    firstpass  score-distribution statistics of the cheap first pass, read
               from whichever retriever that pass actually ran. Available ONLY
               to a cascade policy, and never from the retriever the policy is
               deciding whether to pay for.

`free` is shape + qtext + emb; `all` adds firstpass.
"""

import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retrieval.dense import MODEL as DENSE_MODEL    # noqa: E402
from retrieval.dense import load as load_dense      # noqa: E402

GROUPS = ("shape", "qtext", "emb", "firstpass")
PRESETS = {"free": ("shape", "qtext", "emb"),
           "cheap": ("shape", "qtext"),
           "all": ("shape", "qtext", "emb", "firstpass"),
           "shape": ("shape",), "qtext": ("qtext",), "emb": ("emb",),
           "firstpass": ("firstpass",),
           "shape+firstpass": ("shape", "firstpass"),
           "cheap+firstpass": ("shape", "qtext", "firstpass")}

VISUAL_WORDS = ("figure", "fig", "table", "chart", "graph", "plot", "image",
                "diagram", "picture", "photo", "map", "screenshot")
_WORD = re.compile(r"[a-z0-9]+")


def _stats(scores, cap):
    """Score-distribution summary of one branch of one first pass."""
    s = np.asarray(scores, dtype=np.float64)
    if s.size == 0:
        return [0.0] * 7
    head = s[:cap]
    nz = float((s > 0).sum())
    top1 = float(head[0])
    mean = float(head.mean())
    return [top1, mean, float(head.std()), top1 - float(head[-1]),
            top1 / (mean + 1e-9), nz, nz / max(len(s), 1)]


def featurize(rows, questions, k, quota, groups=("shape", "qtext", "emb"),
              dense_model=DENSE_MODEL, firstpass=("bm25", "bm25")):
    """(X, names). `groups` selects which blocks are concatenated.

    `firstpass` names the retriever the cascade actually ran on (text, visual).
    Only that retriever's scores are read, so the feature vector can never
    contain evidence from a pass the policy has not paid for.
    """
    groups = tuple(groups)
    for g in groups:
        if g not in GROUPS:
            raise ValueError(f"unknown feature group {g!r}")
    qa, qb = quota

    qvec = None
    if "emb" in groups:
        _, Q = load_dense("vlm", dense_model)
        qvec = {str(u): v for u, v in zip(Q["quids"], Q["vecs"])}

    blocks, names = [], []
    if "shape" in groups:
        M = []
        for r in rows:
            sc = r.get("scores", {})
            nt = float(sc.get("text", {}).get("n_pool", 0))
            nv = float(sc.get("visual", {}).get("n_pool", 0))
            M.append([nt, nv, np.log1p(nt), np.log1p(nv),
                      nt / (nt + nv + 1e-9),
                      float(nt <= qa), float(nv <= qb),
                      float(nt + nv <= k)])
        blocks.append(np.asarray(M))
        names += ["n_text_pool", "n_visual_pool", "log_n_text_pool",
                  "log_n_visual_pool", "text_pool_share",
                  "text_pool_saturated", "visual_pool_saturated",
                  "pool_saturated"]

    if "qtext" in groups:
        M = []
        for r in rows:
            q = questions.get(r["quid"], "") or ""
            toks = _WORD.findall(q.lower())
            M.append([float(len(toks)), float(len(q)),
                      float(sum(c.isdigit() for c in q)),
                      float(any(w in toks for w in VISUAL_WORDS)),
                      float(sum(t in VISUAL_WORDS for t in toks)),
                      float("%" in q), float(q.count("?")),
                      float(sum(w[:1].isupper() for w in q.split()))])
        blocks.append(np.asarray(M))
        names += ["q_n_tokens", "q_n_chars", "q_n_digits", "q_has_visual_word",
                  "q_n_visual_words", "q_has_percent", "q_n_qmarks",
                  "q_n_capitalised"]

    if "emb" in groups:
        blocks.append(np.asarray([qvec[r["quid"]] for r in rows]))
        names += [f"emb{i}" for i in range(blocks[-1].shape[1])]

    if "firstpass" in groups:
        M = []
        for r in rows:
            sc = r.get("scores")
            if sc is None:
                raise KeyError("firstpass features need an action cache built "
                               "with keep_scores=True")
            # Only the first pass that was actually run. The other
            # retriever's scores sit in the same record, and reading them
            # would mean the cascade had already paid for the pass it is
            # deciding whether to run.
            M.append(_stats(sc.get("text", {}).get(firstpass[0], []), qa)
                     + _stats(sc.get("visual", {}).get(firstpass[1], []), qb))
        blocks.append(np.asarray(M))
        for br, rt in zip(("text", "visual"), firstpass):
            names += [f"{rt}_{br}_{s}" for s in
                      ("top1", "mean", "std", "gap", "peakiness", "n_nonzero",
                       "frac_nonzero")]

    X = np.hstack(blocks) if blocks else np.zeros((len(rows), 0))
    return np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0), names
