"""The writer every experiment uses to emit results as data rather than as text.

An experiment gets one `ExperimentResult`, records metrics and per-question rows
into it, and finalizes. The files it writes are the only thing downstream
reporting reads. Nothing in this project re-parses stdout to recover a number,
because a table that was formatted for a human has already lost its precision
and its identity: `0.7328` in a column tells you neither which pool it came from
nor how many documents were behind it.

    from expkit.results import ExperimentResult

    with ExperimentResult("E30", metrics_out=args.metrics_out) as res:
        res.config(pool=args.pool, k=k, seed=SEED, bootstrap=BOOT,
                   sample_unit="document")
        res.metric("main_effect_quota", 0.0263, ci=[0.0185, 0.0344],
                   comparison="official->balanced")
        res.per_question(rows)

If `metrics_out` is empty the writer becomes a no-op that still lets the script
run standalone, so adding instrumentation never breaks direct invocation.
"""

import csv
import json
import os
import platform
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import manifest as manifest_mod          # noqa: E402  (reuse, do not replace)
from expkit import paths                 # noqa: E402

# Every metric carries the settings that make it comparable. A recall with no
# pool, k and sample unit attached is not a result, it is a rumour.
REQUIRED_CONFIG = ("pool", "k")


def atomic_write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    os.replace(tmp, path)


def atomic_json(path, obj):
    atomic_write(path, json.dumps(obj, ensure_ascii=False, indent=2, default=str))


class ExperimentResult:
    """Collects one experiment's output and writes it to `metrics_out`."""

    def __init__(self, exp_id, metrics_out=None, title="", run_id=None):
        # The runner names the experiment, because one script can serve several.
        # `nested_cv.py` is E27's main result and also appeared under E28; the
        # metrics file must say which experiment it was filed under, not which
        # script produced it.
        self.exp_id = os.environ.get("MMDOCRAG_EXP_ID") or exp_id
        self.title = title
        self.run_id = run_id or os.environ.get("MMDOCRAG_RUN_ID", "")
        self.outdir = metrics_out or os.environ.get("MMDOCRAG_METRICS_OUT", "")
        self.enabled = bool(self.outdir)
        self._config = {}
        self._metrics = []
        self._per_question = []
        self._notes = []
        self._data_files = []
        self._started = time.time()
        if self.enabled:
            os.makedirs(self.outdir, exist_ok=True)

    # -- collection ---------------------------------------------------------
    def config(self, **kw):
        """Settings that define what the numbers mean: pool, k, seed, quota..."""
        self._config.update({k: v for k, v in kw.items() if v is not None})
        return self

    def data_file(self, *paths_):
        """Inputs to hash into the manifest, so a changed corpus is visible."""
        self._data_files.extend(p for p in paths_ if p)
        return self

    def note(self, text):
        self._notes.append(text)
        return self

    def metric(self, name, value, **meta):
        """One number plus everything needed to read it correctly.

        `ci`, `n`, `n_documents`, `comparison`, `unit` and `significant` are
        conventional keys; anything else is kept verbatim.
        """
        rec = {"experiment": self.exp_id, "name": name,
               "value": None if value is None else float(value)}
        ci = meta.get("ci")
        if ci is not None:
            lo, hi = float(ci[0]), float(ci[1])
            rec["ci_low"], rec["ci_high"] = lo, hi
            # Recorded, never inferred at report time: an interval whose bound
            # sits on zero must not be rendered as significant by a downstream
            # formatter that only sees the numbers.
            rec["significant"] = bool(lo > 0 or hi < 0)
        for k, v in meta.items():
            if k != "ci":
                rec[k] = v
        rec.update({k: v for k, v in self._config.items() if k not in rec})
        self._metrics.append(rec)
        return self

    def per_question(self, rows):
        """Rows must carry identity, not just a score.

        question_uid and doc_name are what make a per-question file joinable
        against any other experiment's output, and doc_name is what makes a
        document-clustered bootstrap possible after the fact.
        """
        for r in rows:
            rec = dict(r)
            rec.setdefault("experiment", self.exp_id)
            for k, v in self._config.items():
                rec.setdefault(k, v)
            self._per_question.append(rec)
        return self

    # -- output -------------------------------------------------------------
    def finalize(self, status="ok", error=None):
        if not self.enabled:
            return None
        missing = [k for k in REQUIRED_CONFIG if k not in self._config]
        payload = {
            "experiment": self.exp_id,
            "title": self.title,
            "run_id": self.run_id,
            "status": status,
            "error": error,
            "config": self._config,
            "config_missing": missing,
            "elapsed_sec": round(time.time() - self._started, 3),
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "n_metrics": len(self._metrics),
            "n_per_question": len(self._per_question),
            "notes": self._notes,
            "metrics": self._metrics,
        }
        atomic_json(os.path.join(self.outdir, "metrics.json"), payload)

        if self._per_question:
            cols, seen = [], set()
            for r in self._per_question:
                for k in r:
                    if k not in seen:
                        seen.add(k)
                        cols.append(k)
            lead = [c for c in ("experiment", "question_uid", "doc_name") if c in seen]
            cols = lead + [c for c in cols if c not in lead]
            path = os.path.join(self.outdir, "per_question.csv")
            tmp = path + ".tmp"
            # utf-8-sig so Excel on Windows opens the Chinese columns correctly
            with open(tmp, "w", encoding="utf-8-sig", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
                w.writeheader()
                w.writerows(self._per_question)
            os.replace(tmp, path)

        try:
            # flat name: manifest.write treats slashes as subdirectories, and a
            # nested tree inside an experiment's own output dir is just clutter
            mpath = manifest_mod.write(
                self.exp_id,
                data_files=self._data_files,
                extra={"experiment": self.exp_id, "run_id": self.run_id,
                       "argv": sys.argv, "python": sys.executable,
                       "platform": platform.platform(), **self._config},
                results={m["name"]: m["value"] for m in self._metrics},
                outdir=self.outdir)
            # manifest.write timestamps the filename; give the runner a stable
            # name to look for as well
            with open(mpath, encoding="utf-8") as fh:
                atomic_json(os.path.join(self.outdir, "manifest.json"), json.load(fh))
            os.remove(mpath)
        except Exception as exc:                              # pragma: no cover
            atomic_json(os.path.join(self.outdir, "manifest.json"),
                        {"error": f"manifest failed: {exc}"})
        return payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.finalize("ok" if exc_type is None else "error",
                      None if exc_type is None else repr(exc))
        return False


def add_output_args(ap):
    """Standard flags so every instrumented script looks the same."""
    ap.add_argument("--metrics-out", default="",
                    help="directory to write metrics.json / per_question.csv / "
                         "manifest.json into (default: none, print only)")
    return ap
