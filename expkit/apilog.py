"""Per-request persistence for anything that costs money.

An API call is the one operation in this project that cannot be repeated for
free. That makes the log of it a primary artifact, not a debugging aid. Three
rules follow:

    EVERY attempt is recorded, including failures. A 429 that is not written
    down looks exactly like a request that was never made, and the difference
    decides whether resuming is safe.

    Records are flushed per question, atomically. A run killed by a daily quota
    at question 613 must lose nothing; the next run reads the log and skips what
    already succeeded.

    Secrets never enter the log. Keys, Authorization headers and anything that
    looks like a bearer token are redacted before serialization, in one place,
    so no caller can forget.

Resume keys on `request_hash` -- a digest of (provider, model, mode, prompt
hash, question id, and the actual quote payload). Keying on question id alone
would silently reuse a response produced from a different candidate set, which
is precisely the mistake that would make an end-to-end retrieval comparison
meaningless.

Cost is recorded as `estimated_cost_usd` with `price_verified: false` and the
price table that produced it. Token usage from the provider is stored verbatim
and is the only figure that may be reported as measured.
"""

import hashlib
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from expkit import paths                            # noqa: E402
from expkit.results import atomic_json              # noqa: E402

# Anchored deliberately. A bare `token` substring also matches `input_tokens`
# and `total_tokens`, which would redact the usage counts -- the one field that
# must survive verbatim, because it is the measured cost of the run.
SECRET_KEYS = re.compile(
    r"^(.*[_\-])?("
    r"api[_\-]?keys?|authorization|auth|bearer|secret[a-z_\-]*|password|passwd|"
    r"credentials?|access[_\-]?token|refresh[_\-]?token|id[_\-]?token|"
    r"auth[_\-]?token|bearer[_\-]?token|session[_\-]?token|token"
    r")$", re.I)
SECRET_VALUE = re.compile(r"\b(sk-[A-Za-z0-9_\-]{8,}|AIza[A-Za-z0-9_\-]{10,}|"
                          r"xai-[A-Za-z0-9_\-]{8,})")


