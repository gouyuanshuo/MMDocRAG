"""Does the source record actually restore the source?

`source_manifest.json` has always been able to *detect* that code changed: it
carries a SHA-256 per file. Restoring the code is a different capability, and the
manifest claimed it without having it. Its reconstruction line read

    git checkout <commit> && git apply source.patch

but `git diff HEAD` only sees tracked files, and 18 of this project's 25
fingerprinted source files have never been committed. Measured against run
20260828T080756Z_replay, that recipe restores 7 files and leaves 18 missing.

So this test does not read the claim. It performs it:

    1  git archive <commit>            -- read-only; a `git checkout` here would
                                          destroy months of uncommitted work
    2  git apply source.patch          -- tracked-file working-tree deltas
    3  unzip source_bundle.zip         -- the authoritative bytes
    4  sha256 every file in the manifest and require every single one to match

Then it breaks the bundle on purpose, twice, and requires the verifier to exit 1
each time. A check that cannot fail is not evidence, so both directions are
tested: an untracked member deleted (nothing else can supply it) and a tracked
member corrupted (proving the bundle, not the patch, is what the verifier
trusts).

Everything lands under `--scratch-root`; the last group re-hashes every project
file the manifest names and asserts the test changed none of them, and that no
pre-existing run directory disappeared.

Run:
    python -m tests.test_source_bundle --scratch-root artifacts/test-runs
    python -m tests.test_source_bundle --run 20260828T080756Z_replay
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from expkit import paths, source                      # noqa: E402

PASS, FAIL = [], []


def check(label, ok, detail=""):
    (PASS if ok else FAIL).append(label)
    print(f"   {'ok  ' if ok else 'FAIL'}  {label}" + (f"   [{detail}]" if detail else ""))
    return ok


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def reconstruct_cli(run_id, into, bundle=None, artifact_root=None):
    """Run the verifier as a subprocess so its EXIT CODE is what we assert on.

    Calling the function in-process would test the return value; CI, a Makefile
    and a human all read the exit code instead.
    """
    argv = [sys.executable, "-m", "expkit.source", "reconstruct",
            "--run", run_id, "--into", into, "--clean"]
    if bundle:
        argv += ["--bundle", bundle]
    if artifact_root:
        argv += ["--artifact-root", artifact_root]
    r = subprocess.run(argv, cwd=paths.REPO_ROOT, capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", "replace") + \
        r.stderr.decode("utf-8", "replace")


# ---------------------------------------------------------------------------
def test_bundle_present_and_intact(run_id, man):
    print("\n1. the bundle exists, and its bytes are what the manifest says")
    b = man.get("source_bundle")
    if not check("manifest records a source_bundle", bool(b),
                 "run predates the bundle" if not b else ""):
        return None
    path = b["path"] if os.path.isabs(b["path"]) else \
        os.path.join(paths.REPO_ROOT, b["path"])
    if not check("source_bundle.zip exists", os.path.exists(path), path):
        return None
    check("container sha256 matches the manifest", sha(path) == b["sha256"],
          b["sha256"][:16])
    res = source.bundle_selfcheck(path, b["members"])
    check(f"every member hash-matches ({res['n_ok']}/{res['n_members']})",
          res["status"] == "pass", str(res["failures"])[:120])
    check("no unexpected member smuggled in", not res["unexpected_members"],
          str(res["unexpected_members"])[:120])

    # A source bundle must stay a source bundle.
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
    bad = [n for n in names if source.BUNDLE_FORBIDDEN.search(n)
           or source.SECRET_PATH.search(n)]
    check("no dataset / model / vector / index / api-log / secret member",
          not bad, str(bad)[:160])
    check("bundle covers every fingerprinted file",
          set(names) == {k for k, v in man["source_files"].items()
                         if v.get("sha256")},
          f"{len(names)} members vs {man['n_source_files']} manifest files")
    return path


def test_patch_alone_is_insufficient(run_id, man, root):
    """The finding that motivated the bundle, re-measured rather than recited."""
    print("\n2. commit + patch alone does NOT restore the run (the original bug)")
    tree = os.path.join(root, "patch-only", "tree")
    steps = source.restore(man, tree, bundle_path=os.path.join(root, "no-such.zip"))
    arch = next((s for s in steps if s["step"].startswith("git archive")), {})
    check("git archive succeeded", arch.get("ok") is True,
          f"{arch.get('files')} files at {str(arch.get('commit'))[:12]}")
    ap = next((s for s in steps if s["step"].startswith("git apply")), {})
    # `git apply` prints "Skipped patch 'x'" and exits 0 when it discovers the
    # surrounding repository instead of the restored tree. Asserting on the exit
    # code alone let that pass once; assert on the work it claims to have done.
    check("git apply actually applied its hunks", ap.get("ok") is True,
          f"{ap.get('applied')} applied, {ap.get('skipped')} skipped"
          f"{' -- ' + str(ap.get('error'))[:80] if ap.get('error') else ''}")
    rows = source.verify_tree(man, tree)
    n_ok = sum(1 for r in rows if r["status"] == "pass")
    n_missing = sum(1 for r in rows if r["status"] == "MISSING")
    tracked = man.get("n_source_files_tracked_by_git")
    check(f"patch route restores only the tracked files "
          f"({n_ok}/{len(rows)}, {n_missing} missing)",
          n_missing > 0, "if this passes, every file is tracked and the "
                         "bundle is belt-and-braces rather than load-bearing")
    if tracked is not None:
        check("restored count equals the recorded tracked-file count",
              n_ok == tracked, f"{n_ok} vs {tracked}")


def test_full_reconstruction(run_id, man, root):
    print("\n3. commit + patch + bundle restores every fingerprinted file")
    tree = os.path.join(root, "restore", "tree")
    code, out = reconstruct_cli(run_id, tree)
    check("reconstruct exits 0", code == 0, out.strip().splitlines()[-1][:100]
          if out.strip() else "")
    rows = source.verify_tree(man, tree)
    n_ok = sum(1 for r in rows if r["status"] == "pass")
    n_bad = [r["path"] for r in rows if r["status"] != "pass"]
    total = man["n_source_files"]
    check(f"{n_ok}/{total} files byte-exact", n_ok == total and not n_bad,
          str(n_bad)[:160])
    check("fingerprint recomputes from the restored tree",
          _fingerprint(man, tree) == man["fingerprint"],
          f"{_fingerprint(man, tree)} vs {man['fingerprint']}")
    return tree


def _fingerprint(man, tree):
    """Recompute the 16-hex fingerprint from the restored files + snapshot."""
    import json
    fp = hashlib.sha256()
    for rel in sorted(man["source_files"]):
        p = os.path.join(tree, rel)
        fp.update(rel.encode())
        fp.update((sha(p) if os.path.isfile(p) else "none").encode())
    fp.update(json.dumps(man["registry_snapshot"], sort_keys=True,
                         ensure_ascii=False, default=str).encode())
    return fp.hexdigest()[:16]


def _mutate_bundle(src_zip, dest_zip, drop=None, corrupt=None):
    with zipfile.ZipFile(src_zip) as zin, \
            zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            if drop and info.filename == drop:
                continue
            data = zin.read(info.filename)
            if corrupt and info.filename == corrupt:
                data = data + b"\n# tampered\n"
            zout.writestr(info, data)


def test_tampering_fails_loudly(run_id, man, bundle, root):
    print("\n4. a broken bundle must exit 1, not quietly restore less")
    untracked = next((r for r in sorted(man["source_files"])
                      if not _is_tracked(r)), None)
    tracked = next((r for r in sorted(man["source_files"]) if _is_tracked(r)), None)

    if untracked:
        dropped = os.path.join(root, "tamper-drop.zip")
        _mutate_bundle(bundle, dropped, drop=untracked)
        code, out = reconstruct_cli(run_id, os.path.join(root, "drop", "tree"),
                                    bundle=dropped)
        check(f"deleting an untracked member ({untracked}) -> exit 1",
              code == 1, f"exit {code}")
        check("the missing file is named in the output", untracked in out,
              out.strip().splitlines()[-1][:90] if out.strip() else "")

    if tracked:
        corrupted = os.path.join(root, "tamper-corrupt.zip")
        _mutate_bundle(bundle, corrupted, corrupt=tracked)
        code, out = reconstruct_cli(run_id, os.path.join(root, "corrupt", "tree"),
                                    bundle=corrupted)
        # This one also proves precedence: the patch restores a CORRECT copy of
        # this tracked file, then the bundle overwrites it with the tampered
        # one. If the verifier passed here, the bundle would not be what is
        # actually being trusted.
        check(f"corrupting a tracked member ({tracked}) -> exit 1",
              code == 1, f"exit {code}")
        check("the corrupted file is named in the output", tracked in out,
              out.strip().splitlines()[-1][:90] if out.strip() else "")


def _is_tracked(rel):
    r = subprocess.run(["git", "ls-files", "--error-unmatch", rel],
                       cwd=paths.REPO_ROOT, capture_output=True)
    return r.returncode == 0


def test_no_pollution(man, before_files, before_runs):
    print("\n5. the test changed no project file and removed no run")
    changed = []
    for rel, info in man["source_files"].items():
        if info.get("sha256") is None:
            continue
        p = os.path.join(paths.REPO_ROOT, rel)
        if not os.path.isfile(p) or sha(p) != before_files.get(rel):
            changed.append(rel)
    check("every project source file is byte-identical to before the test",
          not changed, str(changed)[:160])
    now_runs = set(os.listdir(paths.runs_root())) if os.path.isdir(
        paths.runs_root()) else set()
    check("no pre-existing run directory disappeared",
          before_runs <= now_runs, str(sorted(before_runs - now_runs))[:160])
    stray = [d for d in ("dataset", "response") if _new_entries(d)]
    check("nothing new appeared in dataset/ or response/", not stray, str(stray))


_BASELINE_DIRS = {}


def _snapshot_dirs():
    for d in ("dataset", "response"):
        full = os.path.join(paths.REPO_ROOT, d)
        _BASELINE_DIRS[d] = set(os.listdir(full)) if os.path.isdir(full) else set()


def _new_entries(d):
    full = os.path.join(paths.REPO_ROOT, d)
    now = set(os.listdir(full)) if os.path.isdir(full) else set()
    return sorted(now - _BASELINE_DIRS.get(d, now))


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", default="latest")
    ap.add_argument("--artifact-root", default=None)
    ap.add_argument("--scratch-root", default="",
                    help="directory for the restored trees (default: a temp dir). "
                         "artifacts/test-runs keeps them inspectable.")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    if a.scratch_root:
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        root = os.path.abspath(os.path.join(a.scratch_root,
                                            f"{stamp}-source-bundle"))
        os.makedirs(root, exist_ok=True)
    else:
        root = tempfile.mkdtemp(prefix="mmdocrag-bundletest-")

    run_id = paths.resolve_run(a.run, a.artifact_root)
    man = source.load(run_id, a.artifact_root)
    if man is None:
        raise SystemExit(f"run {run_id} has no source_manifest.json")

    print("=" * 78)
    print(f"SOURCE BUNDLE RECONSTRUCTION TEST   run {run_id}")
    print(f"fingerprint {man['fingerprint']}   "
          f"{man['n_source_files']} source files "
          f"({man.get('n_source_files_tracked_by_git', '?')} tracked, "
          f"{man.get('n_source_files_untracked', '?')} untracked)")
    print(f"scratch     {root}")
    print("=" * 78)

    _snapshot_dirs()
    before_files = {rel: sha(os.path.join(paths.REPO_ROOT, rel))
                    for rel, info in man["source_files"].items()
                    if info.get("sha256") and
                    os.path.isfile(os.path.join(paths.REPO_ROOT, rel))}
    before_runs = set(os.listdir(paths.runs_root())) if os.path.isdir(
        paths.runs_root()) else set()

    try:
        bundle = test_bundle_present_and_intact(run_id, man)
        test_patch_alone_is_insufficient(run_id, man, root)
        if bundle:
            test_full_reconstruction(run_id, man, root)
            test_tampering_fails_loudly(run_id, man, bundle, root)
        test_no_pollution(man, before_files, before_runs)
    finally:
        # A restored tree is an intermediate, not evidence: what this test
        # establishes is the pass/fail list below, which is already printed and
        # already recorded in run.json. Keeping every tree cost 36 GB before
        # anyone measured one. So the trees survive only when they can still be
        # used -- on failure, where you need to look at the bytes that differ.
        if a.keep or FAIL:
            print()
            print(f"restored trees kept at {root}"
                  f"{' (failures above)' if FAIL and not a.keep else ''}")
        else:
            shutil.rmtree(root, ignore_errors=True)

    print()
    print("=" * 78)
    print(f"{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        for f in FAIL:
            print(f"  FAILED: {f}")
    print("=" * 78)
    raise SystemExit(1 if FAIL else 0)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
