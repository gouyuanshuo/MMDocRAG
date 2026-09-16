"""One command to check the code and recompute completed experiments from caches.

    python reproduce.py --dry-run
    python reproduce.py
    python reproduce.py --resume <cached_run_id> --skip-tests

Never calls a paid API, downloads a model, or overwrites saved API responses.
Missing inputs and failed experiments produce a nonzero exit code.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-tests", action="store_true")
    ap.add_argument("--resume", default="")
    ap.add_argument("--only", default="", help="comma-separated experiment IDs")
    a = ap.parse_args()
    os.chdir(ROOT)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    suite = [sys.executable, "experiments.py", "run-suite", "cached", "--offline"]
    if a.only:
        suite += ["--only", a.only]
    if a.resume:
        suite += ["--resume", a.resume]
    if a.dry_run:
        raise SystemExit(subprocess.call(suite + ["--dry-run"], env=env))
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    logs = ROOT/"artifacts/logs"
    logs.mkdir(parents=True, exist_ok=True)
    tasks = []
    if not a.skip_tests:
        for module in ("tests.test_runner", "tests.test_source_bundle",
                       "tests.test_statistics", "tests.test_phase3"):
            cmd = [sys.executable, "-m", module]
            if module in ("tests.test_runner", "tests.test_source_bundle"):
                cmd += ["--scratch-root", "artifacts/test-runs"]
            tasks.append((module, cmd))
    tasks.append(("cached", suite))
    records = []

    def run(label, cmd):
        path = logs/f"reproduce_{stamp}_{label}.log"
        print(f"{label}: {path}", flush=True)
        started = time.monotonic()
        with path.open("w", encoding="utf-8") as fh:
            rc = subprocess.call(cmd, cwd=ROOT, env=env, stdout=fh, stderr=subprocess.STDOUT)
        records.append(dict(task=label, argv=cmd, returncode=rc, log=str(path),
                            seconds=round(time.monotonic()-started, 2), bytes=path.stat().st_size))
        (logs/f"reproduce_{stamp}.json").write_text(
            json.dumps(records, indent=2), encoding="utf-8")
        print(f"{label}: {'PASS' if rc == 0 else 'FAIL'} ({rc})", flush=True)
        return rc, path

    failed = False
    for label, cmd in tasks:
        rc, path = run(label, cmd)
        failed |= rc != 0
        if label == "cached":
            content = path.read_text(encoding="utf-8")
            match = re.search(r"(?m)^run_id\s+(\S+)", content)
            if match:
                rid = match.group(1)
                print(f"Report: artifacts/runs/{rid}/summary.html", flush=True)
                print(f"Resume: python reproduce.py --skip-tests --resume {rid}"
                      + (f" --only {a.only}" if a.only else ""), flush=True)
                ids = set(a.only.upper().split(",")) if a.only else {"E24", "E27"}
                for eid in ("E24", "E27"):
                    if eid in ids:
                        vrc, _ = run(f"verify_{eid}", [sys.executable, "experiments.py",
                                    "verify", eid, "--run", rid])
                        failed |= vrc != 0
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