def redact(obj):
    """Strip secrets anywhere in a nested structure, by key name and by shape."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if SECRET_KEYS.search(str(k)):
                out[k] = "<redacted>"
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [redact(v) for v in obj]
    if isinstance(obj, str):
        return SECRET_VALUE.sub("<redacted>", obj)
    return obj


def sha(text, n=16):
    return hashlib.sha256(str(text).encode("utf-8", "replace")).hexdigest()[:n]


def file_hash(path, n=16):
    if not path or not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()[:n]


def request_hash(*, provider, model, mode, prompt_hash, question_uid, payload):
    """Stable across runs, sensitive to anything that changes the answer.

    `payload` must include the actual quotes shown. Two runs of the same
    question under different retrieval configurations are different requests,
    and resume must not conflate them.
    """
    parts = [provider or "", model or "", mode or "", prompt_hash or "",
             str(question_uid), sha(json.dumps(payload, sort_keys=True,
                                               ensure_ascii=False, default=str), 32)]
    return sha("|".join(parts), 24)


class APILog:
    """Append-only JSONL log with an index for resume."""

    def __init__(self, name, *, experiment_id="", run_id="", artifact_root=None):
        self.dir = os.path.join(paths.api_root(artifact_root), name)
        os.makedirs(self.dir, exist_ok=True)
        self.path = os.path.join(self.dir, "requests.jsonl")
        self.index_path = os.path.join(self.dir, "index.json")
        self.experiment_id = experiment_id
        self.run_id = run_id or os.environ.get("MMDOCRAG_RUN_ID", "")
        self.index = {}
        self._load()

    def _load(self):
        if not os.path.exists(self.path):
            return
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue          # a torn final line from a killed process
                rh = rec.get("request_hash")
                if not rh:
                    continue
                prev = self.index.get(rh)
                # success always wins over a previous error for the same request
                if prev is None or rec.get("status") == "success":
                    self.index[rh] = rec

    def done(self, rh):
        rec = self.index.get(rh)
        return bool(rec and rec.get("status") == "success")

    def get(self, rh):
        return self.index.get(rh)

    def append(self, record):
        """Write one record and fsync it. Called once per attempt."""
        record = redact(record)
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
        rh = record.get("request_hash")
        if rh and (record.get("status") == "success" or rh not in self.index):
            self.index[rh] = record
        return record

    def save_index(self):
        atomic_json(self.index_path, {
            "updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "n_records": len(self.index),
            "n_success": sum(1 for r in self.index.values()
                             if r.get("status") == "success"),
            "n_error": sum(1 for r in self.index.values()
                           if r.get("status") == "error"),
            "log": paths.rel(self.path),
        })

    def stats(self):
        ok = sum(1 for r in self.index.values() if r.get("status") == "success")
        err = sum(1 for r in self.index.values() if r.get("status") == "error")
        tok_in = sum((r.get("usage") or {}).get("input_tokens") or 0
                     for r in self.index.values())
        tok_out = sum((r.get("usage") or {}).get("output_tokens") or 0
                      for r in self.index.values())
        return {"records": len(self.index), "success": ok, "error": err,
                "input_tokens": tok_in, "output_tokens": tok_out}

    def write_plan(self, plan):
        """The call-volume estimate, written BEFORE any request is issued."""
        atomic_json(os.path.join(self.dir, "plan.json"), redact(plan))
        return os.path.join(self.dir, "plan.json")


def make_record(*, request_hash_, provider, model, mode, question_uid, doc_name,
                experiment_id, run_id, prompt_path, prompt_hash, params,
                attempt=1, model_revision=None):
    """The fixed skeleton of a request record, filled in before the call."""
    return {
        "request_id": f"{request_hash_}-a{attempt}",
        "request_hash": request_hash_,
        "experiment_id": experiment_id,
        "run_id": run_id,
        "question_uid": question_uid,
        "doc_name": doc_name,
        "provider": provider,
        "model": model,
        "model_revision": model_revision,
        "mode": mode,
        "prompt_template": paths.rel(prompt_path) if prompt_path else None,
        "prompt_hash": prompt_hash,
        "params": params,
        "attempt": attempt,
        "requested_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "pending",
    }


def finish_record(rec, *, status, latency_sec, raw_response=None,
                  parsed_response=None, usage=None, provider_request_id=None,
                  error=None, http_status=None, rate_limit=None,
                  price_table=None):
    rec = dict(rec)
    rec.update({
        "status": status,
        "completed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "latency_sec": round(latency_sec, 3),
        "raw_response": raw_response,
        "parsed_response": parsed_response,
        "usage": usage,                       # verbatim from the provider
        "provider_request_id": provider_request_id,
        "http_status": http_status,
        "error": error,
        "rate_limit": rate_limit,
    })
    if price_table and usage:
        try:
            cost = ((usage.get("input_tokens") or 0) / 1e6 * price_table["in_per_mtok"]
                    + (usage.get("output_tokens") or 0) / 1e6 * price_table["out_per_mtok"])
            rec["estimated_cost_usd"] = round(cost, 6)
            rec["price_table"] = price_table
            # never presented as measured: the price side is unverified even
            # when the token side came from the provider
            rec["price_verified"] = bool(price_table.get("verified"))
        except Exception:
            rec["estimated_cost_usd"] = None
    return rec


# --------------------------------------------------------------------------
# Mock provider: exercises persistence, resume and error handling with no
# network and no spend. The API path must be tested, and testing it against a
# real provider would mean paying to find out that the logging works.
# --------------------------------------------------------------------------
class MockProvider:
    """Deterministic fake. `fail_on` question ids return an error record."""

    name = "mock"

    def __init__(self, model="mock-model-v1", fail_on=(), latency=0.001,
                 rate_limit_on=()):
        self.model = model
        self.fail_on = set(str(x) for x in fail_on)
        self.rate_limit_on = set(str(x) for x in rate_limit_on)
        self.latency = latency
        self.calls = 0

    def generate(self, question_uid, question, text_quotes, img_quotes):
        self.calls += 1
        time.sleep(self.latency)
        qid = str(question_uid)
        if qid in self.rate_limit_on:
            return {"ok": False, "error": "429 RESOURCE_EXHAUSTED", "http_status": 429,
                    "rate_limit": {"quotaId": "MockRequestsPerDay", "quotaValue": 20},
                    "usage": None, "provider_request_id": None, "raw": None}
        if qid in self.fail_on:
            return {"ok": False, "error": "500 internal error", "http_status": 500,
                    "rate_limit": None, "usage": None,
                    "provider_request_id": None, "raw": None}
        cited = [q.get("quote_id") for q in (text_quotes or [])[:2]]
        cited += [q.get("quote_id") for q in (img_quotes or [])[:1]]
        text = ("Mock answer for " + qid + ". "
                + " ".join(f"[{c}]" for c in cited if c))
        return {
            "ok": True,
            "raw": {"id": f"mock-{sha(qid, 8)}", "text": text},
            "parsed": text,
            "usage": {"input_tokens": 100 + len(text_quotes or []) * 25,
                      "output_tokens": 20 + len(cited) * 3,
                      "total_tokens": None},
            "provider_request_id": f"mockreq-{sha(qid, 10)}",
            "http_status": 200,
            "rate_limit": None,
            "error": None,
        }
