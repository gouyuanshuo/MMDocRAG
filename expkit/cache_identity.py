"""Content identities for derived research caches (not API response caches)."""
import hashlib
import json
from pathlib import Path

from expkit.paths import REPO_ROOT

_HASHES = {}


def file_hash(path):
    p = Path(path).resolve()
    st = p.stat()
    key = (str(p), st.st_size, st.st_mtime_ns)
    if key not in _HASHES:
        h = hashlib.sha256()
        with p.open("rb") as fh:
            for b in iter(lambda: fh.read(1 << 20), b""):
                h.update(b)
        _HASHES[key] = h.hexdigest()
    return _HASHES[key]


def identity(config, files):
    payload = dict(config=config, files={str(Path(p).resolve()): file_hash(p)
                                        for p in files})
    payload["fingerprint"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return payload


def retrieval_inputs(db, quotes, colqwen, dense_model, pool):
    root = Path(REPO_ROOT)
    tag = Path(str(dense_model)).name
    names = ["retrieval/eval_stack_v2.py", "retrieval/dense.py",
             "retrieval/dense_chunks.py", "retrieval/bm25.py",
             "retrieval/quote_corpus.py", "router/actions.py"]
    files = [db, colqwen, *(root / n for n in names)]
    files += [root / "retrieval/embeddings" / f"{tag}_{suffix}.npz"
              for suffix in ("vlm_passages", "query_questions")]
    if pool == "selfbuilt":
        files += [quotes, root / "retrieval/embeddings" / f"{tag}_quotes_chunks.npz"]
    return files
