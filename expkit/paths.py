"""Where everything lives, and the rules about what may live outside the project.

The artifact root defaults to `<repo>/artifacts` and can be moved with
`--artifact-root` or `MMDOCRAG_ARTIFACT_ROOT`. Nothing else in this package is
allowed to invent a path.

Offline discipline
------------------
`enforce_offline()` sets the HuggingFace/transformers offline switches AND
redirects their caches into the project. It is not a performance tweak: a run
that silently pulls a model from `%USERPROFILE%\\.cache` produces numbers whose
inputs are not in the project, so the run cannot be reproduced from the project
alone. Under `--offline` a missing model must be a loud failure, not a download.
"""

import json
import os
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Artifacts that predate this package. They are registered as `legacy` rather
# than copied: they are large, they are already reproducible from their own
# scripts, and duplicating them would double disk use for no gain.
LEGACY_ARTIFACTS = {
    "embeddings/bge-small-vlm": os.path.join(
        REPO_ROOT, "retrieval", "embeddings",
        "bge-small-en-v1.5_vlm_passages.npz"),
    "embeddings/bge-small-query": os.path.join(
        REPO_ROOT, "retrieval", "embeddings",
        "bge-small-en-v1.5_query_questions.npz"),
    "embeddings/bge-small-chunks": os.path.join(
        REPO_ROOT, "retrieval", "embeddings",
        "bge-small-en-v1.5_quotes_chunks.npz"),
    "embeddings/bge-small-ocr": os.path.join(
        REPO_ROOT, "retrieval", "embeddings",
        "bge-small-en-v1.5_ocr_passages.npz"),
    "corpora/page-corpus": os.path.join(REPO_ROOT, "retrieval", "pages.sqlite"),
    "indexes/colqwen-rankings": os.path.join(REPO_ROOT, "retrieval", "colqwen_scores.sqlite"),
    "corpora/canonical-db": os.path.join(REPO_ROOT, "canonical", "mmdocrag.sqlite"),
    "corpora/quotes-selfbuilt": os.path.join(REPO_ROOT, "retrieval", "quotes.sqlite"),
    "embeddings/bge-large-vlm": os.path.join(
        REPO_ROOT, "retrieval", "embeddings",
        "bge-large-en-v1.5_vlm_passages.npz"),
    "embeddings/bge-large-query": os.path.join(
        REPO_ROOT, "retrieval", "embeddings",
        "bge-large-en-v1.5_query_questions.npz"),
    "embeddings/bge-large-chunks": os.path.join(
        REPO_ROOT, "retrieval", "embeddings",
        "bge-large-en-v1.5_quotes_chunks.npz"),
    "indexes/colqwen-fullpool": os.path.join(
        REPO_ROOT, "retrieval", "colqwen_scores_fullpool.sqlite"),
}


def artifact_root(override=None):
    if override:
        return os.path.abspath(override)
    env = os.environ.get("MMDOCRAG_ARTIFACT_ROOT")
    if env:
        return os.path.abspath(env)
    return os.path.join(REPO_ROOT, "artifacts")


def runs_root(root=None):
    return os.path.join(artifact_root(root), "runs")


def derived_root(root=None):
    return os.path.join(artifact_root(root), "derived")


def api_root(root=None):
    return os.path.join(artifact_root(root), "api")


def model_cache(root=None):
    return os.path.join(artifact_root(root), "model_cache")


def run_dir(run_id, root=None):
    return os.path.join(runs_root(root), run_id)


def experiment_dir(run_id, exp_id, root=None):
    return os.path.join(run_dir(run_id, root), "experiments", exp_id)


def new_run_id(suite="run"):
    """Timestamped and collision-proof: a re-run must never land in an old dir."""
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    base = f"{stamp}_{suite}"
    root = runs_root()
    if not os.path.exists(os.path.join(root, base)):
        return base
    n = 2
    while os.path.exists(os.path.join(root, f"{base}_{n}")):
        n += 1
    return f"{base}_{n}"


def ensure_dirs(root=None):
    for p in (runs_root(root), derived_root(root), api_root(root), model_cache(root),
              os.path.join(derived_root(root), "embeddings"),
              os.path.join(derived_root(root), "indexes"),
              os.path.join(derived_root(root), "corpora")):
        os.makedirs(p, exist_ok=True)


def write_latest(run_id, root=None):
    """A pointer file, not a symlink: Windows needs elevation for symlinks."""
    path = os.path.join(runs_root(root), "latest.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"run_id": run_id,
                   "path": os.path.relpath(run_dir(run_id, root), REPO_ROOT),
                   "updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                  fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


def read_latest(root=None):
    path = os.path.join(runs_root(root), "latest.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def resolve_run(run_id=None, root=None):
    """`latest` and `None` both mean the most recent run."""
    if run_id in (None, "", "latest"):
        latest = read_latest(root)
        if not latest:
            raise SystemExit("no runs yet; run `python experiments.py run-suite replay --offline`")
        return latest["run_id"]
    return run_id


def enforce_offline(root=None):
    """Pin every model/dataset cache inside the project and forbid network pulls.

    Returns the environment overlay so the runner can pass it to children and
    record it in the manifest -- a run that cannot say where its model came from
    has not recorded its inputs.
    """
    cache = model_cache(root)
    os.makedirs(cache, exist_ok=True)
    overlay = {
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
        "HF_HOME": cache,
        "HUGGINGFACE_HUB_CACHE": os.path.join(cache, "hub"),
        "TRANSFORMERS_CACHE": os.path.join(cache, "transformers"),
        "SENTENCE_TRANSFORMERS_HOME": os.path.join(cache, "sentence-transformers"),
        "TOKENIZERS_PARALLELISM": "false",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }
    os.environ.update(overlay)
    return overlay


def online_env():
    """The overlay used when network access is deliberately allowed."""
    return {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}


def rel(path):
    """Repo-relative when inside the repo, absolute otherwise. For manifests."""
    ap = os.path.abspath(path)
    if ap.startswith(REPO_ROOT):
        return os.path.relpath(ap, REPO_ROOT).replace("\\", "/")
    return ap
