"""Subprocess execution that keeps the terminal live and the logs complete.

Two properties matter and they pull against each other. The operator wants to
watch a long retrieval sweep scroll by; the record needs every byte of that
scroll on disk. So output is tee'd: read from the pipe, written to the log file
and echoed to this process's stdout in the same loop.

Everything runs with `shell=False` and an argv list. The previous runner passed
a formatted string to `shell=True`, which on Windows routes through cmd.exe --
that mangles quoting, cannot express a path with spaces reliably, and makes the
recorded command a string that may not re-execute the same way. An argv array in
the log is unambiguous and replayable.
"""

import json
import os
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from expkit import paths                 # noqa: E402
from expkit.results import atomic_json   # noqa: E402


def _pump(stream, sink_path, echo, prefix=""):
    """Drain one pipe into a file and to the terminal, losing nothing."""
    os.makedirs(os.path.dirname(sink_path), exist_ok=True)
    with open(sink_path, "w", encoding="utf-8", newline="") as fh:
        for line in iter(stream.readline, ""):
            fh.write(line)
            fh.flush()                    # a killed run must keep its partial log
            if echo:
                try:
                    echo.write(prefix + line)
                    echo.flush()
                except Exception:
                    pass
    stream.close()


def run_command(argv, *, cwd=None, outdir=None, env_overlay=None, echo=True,
                timeout=None, label="", exp_id=""):
    """Execute one command. Returns a status dict; never raises on exit code."""
    cwd = cwd or paths.REPO_ROOT
    outdir = outdir or os.path.join(paths.REPO_ROOT, "artifacts", "runs", "_adhoc")
    os.makedirs(outdir, exist_ok=True)
    stdout_log = os.path.join(outdir, "stdout.log")
    stderr_log = os.path.join(outdir, "stderr.log")

    env = dict(os.environ)
    env.update(env_overlay or {})
    # Children must not inherit a stale metrics dir from a previous experiment.
    env["MMDOCRAG_METRICS_OUT"] = outdir
    if exp_id:
        env["MMDOCRAG_EXP_ID"] = exp_id
    else:
        env.pop("MMDOCRAG_EXP_ID", None)

    started = time.time()
    record = {
        "label": label,
        "argv": list(argv),
        "cwd": cwd,
        "python": sys.executable,
        "stdout_log": paths.rel(stdout_log),
        "stderr_log": paths.rel(stderr_log),
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
        "env_overlay": {k: v for k, v in (env_overlay or {}).items()},
    }
    atomic_json(os.path.join(outdir, "command.json"), record)

    try:
        proc = subprocess.Popen(
            list(argv), cwd=cwd, env=env, shell=False,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1)
    except (OSError, ValueError) as exc:
        record.update({"returncode": None, "elapsed_sec": 0.0,
                       "status": "error", "error": f"could not start: {exc}",
                       "ended_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        atomic_json(os.path.join(outdir, "command.json"), record)
        return record

    t_out = threading.Thread(target=_pump, args=(proc.stdout, stdout_log,
                                                 sys.stdout if echo else None))
    t_err = threading.Thread(target=_pump, args=(proc.stderr, stderr_log,
                                                 sys.stderr if echo else None, ""))
    t_out.start()
    t_err.start()
    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.kill()
        proc.wait()
    t_out.join()
    t_err.join()

    elapsed = time.time() - started
    record.update({
        "returncode": proc.returncode,
        "elapsed_sec": round(elapsed, 3),
        "ended_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "timed_out": timed_out,
        "status": "ok" if (proc.returncode == 0 and not timed_out) else "error",
    })
    if record["status"] == "error":
        record["error"] = (f"timed out after {timeout}s" if timed_out
                           else f"exit code {proc.returncode}")
        tail = []
        if os.path.exists(stderr_log):
            with open(stderr_log, encoding="utf-8", errors="replace") as fh:
                tail = fh.read().splitlines()[-25:]
        record["stderr_tail"] = tail
    atomic_json(os.path.join(outdir, "command.json"), record)
    return record


def run_experiment(exp, run_id, *, cmd_indices=None, dry_run=False,
                   env_overlay=None, artifact_root=None, echo=True,
                   timeout=None):
    """Run one experiment's commands into artifacts/runs/<run>/experiments/<id>/.

    Multiple commands share one experiment directory; per-command logs are
    suffixed so nothing is overwritten, and `status.json` aggregates them.
    """
    exp_id = exp["id"]
    outdir = paths.experiment_dir(run_id, exp_id, artifact_root)
    os.makedirs(outdir, exist_ok=True)

    cmds = exp.get("argv") or []
    if cmd_indices is not None:
        cmds = [cmds[i] for i in cmd_indices if 0 <= i < len(cmds)]

    status = {
        "experiment": exp_id,
        "title": exp.get("title", ""),
        "run_id": run_id,
        "lifecycle": exp.get("lifecycle"),
        "primary_metric": exp.get("primary_metric"),
        "sample_unit": exp.get("sample_unit"),
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "commands": [],
        "dry_run": dry_run,
    }

    if not cmds:
        status.update({"status": "manual", "ended_utc": status["started_utc"],
                       "reason": "no runnable commands (manual verification)"})
        atomic_json(os.path.join(outdir, "status.json"), status)
        return status

    overall = "ok"
    for i, argv in enumerate(cmds):
        argv = [a.replace("{py}", sys.executable) for a in argv]
        sub = outdir if len(cmds) == 1 else os.path.join(outdir, f"cmd{i}")
        os.makedirs(sub, exist_ok=True)
        printable = " ".join(argv)
        print(f"\n  $ {printable}", flush=True)
        if dry_run:
            status["commands"].append({"argv": argv, "status": "dry-run",
                                       "outdir": paths.rel(sub)})
            continue
        rec = run_command(argv, outdir=sub, env_overlay=env_overlay, echo=echo,
                          timeout=timeout, label=f"{exp_id}#{i}", exp_id=exp_id)
        rec["outdir"] = paths.rel(sub)
        status["commands"].append(rec)
        if rec["status"] != "ok":
            overall = "error"
            break                          # later commands usually depend on earlier

    status["status"] = "dry-run" if dry_run else overall
    status["ended_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    status["elapsed_sec"] = round(
        sum(c.get("elapsed_sec") or 0 for c in status["commands"]), 3)

    # Collect any metrics.json the child wrote (single-command experiments write
    # into outdir directly; multi-command ones into cmdN/).
    found = []
    for root, _, files in os.walk(outdir):
        if "metrics.json" in files:
            found.append(os.path.join(root, "metrics.json"))
    status["metrics_files"] = [paths.rel(p) for p in sorted(found)]
    status["instrumented"] = bool(found)
    atomic_json(os.path.join(outdir, "status.json"), status)
    return status


def skip_experiment(exp, run_id, state, reason, artifact_root=None):
    """Record a skip as a first-class outcome. A skipped experiment must never
    be summarised as if it had run."""
    outdir = paths.experiment_dir(run_id, exp["id"], artifact_root)
    os.makedirs(outdir, exist_ok=True)
    status = {
        "experiment": exp["id"],
        "title": exp.get("title", ""),
        "run_id": run_id,
        "lifecycle": exp.get("lifecycle"),
        "status": state,                   # skipped | manual | blocked
        "reason": reason,
        "commands": [],
        "metrics_files": [],
        "instrumented": False,
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ended_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_sec": 0.0,
    }
    atomic_json(os.path.join(outdir, "status.json"), status)
    return status


def load_status(run_id, exp_id, artifact_root=None):
    p = os.path.join(paths.experiment_dir(run_id, exp_id, artifact_root), "status.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)
