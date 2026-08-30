"""Registry for derived artifacts: embeddings, indexes, corpora.

Why a registry rather than a cache directory
--------------------------------------------
An embedding file is not a cache. A cache may be deleted and regenerated at any
time without consequence; an embedding is an experimental input, and every
number computed from it is only reproducible if you can say which model, which
revision, which corpus and which evidence ordering produced it. Two BGE files of
identical shape can disagree because one was normalized and the other was not,
and nothing in the `.npy` header will tell you which.

So each artifact gets a JSON sidecar recording model, revision, local path,
dtype, shape, normalize, corpus name, corpus hash, evidence-id ordering hash,
producing commit and creation time. `load_checked()` refuses to hand back an
artifact whose sidecar disagrees with what the caller asked for. Silently
loading a stale vector is the failure mode this exists to prevent: it produces
numbers that look fine and are wrong.

The DAG below is what lets `--offline` and `full-local` decide honestly whether
a step can be skipped, reused, or must be rebuilt.
"""

import hashlib
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from expkit import paths                 # noqa: E402

REGISTRY_NAME = "registry.json"

# name -> (dependencies, builder command, human label, expensive?)
# The topology the suites reason about. `expensive` means GPU time or a long
# CPU pass; those never run unless --include-expensive is passed.
DAG = {
    "corpora/canonical-db": (
        [], ["-m", "canonical.build"], "canonical evidence DB", False),
    "corpora/page-corpus": (
        ["corpora/canonical-db"], ["-m", "retrieval.corpus"],
        "page-level text corpus (needs OCR)", True),
    "corpora/quotes-selfbuilt": (
        ["corpora/canonical-db"], ["-m", "retrieval.quote_corpus"],
        "self-built chunk corpus (~92.7k chunks)", True),
    "embeddings/bge-small-vlm": (
        ["corpora/canonical-db"], ["-m", "retrieval.dense", "--image-repr", "vlm"],
        "BGE-small vectors over canonical evidence (VLM descriptions)", True),
    "embeddings/bge-small-query": (
        ["corpora/canonical-db"], ["-m", "retrieval.dense", "--image-repr", "vlm"],
        "BGE-small question vectors", True),
    "embeddings/bge-small-ocr": (
        ["corpora/canonical-db"], ["-m", "retrieval.ocr_quotes"],
        "BGE-small vectors over crop-OCR text", True),
    "embeddings/bge-small-chunks": (
        ["corpora/quotes-selfbuilt"], ["-m", "retrieval.dense_chunks"],
        "BGE-small vectors over self-built chunks", True),
    "indexes/colqwen-rankings": (
        ["corpora/canonical-db"],
        [".venv-colpali/Scripts/python.exe", "-m", "retrieval.colqwen_index"],
        "ColQwen2 late-interaction rankings (GPU, ~62 min)", True),
    # The paper-baseline arm. bge-large is the closest local stand-in for the
    # paper's unnamed "BGE"; the full-pool index is the only one whose pool
    # size (63.6 img/doc) matches the paper's 63. See
    # docs/paper-baseline-audit.md for what these do and do not establish.
    "embeddings/bge-large-vlm": (
        ["corpora/canonical-db"],
        ["-m", "retrieval.dense", "--model", "models/bge-large-en-v1.5",
         "--image-repr", "vlm"],
        "BGE-large vectors over canonical evidence (VLM descriptions)", True),
    "embeddings/bge-large-query": (
        ["corpora/canonical-db"],
        ["-m", "retrieval.dense", "--model", "models/bge-large-en-v1.5",
         "--image-repr", "vlm"],
        "BGE-large question vectors", True),
    "embeddings/bge-large-chunks": (
        ["corpora/quotes-selfbuilt"],
        ["-m", "retrieval.dense_chunks", "--model", "models/bge-large-en-v1.5"],
        "BGE-large vectors over self-built chunks", True),
    "indexes/colqwen-fullpool": (
        ["corpora/canonical-db"],
        [".venv-colpali/Scripts/python.exe", "-m", "retrieval.colqwen_index",
         "--image-source", "fulldisk",
         "--out", "retrieval/colqwen_scores_fullpool.sqlite"],
        "ColQwen2 rankings over the FULL image pool (GPU, ~130 min)", True),
}


