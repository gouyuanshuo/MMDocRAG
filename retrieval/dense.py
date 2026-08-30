"""Dense retrieval arm: BGE embeddings over the quote pool.

Second retriever for two purposes. It is the comparison BM25 needs -- a lexical
retriever and a semantic one fail on different queries, which is the premise of
RQ2 -- and it is the text-side baseline the paper reports (BGE, Table 6), so
having it here keeps this project on the same axis.

BGE asymmetry: queries get an instruction prefix, passages do not. Skipping the
prefix costs real recall, and it is the single most common way BGE is
mis-deployed, so it is applied here explicitly rather than left to a default.

Embeddings are cached to npz keyed by (model, image representation), because the
image quotes' text surrogate is a variable of the experiment -- VLM description
or crop OCR -- and each needs its own vectors.

Run:
    python -m retrieval.dense --image-repr vlm
    python -m retrieval.dense --image-repr ocr
"""

import argparse
import os
import sqlite3
import sys

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retrieval.corpus import normalize            # noqa: E402
from retrieval.eval_quote_recall import surrogate  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO_ROOT, "canonical", "mmdocrag.sqlite")
DEFAULT_OCR = os.path.join(REPO_ROOT, "retrieval", "quote_ocr.sqlite")
CACHE_DIR = os.path.join(REPO_ROOT, "retrieval", "embeddings")

MODEL = "BAAI/bge-small-en-v1.5"
# BGE's own retrieval prefix. Applied to queries only; passages are encoded bare.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def cache_path(model, repr_mode, what):
    tag = model.split("/")[-1]
    return os.path.join(CACHE_DIR, f"{tag}_{repr_mode}_{what}.npz")


_MODELS = {}


def _model(model_name):
    """One instance per process. Rebuilding it per call is not free.

    This used to construct a SentenceTransformer on every `encode`, which was
    invisible while the callers encoded everything in one shot. Once
    dense_chunks started encoding in shards to survive a kill, the same corpus
    began paying for 23 constructions -- each one re-reading the weights and
    re-staging them on the device -- and throughput fell from ~45 chunks/s to
    ~14. Same model, same batches, three times the wall clock.
    """
    m = _MODELS.get(model_name)
    if m is None:
        from sentence_transformers import SentenceTransformer
        m = _MODELS[model_name] = SentenceTransformer(model_name)
    return m


def encode(texts, batch=128, is_query=False, model_name=MODEL):
    model = _model(model_name)
    if is_query:
        texts = [QUERY_PREFIX + t for t in texts]
    return model.encode(texts, batch_size=batch, normalize_embeddings=True,
                        show_progress_bar=True).astype(np.float32)


def build(db_path, ocr_path, repr_mode, model_name=MODEL):
    """Encode the quote pool and the evaluation questions, caching both."""
    con = sqlite3.connect(db_path)
    ev = con.execute(
        "SELECT evidence_id, doc_name, type, text, img_description "
        "FROM canonical_evidence ORDER BY doc_name, evidence_id").fetchall()
    qs = con.execute(
        "SELECT question_uid, doc_name, question FROM questions "
        "ORDER BY question_uid").fetchall()
    con.close()

    ocr = {}
    if os.path.exists(ocr_path):
        c = sqlite3.connect(ocr_path)
        ocr = {e: t or "" for e, t in
               c.execute("SELECT evidence_id, text FROM quote_ocr")}
        c.close()

    os.makedirs(CACHE_DIR, exist_ok=True)

    p_path = cache_path(model_name, repr_mode, "passages")
    if not os.path.exists(p_path):
        eids = [e[0] for e in ev]
        bodies = [normalize(surrogate(t, txt, desc, ocr.get(e, ""), repr_mode))
                  for e, _, t, txt, desc in ev]
        empty = sum(1 for b in bodies if not b.strip())
        print(f"encoding {len(bodies)} quotes ({repr_mode}); "
              f"{empty} have no text under this representation")
        # An empty string still yields a vector, and an arbitrary one -- it would
        # match queries for no reason. Zero it so its cosine score is exactly 0.
        vecs = encode(bodies, model_name=model_name)
        for i, b in enumerate(bodies):
            if not b.strip():
                vecs[i] = 0.0
        np.savez_compressed(p_path, eids=np.asarray(eids),
                            docs=np.asarray([e[1] for e in ev]),
                            types=np.asarray([e[2] for e in ev]), vecs=vecs)
        print(f"wrote {p_path}")
    else:
        print(f"passages cached: {p_path}")

    q_path = cache_path(model_name, "query", "questions")
    if not os.path.exists(q_path):
        print(f"encoding {len(qs)} questions")
        vecs = encode([q[2] or "" for q in qs], is_query=True, model_name=model_name)
        np.savez_compressed(q_path, quids=np.asarray([q[0] for q in qs]),
                            docs=np.asarray([q[1] for q in qs]), vecs=vecs)
        print(f"wrote {q_path}")
    else:
        print(f"questions cached: {q_path}")


def load(repr_mode, model_name=MODEL):
    """(passage bundle, question bundle) as dicts of arrays."""
    p = np.load(cache_path(model_name, repr_mode, "passages"), allow_pickle=True)
    q = np.load(cache_path(model_name, "query", "questions"), allow_pickle=True)
    return p, q


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--ocr", default=DEFAULT_OCR)
    ap.add_argument("--image-repr", dest="repr", default="vlm",
                    choices=("vlm", "ocr", "both", "none"))
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()
    build(args.db, args.ocr, args.repr, args.model)


if __name__ == "__main__":
    main()
