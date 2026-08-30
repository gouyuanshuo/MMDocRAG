"""Materialise a Hub model into models/<name>/ as a plain directory.

Why not just let SentenceTransformer download it
------------------------------------------------
Two reasons, both learned the hard way on this box (see docs/lab-notebook.html
E24). `huggingface_hub` builds its cache out of symlinks, which Windows refuses
to create without developer mode (WinError 1314); the cache then resolves as
empty even though the blobs are present. And its xet transfer backend has hung
on this network. Materialising into a flat folder and pointing the loader at a
path sidesteps both.

The third reason is about the record rather than the plumbing: a baseline that
claims to reproduce a published system has to name the model *and* pin what it
actually loaded. This writes `fetch.json` next to the weights with the resolved
revision SHA and a hash of every file, so a later run can prove it loaded the
same bytes rather than whatever `main` points at today.

    python -m retrieval.fetch_model BAAI/bge-large-en-v1.5
    python -m retrieval.fetch_model BAAI/bge-large-en-v1.5 --check
"""

import argparse
import hashlib
import json
import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# safetensors only: the .bin is the same weights in a format nothing here reads,
# and pulling both doubles a 1.3 GB download on a disk that recently ran out.
ALLOW = ["*.json", "*.txt", "*.md", "*.safetensors", "1_Pooling/*",
         "tokenizer*", "vocab*", "special_tokens_map*", "modules.json"]
DENY = ["*.bin", "*.h5", "*.ot", "*.msgpack", "onnx/*", "openvino/*"]


def sha256(path, buf=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(buf), b""):
            h.update(chunk)
    return h.hexdigest()


def inventory(dest):
    out = {}
    for root, _dirs, files in os.walk(dest):
        for f in files:
            if f == "fetch.json":
                continue
            p = os.path.join(root, f)
            rel = os.path.relpath(p, dest).replace("\\", "/")
            out[rel] = {"bytes": os.path.getsize(p), "sha256": sha256(p)}
    return out


def fetch(repo_id, dest, revision=None):
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    from huggingface_hub import snapshot_download

    t0 = time.time()
    print(f"downloading {repo_id} -> {os.path.relpath(dest, REPO_ROOT)}")
    path = snapshot_download(repo_id=repo_id, revision=revision,
                             local_dir=dest, allow_patterns=ALLOW,
                             ignore_patterns=DENY)
    took = time.time() - t0

    from huggingface_hub import HfApi
    try:
        sha = HfApi().model_info(repo_id, revision=revision).sha
    except Exception as exc:                    # offline later; not fatal now
        sha = None
        print(f"  (could not resolve revision sha: {type(exc).__name__})")

    files = inventory(dest)
    meta = {
        "repo_id": repo_id,
        "revision_requested": revision or "main",
        "revision_sha": sha,
        "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "local_dir": os.path.relpath(dest, REPO_ROOT).replace("\\", "/"),
        "n_files": len(files),
        "bytes": sum(v["bytes"] for v in files.values()),
        "seconds": round(took, 1),
        "files": files,
        "allow_patterns": ALLOW,
        "ignore_patterns": DENY,
        "note": "Weights only, safetensors format. The .bin duplicate is not "
                "fetched. Verify with: python -m retrieval.fetch_model "
                f"{repo_id} --check",
    }
    with open(os.path.join(dest, "fetch.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)
    print(f"  {len(files)} files, {meta['bytes'] / 1e6:.1f} MB, {took:.0f}s")
    print(f"  revision {sha}")
    return meta


def check(dest):
    """Re-hash the directory against fetch.json. Exit 1 on any drift."""
    mpath = os.path.join(dest, "fetch.json")
    if not os.path.isfile(mpath):
        print(f"FAIL no fetch.json in {dest}")
        return 1
    with open(mpath, encoding="utf-8") as fh:
        meta = json.load(fh)
    now = inventory(dest)
    bad = []
    for rel, info in meta["files"].items():
        got = now.get(rel)
        if got is None:
            bad.append(f"MISSING {rel}")
        elif got["sha256"] != info["sha256"]:
            bad.append(f"CHANGED {rel}")
    extra = sorted(set(now) - set(meta["files"]))
    print(f"{meta['repo_id']}  revision {meta.get('revision_sha')}")
    print(f"  {len(meta['files']) - len(bad)}/{len(meta['files'])} files "
          f"byte-identical to the fetch record")
    for b in bad:
        print(f"  {b}")
    if extra:
        print(f"  {len(extra)} file(s) not in the record: {extra[:5]}")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("repo_id")
    ap.add_argument("--revision", default=None,
                    help="pin a commit sha instead of tracking main")
    ap.add_argument("--dest", default=None)
    ap.add_argument("--check", action="store_true",
                    help="re-hash an existing local copy; do not download")
    a = ap.parse_args()

    dest = a.dest or os.path.join(REPO_ROOT, "models", a.repo_id.split("/")[-1])
    if a.check:
        raise SystemExit(check(dest))
    if os.path.isfile(os.path.join(dest, "fetch.json")):
        print(f"already present at {os.path.relpath(dest, REPO_ROOT)}; verifying")
        raise SystemExit(check(dest))
    os.makedirs(dest, exist_ok=True)
    fetch(a.repo_id, dest, a.revision)
    raise SystemExit(check(dest))


if __name__ == "__main__":
    main()
