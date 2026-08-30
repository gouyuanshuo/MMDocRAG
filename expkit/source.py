"""Bind a run to the source code that actually executed it.

`git_state()` records the commit and the *names* of dirty files. On a tree that
has been dirty for weeks -- which is this project's normal condition -- that is
not enough to reconstruct what ran: the commit is months old and every file that
matters is in the dirty list. Two runs a day apart can share a commit hash, a
dirty-file list, and nothing else.

So each run gets a `source_manifest.json` carrying:

    per-file SHA-256 of experiments.py, all of expkit/, and every module the
    run's commands actually imported by name
    a full snapshot of the experiment registry as executed
    hashes of the config and key data files
    when the tree is dirty, the working-tree diff as a patch file
    a `source_bundle.zip` holding the bytes of every file in the manifest

Why the bundle exists (2026-08-29)
----------------------------------
The manifest used to claim `git checkout <commit> && git apply source.patch`
reconstructs the run. It does not. `git diff HEAD` only sees *tracked* files,
and in this repository 18 of the 25 fingerprinted files -- `experiments.py`,
all of `expkit/`, `retrieval/nested_cv.py`, `retrieval/ablation.py` and the
rest -- have never been committed. Measured against run 20260828T080756Z_replay,
commit + patch restores 7 of 25 files and leaves 18 missing. The manifest could
therefore *detect* that the code differed while being unable to *produce* the
code that ran, which is exactly half of what a source record is for.

`source_bundle.zip` closes that gap: it stores the bytes of every manifest file
under its repo-relative path, tracked and untracked alike, so restoration never
depends on what happened to be committed. The patch is kept because it still
records the tracked-file deltas in reviewable form -- but it is no longer
advertised as sufficient on its own.

The bundle carries source only. Datasets, models, vectors, indexes, API logs,
responses and anything credential-shaped are excluded by construction: the
member list is the manifest's `source_files`, which is built from `.py`, `.txt`
and `.json` under the source directories plus the modules a command invoked.

The 16-hex `fingerprint` is a digest over the file hashes plus the registry
snapshot. Two runs with the same fingerprint ran the same code against the same
registry; two runs that differ, differ somewhere recorded here. That is the
property `git dirty: true` cannot give you.

Secrets never enter the patch: it is filtered through the same redaction the API
log uses, and any file whose path looks like a credential store is excluded
rather than diffed.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from expkit import paths                          # noqa: E402
from expkit.apilog import SECRET_VALUE            # noqa: E402
from expkit.results import atomic_json, atomic_write   # noqa: E402

# Files that may hold credentials are never diffed or hashed into the manifest.
SECRET_PATH = re.compile(r"(\.env|credential|secret|\.key$|\.pem$|token)", re.I)

# Always fingerprinted, whether or not a command touched them: they define what
# a run means.
ALWAYS = ["experiments.py", "manifest.py", "data_utils.py", "eval_all.py",
          "inference_api.py", "inference_wrapper.py"]
ALWAYS_DIRS = ["expkit", "prompt_bank"]

# Data files whose content decides every number. Hashed via manifest.py's cache
# so a 50 MB sqlite is not re-read on every run.
KEY_DATA = ["canonical/mmdocrag.sqlite", "retrieval/quotes.sqlite",
            "retrieval/colqwen_scores.sqlite", "retrieval/pages.sqlite",
            "manifests/split_doc_disjoint.json", "manifests/e29_subset.json"]


def sha256_file(path):
    if not os.path.isfile(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _git(*args, binary=False):
    try:
        r = subprocess.run(("git",) + args, cwd=paths.REPO_ROOT,
                           capture_output=True, timeout=60)
        if r.returncode != 0:
            return None
        return r.stdout if binary else r.stdout.decode("utf-8", "replace")
    except Exception:
        return None


def modules_from_argv(argv_lists):
    """Map `-m pkg.mod` and bare script arguments onto files on disk.

    Only what the run actually invoked -- fingerprinting every .py in the repo
    would make the manifest change whenever an unrelated file is edited, which
    defeats the purpose of a fingerprint.
    """
    files = set()
    for argv in argv_lists or ():
        for i, a in enumerate(argv):
            if a == "-m" and i + 1 < len(argv):
                rel = argv[i + 1].replace(".", os.sep) + ".py"
                if os.path.isfile(os.path.join(paths.REPO_ROOT, rel)):
                    files.add(rel.replace("\\", "/"))
                pkg_init = os.path.join(argv[i + 1].split(".")[0], "__init__.py")
                if os.path.isfile(os.path.join(paths.REPO_ROOT, pkg_init)):
                    files.add(pkg_init.replace("\\", "/"))
            elif a.endswith(".py") and os.path.isfile(
                    os.path.join(paths.REPO_ROOT, a)):
                files.add(a.replace("\\", "/"))
    return sorted(files)


def _collect(paths_list):
    out = {}
    for rel in paths_list:
        full = os.path.join(paths.REPO_ROOT, rel)
        if SECRET_PATH.search(rel):
            out[rel] = {"sha256": None, "skipped": "path looks credential-bearing"}
            continue
        if os.path.isfile(full):
            out[rel] = {"sha256": sha256_file(full),
                        "bytes": os.path.getsize(full)}
    return out


def _walk_dirs(dirs):
    rels = []
    for d in dirs:
        root = os.path.join(paths.REPO_ROOT, d)
        if not os.path.isdir(root):
            continue
        for base, subs, files in os.walk(root):
            subs[:] = [x for x in sorted(subs) if x != "__pycache__"]
            for f in sorted(files):
                if f.endswith((".py", ".txt", ".json")):
                    rels.append(os.path.relpath(
                        os.path.join(base, f), paths.REPO_ROOT).replace("\\", "/"))
    return rels


BUNDLE_NAME = "source_bundle.zip"

# The bundle is a *source* snapshot. Nothing here may reach outside that: no
# dataset row, no model weight, no vector, no index, no API log, no response,
# no credential. Membership comes from the manifest, and the manifest is built
# from ALWAYS / ALWAYS_DIRS / invoked modules -- none of which can name those.
# This guard is the second line of defence, checked per member at write time.
BUNDLE_FORBIDDEN = re.compile(
    r"^(artifacts|dataset|response|models|images|tmp|\.venv|"
    r"[^/]*\.venv[^/]*)/|"
    r"\.(npz|npy|sqlite|db|pt|bin|safetensors|onnx|zip|pdf|png|jpg|jpeg)$", re.I)


def write_bundle(rdir, src):
    """Zip every manifest file at its repo-relative path.

    Members are stored with a fixed timestamp-free ordering (sorted by path) so
    two runs of identical source produce byte-comparable bundles; the hash that
    matters is per member, recorded in the manifest, not the zip container's.
    """
    path = os.path.join(rdir, BUNDLE_NAME)
    tmp = path + ".tmp"
    members, skipped = {}, []
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in sorted(src):
            if src[rel].get("sha256") is None:
                skipped.append({"path": rel, "why": "credential-shaped path"})
                continue
            if BUNDLE_FORBIDDEN.search(rel) or SECRET_PATH.search(rel):
                skipped.append({"path": rel, "why": "not source"})
                continue
            full = os.path.join(paths.REPO_ROOT, rel)
            if not os.path.isfile(full):
                skipped.append({"path": rel, "why": "file vanished before bundling"})
                continue
            with open(full, "rb") as fh:
                data = fh.read()
            info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)
            members[rel] = {"sha256": hashlib.sha256(data).hexdigest(),
                            "bytes": len(data)}
    os.replace(tmp, path)
    return path, members, skipped


def bundle_selfcheck(bundle_path, members):
    """Re-read every member out of the zip and re-hash it.

    Writing a file and recording a hash of what you meant to write is not proof
    the bytes landed. This reads them back from the container.
    """
    rows = []
    with zipfile.ZipFile(bundle_path) as z:
        names = set(z.namelist())
        for rel in sorted(members):
            if rel not in names:
                rows.append({"path": rel, "ok": False, "why": "absent from zip"})
                continue
            got = hashlib.sha256(z.read(rel)).hexdigest()
            rows.append({"path": rel, "ok": got == members[rel]["sha256"],
                         "sha256": got})
        extra = sorted(names - set(members))
    n_ok = sum(1 for r in rows if r["ok"])
    return {"status": "pass" if (n_ok == len(rows) and not extra) else "FAIL",
            "n_members": len(rows), "n_ok": n_ok,
            "n_bad": len(rows) - n_ok,
            "unexpected_members": extra,
            "failures": [r for r in rows if not r["ok"]]}


# --------------------------------------------------------------------------
# Reconstruction
# --------------------------------------------------------------------------
def _patch_targets(patch_path):
    """Repo-relative paths a patch will touch, from its `diff --git` headers."""
    if not patch_path or not os.path.exists(patch_path):
        return set()
    out = set()
    with open(patch_path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("diff --git a/"):
                rest = line[len("diff --git a/"):].rstrip()
                i = rest.find(" b/")
                if i > 0:
                    out.add(rest[:i])
    return out


def _wanted_in_tree(rel, needed):
    """Should this member of `git archive` be written into a restored tree?

    A reconstruction tree exists to prove that the manifest's source files come
    back byte-identical. It does not need the repository's data. Extracting the
    commit wholesale put every tracked dataset in every tree -- 963 MB of
    jsonl per tree, against 137 KB of source actually under test -- and 38
    trees filled 36 GB of disk before anyone measured one.

    So the same policy that keeps data out of the bundle keeps it out of the
    tree. `needed` overrides the filter: anything the patch will apply to, or
    the manifest will re-hash, is extracted no matter what it looks like, so
    trimming can never turn `git apply` or verify_tree into a false failure.
    """
    rel = rel.replace("\\", "/")
    if rel in needed:
        return True
    return not (BUNDLE_FORBIDDEN.search(rel) or SECRET_PATH.search(rel))


def restore(manifest, dest, bundle_path=None, patch_path=None, repo=None,
            apply_patch=True):
    """Rebuild a run's source tree at `dest` from commit + patch + bundle.

    Read-only with respect to the repository: `git archive` streams a commit
    without touching the working tree, which matters here because this project's
    tree is permanently dirty and a `git checkout` would destroy uncommitted
    work. Returns a step log so a caller can report which layer supplied what.
    """
    repo = repo or paths.REPO_ROOT
    os.makedirs(dest, exist_ok=True)
    steps = []
    commit = (manifest.get("git") or {}).get("commit")
    patch_path = patch_path or _abs(manifest.get("git", {}).get("patch"))
    needed = set(manifest.get("source_files") or ()) | _patch_targets(patch_path)

    if commit:
        zpath = os.path.join(dest, "_head.zip")
        r = subprocess.run(["git", "archive", "--format=zip", commit,
                            "-o", zpath], cwd=repo, capture_output=True)
        if r.returncode == 0:
            with zipfile.ZipFile(zpath) as z:
                infos = z.infolist()
                take = [i for i in infos
                        if not i.is_dir() and _wanted_in_tree(i.filename, needed)]
                kept = {i.filename for i in take}
                skip_bytes = sum(i.file_size for i in infos
                                 if not i.is_dir() and i.filename not in kept)
                for i in take:
                    z.extract(i, dest)
            os.remove(zpath)
            steps.append({"step": "git archive <commit>", "ok": True,
                          "files": len(take), "files_in_commit": len(infos),
                          "skipped_not_source": len(infos) - len(take),
                          "skipped_bytes": skip_bytes,
                          "skipped_why": "data, models and binaries are not "
                                         "under test here; see _wanted_in_tree",
                          "commit": commit})
        else:
            steps.append({"step": "git archive <commit>", "ok": False,
                          "error": r.stderr.decode("utf-8", "replace")[:400]})
    else:
        steps.append({"step": "git archive <commit>", "ok": False,
                      "error": "no commit recorded"})

    if apply_patch and patch_path and os.path.exists(patch_path):
        # `git apply` walks up from cwd looking for a repository. When `dest` is
        # inside this repo -- which it is by default, because the restored trees
        # live under artifacts/test-runs -- git finds THIS repo, treats the patch
        # paths as repo-relative, decides the changes are already present, and
        # prints "Skipped patch 'eval_all.py'." while exiting 0. A silent no-op
        # that reports success is worse than a failure, so both halves are fixed:
        # GIT_CEILING_DIRECTORIES stops the upward walk at dest's parent, and the
        # output is inspected because the exit code alone did not catch this.
        env = dict(os.environ)
        env["GIT_CEILING_DIRECTORIES"] = os.path.dirname(os.path.abspath(dest))
        env.pop("GIT_DIR", None)
        env.pop("GIT_WORK_TREE", None)
        r = subprocess.run(["git", "apply", "--verbose", patch_path], cwd=dest,
                           capture_output=True, env=env)
        out = (r.stdout.decode("utf-8", "replace")
               + r.stderr.decode("utf-8", "replace"))
        skipped = [ln for ln in out.splitlines() if ln.startswith("Skipped patch")]
        ok = r.returncode == 0 and not skipped
        steps.append({"step": "git apply source.patch", "ok": ok,
                      "applied": sum(1 for ln in out.splitlines()
                                     if ln.startswith("Applied patch")),
                      "skipped": len(skipped),
                      # --verbose writes progress to stderr, so stderr is not
                      # evidence of failure here; only report it when it is.
                      "error": None if ok else
                               ("; ".join(skipped)[:400] if skipped else
                                r.stderr.decode("utf-8", "replace")[:400] or None)})
    else:
        steps.append({"step": "git apply source.patch", "ok": None,
                      "error": "no patch recorded" if not patch_path else "skipped"})

    bundle_path = bundle_path or _abs(manifest.get("source_bundle", {}).get("path"))
    if bundle_path and os.path.exists(bundle_path):
        with zipfile.ZipFile(bundle_path) as z:
            names = z.namelist()
            z.extractall(dest)
        steps.append({"step": "unzip source_bundle.zip over the tree",
                      "ok": True, "files": len(names)})
    else:
        steps.append({"step": "unzip source_bundle.zip over the tree",
                      "ok": False, "error": "bundle missing"})
    return steps


def verify_tree(manifest, tree):
    """Re-hash every manifest file inside a restored tree. 25/25 or nothing."""
    rows = []
    for rel, info in sorted(manifest.get("source_files", {}).items()):
        want = info.get("sha256")
        p = os.path.join(tree, rel)
        if want is None:
            rows.append({"path": rel, "status": "skipped",
                         "why": "credential-shaped; never hashed"})
            continue
        if not os.path.isfile(p):
            rows.append({"path": rel, "status": "MISSING", "expected": want})
            continue
        with open(p, "rb") as fh:
            got = hashlib.sha256(fh.read()).hexdigest()
        rows.append({"path": rel, "expected": want, "measured": got,
                     "status": "pass" if got == want else "FAIL"})
    return rows


def _abs(rel):
    if not rel:
        return None
    return rel if os.path.isabs(rel) else os.path.join(paths.REPO_ROOT, rel)


def registry_snapshot(entries):
    """The registry exactly as executed, minus derived fields.

    Stored in full because a run's meaning depends on it: which commands an id
    mapped to, which suite it belonged to, what its gates were. Reading today's
    experiments.py to interpret last month's run is how a record goes stale.
    """
    keep = ("id", "phase", "status", "lifecycle", "title", "asks", "cmds",
            "suites", "replay", "deps", "requires_api", "requires_gpu",
            "expensive", "primary_metric", "sample_unit", "expected_outputs",
            "estimated_runtime", "result", "result2", "superseded", "note",
            "how", "metric_meaning", "limits")
    return [{k: e[k] for k in keep if k in e} for e in entries]


def write(run_id, *, registry, argv_lists=(), artifact_root=None, extra=None):
    rdir = paths.run_dir(run_id, artifact_root)
    os.makedirs(rdir, exist_ok=True)

    src = {}
    src.update(_collect(ALWAYS))
    src.update(_collect(_walk_dirs(ALWAYS_DIRS)))
    invoked = modules_from_argv(argv_lists)
    src.update(_collect(invoked))

    data = {}
    for rel in KEY_DATA:
        full = os.path.join(paths.REPO_ROOT, rel)
        if os.path.exists(full):
            # cheap identity for multi-hundred-MB files: size + mtime + head/tail
            st = os.stat(full)
            h = hashlib.sha256()
            with open(full, "rb") as fh:
                h.update(fh.read(1 << 20))
                if st.st_size > (2 << 20):
                    fh.seek(-(1 << 20), os.SEEK_END)
                    h.update(fh.read())
            h.update(f"{st.st_size}".encode())
            data[rel] = {"sha256_head_tail_size": h.hexdigest(),
                         "bytes": st.st_size,
                         "note": "head+tail+size digest; full hash in manifest.json"}

    snapshot = registry_snapshot(registry)
    status = _git("status", "--porcelain") or ""
    dirty = bool(status.strip())

    # How many manifest files git actually tracks -- i.e. how far commit+patch
    # can get you. Recorded so the shortfall is a number in the record rather
    # than something a reader has to discover.
    tracked = set()
    for rel in src:
        r = subprocess.run(["git", "ls-files", "--error-unmatch", rel],
                           cwd=paths.REPO_ROOT, capture_output=True)
        if r.returncode == 0:
            tracked.add(rel)
    n_tracked = len(tracked)

    patch_rel = None
    patch_sha = None
    if dirty:
        raw = _git("diff", "HEAD", binary=False)
        if raw is not None:
            clean = SECRET_VALUE.sub("<redacted>", raw)
            # drop hunks belonging to credential-shaped paths entirely
            blocks, keep_block = [], True
            for line in clean.splitlines(keepends=True):
                if line.startswith("diff --git "):
                    keep_block = not SECRET_PATH.search(line)
                    if not keep_block:
                        blocks.append(f"# [omitted: {line.strip()} "
                                      f"-- path looks credential-bearing]\n")
                if keep_block:
                    blocks.append(line)
            patch = "".join(blocks)
            ppath = os.path.join(rdir, "source.patch")
            atomic_write(ppath, patch)
            patch_rel = paths.rel(ppath)
            patch_sha = hashlib.sha256(patch.encode("utf-8")).hexdigest()

    bundle_path, members, bundle_skipped = write_bundle(rdir, src)
    with open(bundle_path, "rb") as fh:
        bundle_sha = hashlib.sha256(fh.read()).hexdigest()
    selfcheck = bundle_selfcheck(bundle_path, members)

    fp = hashlib.sha256()
    for rel in sorted(src):
        fp.update(rel.encode())
        fp.update((src[rel].get("sha256") or "none").encode())
    fp.update(json.dumps(snapshot, sort_keys=True, ensure_ascii=False,
                         default=str).encode())
    fingerprint = fp.hexdigest()[:16]

    payload = {
        "run_id": run_id,
        "fingerprint": fingerprint,
        "fingerprint_covers": ("per-file sha256 of the source files listed below "
                               "plus the full registry snapshot"),
        "git": {
            "commit": (_git("rev-parse", "HEAD") or "").strip() or None,
            "branch": (_git("rev-parse", "--abbrev-ref", "HEAD") or "").strip() or None,
            "dirty": dirty,
            "dirty_files": sorted(l[3:] for l in status.splitlines()) if dirty else [],
            "patch": patch_rel,
            "patch_sha256": patch_sha,
            "patch_covers": ("tracked files only. `git diff HEAD` cannot see "
                             "untracked files, so the patch alone does NOT "
                             "reconstruct this run -- use source_bundle.zip."),
            "patch_reconstructs_n_files": n_tracked,
            "reconstruct": ("git checkout <commit> && git apply " + patch_rel
                            + "  # tracked files only -- NOT sufficient")
                           if patch_rel else "git checkout <commit>",
        },
        "source_bundle": {
            "path": paths.rel(bundle_path),
            "sha256": bundle_sha,
            "n_files": len(members),
            "bytes": os.path.getsize(bundle_path),
            "members": members,
            "excluded": bundle_skipped,
            "contains": ("source only: the files listed in source_files. No "
                         "dataset, model, vector, index, API log, response or "
                         "credential is included."),
            "selfcheck": selfcheck,
            "reconstruction": [
                "git archive --format=zip <commit> -o head.zip   "
                "# read-only; never `git checkout` a dirty tree",
                "unzip head.zip -d <tree>",
                "cd <tree> && git apply <run>/source.patch        "
                "# tracked-file working-tree deltas",
                "unzip -o <run>/source_bundle.zip -d <tree>       "
                "# authoritative: overwrites with the exact bytes that ran",
                "python -m expkit.source reconstruct --run <run_id>  "
                "# does all of the above and re-hashes every file",
            ],
            "authority": ("source_bundle.zip is the final source snapshot. The "
                          "patch records working-tree modifications to tracked "
                          "files and is kept for review; where the two differ, "
                          "the bundle is what ran."),
        },
        "python": {"executable": sys.executable,
                   "version": sys.version.split()[0]},
        "source_files": src,
        "invoked_modules": invoked,
        "key_data_files": data,
        "registry_snapshot": snapshot,
        "n_source_files": len(src),
        "n_source_files_tracked_by_git": n_tracked,
        "n_source_files_untracked": len(src) - n_tracked,
        "n_registry_entries": len(snapshot),
    }
    if extra:
        payload.update(extra)
    out = os.path.join(rdir, "source_manifest.json")
    atomic_json(out, payload)
    return payload, paths.rel(out)


def load(run_id, artifact_root=None):
    p = os.path.join(paths.run_dir(run_id, artifact_root), "source_manifest.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------
# CLI: prove the bundle restores, rather than asserting that it would
# --------------------------------------------------------------------------
def cmd_reconstruct(a):
    run_id = paths.resolve_run(a.run, a.artifact_root)
    man = load(run_id, a.artifact_root)
    if man is None:
        raise SystemExit(f"run {run_id} has no source_manifest.json")
    dest = a.into or os.path.join(
        paths.artifact_root(a.artifact_root), "test-runs",
        time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-source-restore", "tree")
    if os.path.isdir(dest) and a.clean:
        shutil.rmtree(dest)
    os.makedirs(dest, exist_ok=True)

    print("=" * 88)
    print(f"RECONSTRUCT {run_id}  ->  {dest}")
    print("=" * 88)
    steps = restore(man, dest, bundle_path=a.bundle,
                    apply_patch=not a.no_patch)
    for st in steps:
        mark = {True: "ok", False: "**FAIL**", None: "skip"}[st["ok"]]
        extra = (f"  {st['files']} files" if st.get("files") is not None else "")
        if st.get("applied") is not None:
            extra += f"  {st['applied']} hunks applied, {st['skipped']} skipped"
        err = f"  {st['error']}" if st.get("error") else ""
        print(f"  {st['step']:<44}{mark}{extra}{err}")

    rows = verify_tree(man, dest)
    n_pass = sum(1 for r in rows if r["status"] == "pass")
    n_fail = sum(1 for r in rows if r["status"] in ("FAIL", "MISSING"))
    n_skip = sum(1 for r in rows if r["status"] == "skipped")
    print()
    print(f"SOURCE VERIFICATION  pass {n_pass}/{len(rows)}   "
          f"FAIL {n_fail}   skipped {n_skip}")
    print("-" * 88)
    width = max(len(r["path"]) for r in rows)
    for r in rows:
        if r["status"] == "pass" and not a.verbose:
            continue
        print(f"  {r['path']:<{width}}  {r['status']}")
    if not a.verbose and not n_fail:
        print(f"  (all {n_pass} files matched; --verbose to list them)")
    print("-" * 88)
    print(f"fingerprint claimed : {man.get('fingerprint')}")
    print(f"bundle sha256       : {(man.get('source_bundle') or {}).get('sha256')}")
    print(f"tree                : {dest}")
    if n_fail:
        print("\nRECONSTRUCTION FAILED -- the recorded source cannot be restored.")
        return 1
    print("\nRECONSTRUCTION OK -- every fingerprinted file restored byte-exact.")
    return 0


def cmd_check_bundle(a):
    run_id = paths.resolve_run(a.run, a.artifact_root)
    man = load(run_id, a.artifact_root)
    if man is None:
        raise SystemExit(f"run {run_id} has no source_manifest.json")
    b = man.get("source_bundle")
    if not b:
        print(f"run {run_id} predates source_bundle.zip -- nothing to check")
        return 1
    path = a.bundle or _abs(b["path"])
    if not os.path.exists(path):
        print(f"**FAIL** bundle missing: {path}")
        return 1
    with open(path, "rb") as fh:
        got = hashlib.sha256(fh.read()).hexdigest()
    container_ok = got == b["sha256"]
    res = bundle_selfcheck(path, b["members"])
    print(f"bundle           {paths.rel(path)}")
    print(f"container sha256 {'ok' if container_ok else '**FAIL**'}  {got}")
    print(f"members          {res['n_ok']}/{res['n_members']} hash-match")
    for f in res["failures"]:
        print(f"  **FAIL** {f['path']}  {f.get('why', 'hash mismatch')}")
    for e in res["unexpected_members"]:
        print(f"  **FAIL** unexpected member {e}")
    bad = (not container_ok) or res["status"] != "pass"
    print("BUNDLE " + ("FAILED" if bad else "OK"))
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m expkit.source",
                                 description="restore and verify a run's source")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("reconstruct",
                       help="rebuild the source tree from commit + patch + bundle "
                            "and re-hash every fingerprinted file")
    r.add_argument("--run", default="latest")
    r.add_argument("--into", default=None, help="destination tree")
    r.add_argument("--bundle", default=None, help="override the bundle path")
    r.add_argument("--no-patch", action="store_true")
    r.add_argument("--clean", action="store_true", help="wipe --into first")
    r.add_argument("--artifact-root", default=None)
    r.add_argument("--verbose", action="store_true")
    r.set_defaults(fn=cmd_reconstruct)

    c = sub.add_parser("check-bundle",
                       help="hash the bundle and every member in place")
    c.add_argument("--run", default="latest")
    c.add_argument("--bundle", default=None)
    c.add_argument("--artifact-root", default=None)
    c.set_defaults(fn=cmd_check_bundle)

    a = ap.parse_args(argv)
    raise SystemExit(a.fn(a))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
