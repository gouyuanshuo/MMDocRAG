"""BGE vectors for the self-built text chunks.

`retrieval/dense.py` encodes `canonical_evidence` -- the question-conditioned
candidate union. Every conclusion drawn on that pool carries an optimism caveat,
and the fusion result the stacked comparison rests on is exactly the kind that
pool composition can distort. So the dense arm is rebuilt here over the 92,752
chunks `quote_corpus.py` produced from the PDFs, which is the pool a deployed
system would actually index.

Image quotes are not re-encoded: they are unchanged from `dense.py`'s cache and
are loaded from there, so the two halves stay on the same model and prefix
convention.

Run:
    python -m retrieval.dense_chunks
    python -m retrieval.dense_chunks --quotes retrieval/quotes_t600.sqlite
"""

import argparse
import os
import shutil
import sqlite3
import sys

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retrieval.dense import CACHE_DIR, MODEL, encode      # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_QUOTES = os.path.join(REPO_ROOT, "retrieval", "quotes.sqlite")


def cache_path(quotes_db, model_name=MODEL):
    tag = model_name.split("/")[-1]
    stem = os.path.splitext(os.path.basename(quotes_db))[0]
    return os.path.join(CACHE_DIR, f"{tag}_{stem}_chunks.npz")


def _shard_dir(out):
    return out[:-4] + ".shards"


def build(quotes_db, model_name=MODEL, batch=256, shard=8192):
    out = cache_path(quotes_db, model_name)
    if os.path.exists(out):
        print(f"cached: {out}")
        return out
    con = sqlite3.connect(quotes_db)
    rows = con.execute(
        "SELECT chunk_id, doc_name, text FROM chunks "
        "ORDER BY doc_name, page_id, idx").fetchall()
    con.close()

    bodies = [(t or "") for _, _, t in rows]
    empty = sum(1 for b in bodies if not b.strip())
    print(f"encoding {len(bodies)} chunks from {os.path.basename(quotes_db)}; "
          f"{empty} are empty")

    # Shard so a kill costs one shard, not the run. This encoder held ~50
    # minutes of GPU work in memory and wrote only at the end; an external kill
    # at 65% therefore recovered nothing, twice. The row order is fixed by the
    # SELECT above, so shard i always covers the same rows and a resumed run
    # reassembles them in the same order.
    sd = _shard_dir(out)
    os.makedirs(sd, exist_ok=True)
    parts = []
    n_reused = 0
    for start in range(0, len(bodies), shard):
        stop = min(start + shard, len(bodies))
        p = os.path.join(sd, f"{start:08d}-{stop:08d}.npy")
        if os.path.exists(p):
            try:
                arr = np.load(p)
                if arr.shape[0] == stop - start:
                    parts.append(arr)
                    n_reused += arr.shape[0]
                    continue
                print(f"  shard {os.path.basename(p)} has {arr.shape[0]} rows, "
                      f"expected {stop - start}; re-encoding")
            except Exception as exc:
                print(f"  shard {os.path.basename(p)} unreadable "
                      f"({type(exc).__name__}); re-encoding")
        v = encode(bodies[start:stop], batch=batch, model_name=model_name)
        # np.save appends ".npy" to any path that lacks it, so saving to
        # "<name>.npy.tmp" silently produces "<name>.npy.tmp.npy" and the
        # rename below then fails on a file that was never written. Handing it
        # an open handle is the one form that writes exactly where told.
        tmp = p + ".tmp"
        with open(tmp, "wb") as fh:
            np.save(fh, v)
        os.replace(tmp, p)          # a torn shard must never look complete
        parts.append(v)
        print(f"  shard {start}-{stop} written ({stop}/{len(bodies)})",
              flush=True)
    if n_reused:
        # relpath raises across Windows drives, and the cache can legitimately
        # sit on another one. A pretty path is not worth losing the run over.
        try:
            where = os.path.relpath(sd, REPO_ROOT)
        except ValueError:
            where = sd
        print(f"resumed: {n_reused} chunk vectors reused from {where}")
    vecs = np.concatenate(parts, axis=0)
    assert vecs.shape[0] == len(bodies), (vecs.shape, len(bodies))
    # As in dense.py: an empty passage still gets a vector, and an arbitrary one.
    # Zeroing makes its cosine score exactly 0 rather than accidentally relevant.
    for i, b in enumerate(bodies):
        if not b.strip():
            vecs[i] = 0.0

    os.makedirs(CACHE_DIR, exist_ok=True)
    np.savez_compressed(out,
                        cids=np.asarray([r[0] for r in rows]),
                        docs=np.asarray([r[1] for r in rows]),
                        vecs=vecs)
    print(f"wrote {out}")
    shutil.rmtree(_shard_dir(out), ignore_errors=True)
    return out


def load(quotes_db, model_name=MODEL):
    return np.load(cache_path(quotes_db, model_name), allow_pickle=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--quotes", default=DEFAULT_QUOTES)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--shard", type=int, default=8192,
                    help="checkpoint every N chunks (0 disables). A kill then "
                         "costs at most one shard; the next run reuses the rest.")
    args = ap.parse_args()
    build(args.quotes, args.model, args.batch, args.shard or 10 ** 9)


if __name__ == "__main__":
    main()