def _git_commit():
    try:
        r = subprocess.run(("git", "rev-parse", "HEAD"), cwd=paths.REPO_ROOT,
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def digest_path(path, cap_bytes=256 << 20):
    """sha256 of a file, or of a directory's (name, size, mtime) listing.

    Directories are fingerprinted structurally rather than by content: the
    embedding directory is hundreds of MB and re-hashing it on every run would
    dominate the runtime of an experiment that takes five seconds.
    """
    if not os.path.exists(path):
        return None
    if os.path.isdir(path):
        h = hashlib.sha256()
        for root, dirs, files in os.walk(path):
            dirs.sort()
            for f in sorted(files):
                fp = os.path.join(root, f)
                try:
                    st = os.stat(fp)
                except OSError:
                    continue
                h.update(os.path.relpath(fp, path).replace("\\", "/").encode())
                h.update(f"{st.st_size}:{int(st.st_mtime)}".encode())
        return "dir:" + h.hexdigest()[:32]
    h = hashlib.sha256()
    read = 0
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
            read += len(block)
            if read >= cap_bytes:
                h.update(b"TRUNCATED")
                break
    return h.hexdigest()[:32]


def size_of(path):
    if not os.path.exists(path):
        return None
    if os.path.isfile(path):
        return os.path.getsize(path)
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


# Fields every embedding/index artifact should carry. Anything not determinable
# from the bytes on disk is recorded as UNKNOWN rather than inferred: a guessed
# model revision is worse than an admitted gap, because it reads as a fact.
UNKNOWN = "unknown"

EMBEDDING_FIELDS = ("model_name", "model_revision", "model_local_path", "dtype",
                    "shape", "normalized", "input_corpus", "input_corpus_hash",
                    "id_order_hash", "produced_by_cmd", "software_versions")

# What the producing scripts declare. Names come from the scripts themselves;
# revision is genuinely unrecorded for the legacy files, hence unknown.
KNOWN_PRODUCERS = {
    "embeddings/bge-small-vlm": {
        "model_name": "BAAI/bge-small-en-v1.5",
        "model_local_path": "models/bge-small-en-v1.5",
        "input_corpus": "corpora/canonical-db :: canonical_evidence",
        "produced_by_cmd": "python -m retrieval.dense --image-repr vlm"},
    "embeddings/bge-small-query": {
        "model_name": "BAAI/bge-small-en-v1.5",
        "model_local_path": "models/bge-small-en-v1.5",
        "input_corpus": "corpora/canonical-db :: questions (split=evaluation)",
        "produced_by_cmd": "python -m retrieval.dense --image-repr vlm"},
    "embeddings/bge-small-chunks": {
        "model_name": "BAAI/bge-small-en-v1.5",
        "model_local_path": "models/bge-small-en-v1.5",
        "input_corpus": "corpora/quotes-selfbuilt :: chunks",
        "produced_by_cmd": "python -m retrieval.dense_chunks"},
    "embeddings/bge-small-ocr": {
        "model_name": "BAAI/bge-small-en-v1.5",
        "model_local_path": "models/bge-small-en-v1.5",
        "input_corpus": "retrieval/quote_ocr.sqlite :: crop OCR text",
        "produced_by_cmd": "python -m retrieval.ocr_quotes"},
    # bge-large is the one model in this project whose exact bytes are pinned:
    # retrieval/fetch_model.py wrote models/bge-large-en-v1.5/fetch.json with
    # the resolved revision and a SHA-256 per file. Every other entry here names
    # a model without being able to prove which weights were loaded.
    "embeddings/bge-large-vlm": {
        "model_name": "BAAI/bge-large-en-v1.5",
        "model_revision": "d4aa6901d3a41ba39fb536a557fa166f842b0e09",
        "model_local_path": "models/bge-large-en-v1.5",
        "input_corpus": "corpora/canonical-db :: canonical_evidence",
        "produced_by_cmd": "python -m retrieval.dense "
                           "--model models/bge-large-en-v1.5 --image-repr vlm"},
    "embeddings/bge-large-query": {
        "model_name": "BAAI/bge-large-en-v1.5",
        "model_revision": "d4aa6901d3a41ba39fb536a557fa166f842b0e09",
        "model_local_path": "models/bge-large-en-v1.5",
        "input_corpus": "corpora/canonical-db :: questions (split=evaluation)",
        "produced_by_cmd": "python -m retrieval.dense "
                           "--model models/bge-large-en-v1.5 --image-repr vlm"},
    "embeddings/bge-large-chunks": {
        "model_name": "BAAI/bge-large-en-v1.5",
        "model_revision": "d4aa6901d3a41ba39fb536a557fa166f842b0e09",
        "model_local_path": "models/bge-large-en-v1.5",
        "input_corpus": "corpora/quotes-selfbuilt :: chunks",
        "produced_by_cmd": "python -m retrieval.dense_chunks "
                           "--model models/bge-large-en-v1.5"},
    "indexes/colqwen-fullpool": {
        "model_name": "vidore/colqwen2-v1.0",
        "model_local_path": "models/colqwen2-v1.0",
        "input_corpus": "every image file on disk for the 220 evaluation "
                        "documents (13,999 images, 63.6/doc), NOT the "
                        "candidate pool",
        "produced_by_cmd": ".venv-colpali/Scripts/python.exe -m "
                           "retrieval.colqwen_index --image-source fulldisk "
                           "--out retrieval/colqwen_scores_fullpool.sqlite"},
    "indexes/colqwen-rankings": {
        "model_name": "vidore/colqwen2-v1.0",
        "model_local_path": "models/colqwen2-v1.0",
        "dtype": "bfloat16 (model compute; stored scores are float64 in sqlite)",
        "normalized": "n/a -- late-interaction MaxSim scores, not vectors",
        "input_corpus": "corpora/canonical-db :: canonical_evidence (type<>'text')",
        "produced_by_cmd":
            ".venv-colpali/Scripts/python.exe -m retrieval.colqwen_index"},
}


def probe_npz(path):
    """Read back what the file itself can tell us. No guessing."""
    out = {}
    try:
        import numpy as np
        with np.load(path, allow_pickle=True) as z:
            keys = list(z.files)
            out["npz_keys"] = keys
            vec_key = next((k for k in ("vecs", "vectors", "emb") if k in keys), None)
            if vec_key:
                v = z[vec_key]
                out["dtype"] = str(v.dtype)
                out["shape"] = list(v.shape)
                if v.ndim == 2 and v.shape[0]:
                    n = min(512, v.shape[0])
                    norms = np.linalg.norm(v[:n].astype("float64"), axis=1)
                    finite = norms[np.isfinite(norms) & (norms > 0)]
                    if finite.size:
                        out["normalized"] = bool(
                            np.allclose(finite, 1.0, atol=2e-3))
                        out["row_norm_median"] = float(np.median(finite))
                    else:
                        out["normalized"] = UNKNOWN
                    out["n_zero_rows"] = int((norms == 0).sum())
            id_key = next((k for k in ("eids", "cids", "quids", "ids") if k in keys),
                          None)
            if id_key:
                ids = [str(x) for x in z[id_key].tolist()]
                out["id_field"] = id_key
                out["n_ids"] = len(ids)
                # Order matters: a retriever indexes rows positionally, so a
                # reordered file with the same contents is a different artifact.
                out["id_order_hash"] = hashlib.sha256(
                    "\n".join(ids).encode()).hexdigest()[:16]
    except Exception as exc:
        out["probe_error"] = f"{type(exc).__name__}: {exc}"
    return out


def probe_sqlite_ranking(path):
    out = {}
    try:
        import sqlite3
        con = sqlite3.connect(path)
        out["n_rows"] = con.execute("SELECT COUNT(*) FROM ranking").fetchone()[0]
        out["n_questions"] = con.execute(
            "SELECT COUNT(DISTINCT question_uid) FROM ranking").fetchone()[0]
        out["n_evidence"] = con.execute(
            "SELECT COUNT(DISTINCT evidence_id) FROM ranking").fetchone()[0]
        ids = [r[0] for r in con.execute(
            "SELECT question_uid FROM ranking GROUP BY question_uid "
            "ORDER BY question_uid")]
        out["id_field"] = "question_uid"
        out["n_ids"] = len(ids)
        out["id_order_hash"] = hashlib.sha256(
            "\n".join(map(str, ids)).encode()).hexdigest()[:16]
        con.close()
    except Exception as exc:
        out["probe_error"] = f"{type(exc).__name__}: {exc}"
    return out


def software_versions():
    import importlib.metadata as md
    out = {"python": sys.version.split()[0]}
    for pkg in ("numpy", "torch", "transformers", "sentence-transformers",
                "colpali-engine"):
        try:
            out[pkg] = md.version(pkg)
        except Exception:
            out[pkg] = None
    return out


def describe(name, path):
    """Full metadata block for one artifact: probed + declared + unknown."""
    meta = {f: UNKNOWN for f in EMBEDDING_FIELDS}
    meta.update({k: v for k, v in KNOWN_PRODUCERS.get(name, {}).items()})
    if path and os.path.isfile(path):
        if path.endswith(".npz"):
            meta.update(probe_npz(path))
        elif path.endswith(".sqlite") and name.startswith("indexes/"):
            meta.update(probe_sqlite_ranking(path))
    dep = DAG.get(name, ([], None, "", False))[0]
    if dep:
        meta["input_corpus_artifact"] = dep[0]
        # The corpus hash AS OF NOW is a fact and worth recording; the hash at
        # production time is not recoverable for a legacy artifact, so
        # `input_corpus_hash` stays unknown rather than borrowing this value.
        dep_path = paths.LEGACY_ARTIFACTS.get(dep[0])
        if dep_path and os.path.exists(dep_path):
            meta["input_corpus_hash_at_registration"] = digest_path(dep_path)
            meta["input_corpus_hash_note"] = (
                "hash of the dependency as it stands at registration time, NOT "
                "necessarily the corpus this artifact was built from")
    meta["software_versions"] = software_versions()
    missing = sorted(f for f in EMBEDDING_FIELDS if meta.get(f) == UNKNOWN)
    meta["unknown_fields"] = missing
    meta["metadata_incomplete"] = bool(missing)
    if missing:
        meta["metadata_note"] = (
            "fields listed in unknown_fields were not recorded when this "
            "artifact was produced and cannot be recovered from the file; "
            "they are left as 'unknown' rather than inferred. Rebuild via the "
            "DAG to populate them.")
    return meta


class Registry:
    def __init__(self, root=None):
        self.root = paths.derived_root(root)
        os.makedirs(self.root, exist_ok=True)
        self.path = os.path.join(self.root, REGISTRY_NAME)
        self.entries = {}
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as fh:
                self.entries = json.load(fh).get("artifacts", {})

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "artifacts": self.entries}, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def register(self, name, path, *, kind="", legacy=False, **meta):
        """Record an artifact. `legacy=True` means it predates this registry and
        stays where it is rather than being copied into artifacts/derived."""
        entry = {
            "name": name,
            "kind": kind or name.split("/")[0],
            "path": paths.rel(path),
            "abs_path": os.path.abspath(path),
            "exists": os.path.exists(path),
            "legacy": legacy,
            "bytes": size_of(path),
            "content_hash": digest_path(path),
            "git_commit": _git_commit(),
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        entry.update(meta)
        self.entries[name] = entry
        self.save()
        return entry

    def get(self, name):
        return self.entries.get(name)

    def status(self, name):
        """Present / stale / missing / unregistered, for the runner's report."""
        e = self.entries.get(name)
        target = e["abs_path"] if e else None
        if target is None:
            for legacy_name, legacy_path in paths.LEGACY_ARTIFACTS.items():
                if legacy_name == name:
                    return ("unregistered" if os.path.exists(legacy_path)
                            else "missing", legacy_path)
            return "missing", None
        if not os.path.exists(target):
            return "missing", target
        if e.get("content_hash") and digest_path(target) != e["content_hash"]:
            return "stale", target
        return "present", target

    def load_checked(self, name, **expect):
        """Return the artifact path, or raise if its sidecar contradicts `expect`.

        A mismatch is always an error, never a warning followed by a load: the
        whole point is that an experiment must not run on inputs it did not ask
        for.
        """
        state, target = self.status(name)
        if state == "missing":
            raise FileNotFoundError(
                f"artifact '{name}' is missing at {target}. "
                f"Build it with: python experiments.py run-suite full-local "
                f"--include-expensive --force-rebuild {name}")
        if state == "stale":
            raise ValueError(
                f"artifact '{name}' changed on disk since it was registered "
                f"(content hash differs). Re-register or rebuild it; refusing "
                f"to load possibly-stale inputs.")
        e = self.entries.get(name, {})
        bad = {k: (e.get(k), v) for k, v in expect.items()
               if v is not None and e.get(k) != v}
        if bad:
            detail = "; ".join(f"{k}: registered={a!r} requested={b!r}"
                               for k, (a, b) in bad.items())
            raise ValueError(f"artifact '{name}' metadata mismatch -- {detail}")
        return target

    def adopt_legacy(self):
        """Register the pre-existing artifacts in place, without copying."""
        out = []
        for name, path in paths.LEGACY_ARTIFACTS.items():
            if not os.path.exists(path):
                continue
            if name in self.entries and self.entries[name].get("exists"):
                out.append((name, "already registered"))
                continue
            self.register(name, path, legacy=True,
                          note="pre-existing artifact adopted in place; not copied",
                          **describe(name, path))
            out.append((name, "adopted"))
        return out


def plan(names, registry=None, force_rebuild=()):
    """Resolve a dependency closure into reuse / rebuild decisions.

    Returns a list of dicts the runner writes verbatim into the run manifest, so
    every skip is explainable after the fact rather than inferred.
    """
    reg = registry or Registry()
    force = set(force_rebuild or ())
    seen, order = set(), []

    def visit(n):
        if n in seen:
            return
        seen.add(n)
        for dep in DAG.get(n, ([], None, "", False))[0]:
            visit(dep)
        order.append(n)

    for n in names:
        visit(n)

    out = []
    for n in order:
        deps, cmd, label, expensive = DAG.get(n, ([], None, n, False))
        state, target = reg.status(n)
        if n in force:
            decision, why = "rebuild", "explicitly requested via --force-rebuild"
        elif state in ("present", "unregistered"):
            decision, why = "reuse", f"artifact {state} at {paths.rel(target or '')}"
        elif state == "stale":
            decision, why = "rebuild", "content hash differs from registration"
        else:
            decision, why = "rebuild", "artifact missing"
        out.append({"artifact": n, "label": label, "state": state,
                    "path": paths.rel(target) if target else None,
                    "decision": decision, "reason": why,
                    "expensive": expensive, "dependencies": deps,
                    "build_cmd": cmd})
    return out
