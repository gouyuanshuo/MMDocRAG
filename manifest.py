"""Experiment manifests: record exactly what produced a set of numbers.

Every experiment in this project writes a manifest next to its results so a
run can be traced back to the code, data and settings behind it. Reproduction
is the whole point of Phase 0, and an averaged score with no provenance is not
reproducible even when the code is.

Usage from an experiment script:

    import manifest
    manifest.write(
        "eval_all/gemini-2.0-flash_multimodal_20",
        data_files=["dataset/evaluation_20.jsonl", eval_path, judge_path],
        extra={"model": "gemini-2.0-flash", "setting": "20", "mode": "multimodal",
               "seed": 42, "prompt": "prompt_bank/multimodal_infer.txt"},
        results={"final_f1": 60.0},
    )

Hashing is cached on (path, size, mtime) in manifests/.checksum_cache.json, so
re-stamping the same multi-hundred-MB dataset file is cheap after the first run.
"""

import hashlib
import json
import os
import platform
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
MANIFEST_DIR = os.path.join(REPO_ROOT, "manifests")
CACHE_PATH = os.path.join(MANIFEST_DIR, ".checksum_cache.json")

# Packages whose versions are worth pinning into every manifest. Anything not
# installed is simply reported as absent rather than failing the run.
TRACKED_PACKAGES = (
    "nltk", "rouge_score", "tqdm", "numpy", "openai", "anthropic",
    "google-genai", "torch", "transformers", "sentence-transformers",
    "pymupdf", "ms-swift",
)


def _run_git(*args):
    try:
        out = subprocess.run(("git",) + args, cwd=REPO_ROOT, capture_output=True,
                             text=True, timeout=30)
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def git_state():
    """Commit the code is at, plus whether the tree has uncommitted edits."""
    status = _run_git("status", "--porcelain")
    return {
        "commit": _run_git("rev-parse", "HEAD"),
        "branch": _run_git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(status) if status is not None else None,
        "dirty_files": sorted(
            line[3:] for line in status.splitlines()) if status else [],
    }


def env_state():
    import importlib.metadata as md
    versions = {}
    for pkg in TRACKED_PACKAGES:
        try:
            versions[pkg] = md.version(pkg)
        except Exception:
            versions[pkg] = None
    state = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": versions,
    }
    try:
        import torch
        state["cuda"] = {
            "available": torch.cuda.is_available(),
            "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "torch_cuda": torch.version.cuda,
        }
    except Exception:
        state["cuda"] = None
    return state


def _load_cache():
    try:
        with open(CACHE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_cache(cache):
    os.makedirs(MANIFEST_DIR, exist_ok=True)
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cache, fh)
    os.replace(tmp, CACHE_PATH)


def file_digest(path, cache=None):
    """sha256 of a file, cached on (size, mtime) so large files hash once."""
    own_cache = cache is None
    cache = _load_cache() if own_cache else cache
    try:
        st = os.stat(path)
    except OSError:
        return {"path": path, "sha256": None, "bytes": None, "missing": True}

    key = os.path.abspath(path)
    stamp = [st.st_size, int(st.st_mtime)]
    hit = cache.get(key)
    if hit and hit.get("stamp") == stamp:
        digest = hit["sha256"]
    else:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
        digest = h.hexdigest()
        cache[key] = {"stamp": stamp, "sha256": digest}
        if own_cache:
            _save_cache(cache)
    return {"path": os.path.relpath(path, REPO_ROOT) if key.startswith(REPO_ROOT) else path,
            "sha256": digest, "bytes": st.st_size}


def write(name, *, data_files=(), extra=None, results=None, outdir=MANIFEST_DIR):
    """Write a manifest and return its path.

    `name` may contain slashes; it becomes a subdirectory. A UTC timestamp is
    appended so repeated runs accumulate rather than overwrite.
    """
    cache = _load_cache()
    payload = {
        "name": name,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git": git_state(),
        "env": env_state(),
        "data": [file_digest(p, cache) for p in data_files],
        "config": dict(extra or {}),
        "results": dict(results or {}),
        "argv": sys.argv,
    }
    _save_cache(cache)

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = os.path.join(outdir, f"{name}_{stamp}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return path


if __name__ == "__main__":
    # Smoke test: stamp the current environment against the dataset files.
    import argparse

    ap = argparse.ArgumentParser(description="Write a manifest for the current state")
    ap.add_argument("--name", default="env/snapshot")
    ap.add_argument("--data", nargs="*", default=[])
    args = ap.parse_args()

    out = write(args.name, data_files=args.data)
    print("wrote", out)
    with open(out, encoding="utf-8") as fh:
        payload = json.load(fh)
    print("commit :", payload["git"]["commit"], "dirty:", payload["git"]["dirty"])
    print("python :", payload["env"]["python"])
    print("cuda   :", payload["env"]["cuda"])
    for entry in payload["data"]:
        print(f"  {entry.get('sha256', '')[:16]}  {entry['path']}")
