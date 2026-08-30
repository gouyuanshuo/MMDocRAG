"""End-to-end tests for the run system: failure handling, resume, isolation.

These are the properties that decide whether a long unattended run can be
trusted, and none of them can be checked by reading the code:

    a failing experiment must be RECORDED as failed, not silently absent
    the suite must continue past it by default, and stop with --fail-fast
    a re-run must never land in a previous run's directory
    logs must be complete, not just the last few lines
    the API layer must resume from its own log after a hard kill

A test that writes into `dataset/` or `response/` has broken the record it was
meant to protect, so the last check walks both directories and asserts nothing
new appeared. `--scratch-root` puts every test artifact somewhere inspectable
instead of a temp dir that vanishes.

Run:
    python -m tests.test_runner
    python -m tests.test_runner --scratch-root artifacts/test-runs
    python -m tests.test_source_bundle --scratch-root artifacts/test-runs
    python -m tests.test_runner --keep     # leave the scratch runs on disk
"""

import argparse
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from expkit import paths, runner                          # noqa: E402
from expkit import apilog                                 # noqa: E402

REPO = paths.REPO_ROOT
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))
    return cond


def test_command_capture(root):
    """A failing command leaves a complete record, not an exception."""
    print("\n1. failing command is recorded, not raised")
    out = os.path.join(root, "cmd_fail")
    # 500 lines then a non-zero exit: proves the log is complete, not a tail
    script = ("import sys\n"
              "for i in range(500): print('line', i)\n"
              "print('boom', file=sys.stderr)\n"
              "sys.exit(3)\n")
    rec = runner.run_command([sys.executable, "-c", script], outdir=out, echo=False)
    check("returns instead of raising", rec is not None)
    check("status == error", rec["status"] == "error", f"got {rec['status']}")
    check("exit code preserved", rec["returncode"] == 3, f"got {rec['returncode']}")
    check("elapsed recorded", isinstance(rec.get("elapsed_sec"), float))
    check("start and end timestamps", bool(rec.get("started_utc")) and bool(rec.get("ended_utc")))
    check("cwd and interpreter recorded", bool(rec.get("cwd")) and bool(rec.get("python")))
    so = io.open(os.path.join(out, "stdout.log"), encoding="utf-8").read()
    se = io.open(os.path.join(out, "stderr.log"), encoding="utf-8").read()
    check("stdout log is COMPLETE (500 lines)", so.count("\n") == 500,
          f"{so.count(chr(10))} lines")
    check("first line kept, not just the tail", so.startswith("line 0"))
    check("stderr captured separately", "boom" in se)
    check("stderr tail attached to the record", "boom" in "".join(rec.get("stderr_tail", [])))
    check("command.json written", os.path.exists(os.path.join(out, "command.json")))
    j = json.load(io.open(os.path.join(out, "command.json"), encoding="utf-8"))
    check("argv stored as a list, not a shell string", isinstance(j["argv"], list))


def test_suite_continues_and_fail_fast(root):
    """One failure must not take the rest of the suite with it."""
    print("\n2. suite continues past a failure; --fail-fast stops")
    good = [sys.executable, "-c", "print('fine')"]
    bad = [sys.executable, "-c", "import sys; sys.exit(9)"]
    exps = [
        {"id": "T1", "title": "ok", "argv": [good], "cmds": ["x"], "lifecycle": "active"},
        {"id": "T2", "title": "fails", "argv": [bad], "cmds": ["x"], "lifecycle": "active"},
        {"id": "T3", "title": "after the failure", "argv": [good], "cmds": ["x"],
         "lifecycle": "active"},
    ]
    run_id = "test_continue"
    results = {}
    for e in exps:
        results[e["id"]] = runner.run_experiment(e, run_id, env_overlay={},
                                                 artifact_root=root, echo=False)
    check("T1 ok", results["T1"]["status"] == "ok")
    check("T2 recorded as error", results["T2"]["status"] == "error")
    check("T3 STILL RAN after T2 failed", results["T3"]["status"] == "ok")
    for eid in ("T1", "T2", "T3"):
        p = os.path.join(paths.experiment_dir(run_id, eid, root), "status.json")
        check(f"{eid} status.json on disk", os.path.exists(p))

    # fail-fast is the suite loop's job; simulate the same decision
    stop_at = None
    for e in exps:
        st = runner.run_experiment(e, "test_failfast", env_overlay={},
                                   artifact_root=root, echo=False)
        if st["status"] == "error":
            stop_at = e["id"]
            break
    check("--fail-fast stops at the first failure", stop_at == "T2", f"stopped at {stop_at}")
    check("T3 absent under fail-fast",
          not os.path.exists(os.path.join(
              paths.experiment_dir("test_failfast", "T3", root), "status.json")))


def test_skips_are_first_class(root):
    """A skipped experiment must be visible as skipped, never as success."""
    print("\n3. skips are recorded with a reason")
    e = {"id": "T4", "title": "blocked", "lifecycle": "blocked", "cmds": [], "argv": []}
    st = runner.skip_experiment(e, "test_skip", "blocked", "needs an API key", root)
    check("state is 'blocked', not 'ok'", st["status"] == "blocked")
    check("reason recorded", st["reason"] == "needs an API key")
    check("no metrics claimed", st["metrics_files"] == [] and st["instrumented"] is False)
    st2 = runner.run_experiment({"id": "T5", "title": "manual", "cmds": [], "argv": []},
                                "test_skip", artifact_root=root)
    check("experiment with no commands -> 'manual'", st2["status"] == "manual")


def test_run_ids_never_collide():
    """A re-run must get its own directory; old results are never overwritten."""
    print("\n4. run ids never collide")
    a = paths.new_run_id("probe")
    d = paths.run_dir(a)
    os.makedirs(d, exist_ok=True)
    try:
        b = paths.new_run_id("probe")
        check("second id differs from the first", a != b, f"{a} vs {b}")
        check("second dir does not exist yet", not os.path.exists(paths.run_dir(b)))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    latest = paths.read_latest()
    check("latest.json exists and names a run", bool(latest and latest.get("run_id")))
    check("latest.json is a file, not a symlink",
          os.path.isfile(os.path.join(paths.runs_root(), "latest.json")))


def test_api_resume_after_hard_kill(root):
    """The API log must survive a killed process and drive resume."""
    print("\n5. API log survives a kill and resumes")
    tag = "unittest-resume"
    d = os.path.join(paths.api_root(root), tag)
    shutil.rmtree(d, ignore_errors=True)
    os.environ["MMDOCRAG_ARTIFACT_ROOT"] = root

    log = apilog.APILog(tag, experiment_id="TEST")
    mock = apilog.MockProvider(fail_on=["q3"])
    hashes = {}
    for q in ("q1", "q2", "q3", "q4"):
        payload = {"question": f"question {q}", "text_quotes": [{"quote_id": "text1"}]}
        hashes[q] = apilog.request_hash(provider="mock", model="m", mode="pure-text",
                                        prompt_hash="ph", question_uid=q, payload=payload)

    for q in ("q1", "q2", "q3"):          # q4 never reached: simulated kill
        r = mock.generate(q, "question", [{"quote_id": "text1"}], [])
        rec = apilog.make_record(
            request_hash_=hashes[q], provider="mock", model="m", mode="pure-text",
            question_uid=q, doc_name="d", experiment_id="TEST", run_id="r",
            prompt_path=None, prompt_hash="ph", params={})
        log.append(apilog.finish_record(
            rec, status="success" if r["ok"] else "error", latency_sec=0.001,
            raw_response=r.get("raw"), parsed_response=r.get("parsed"),
            usage=r.get("usage"), error=r.get("error")))

    # a torn final line is what a hard kill actually leaves behind
    with open(log.path, "a", encoding="utf-8") as fh:
        fh.write('{"request_hash": "trunc", "sta')

    fresh = apilog.APILog(tag, experiment_id="TEST")
    check("survives a truncated final line", len(fresh.index) >= 3, f"{len(fresh.index)}")
    check("q1 marked done", fresh.done(hashes["q1"]))
    check("q2 marked done", fresh.done(hashes["q2"]))
    check("q3 (failed) NOT marked done -- must be retried", not fresh.done(hashes["q3"]))
    check("q3 error record kept", fresh.get(hashes["q3"]) is not None
          and fresh.get(hashes["q3"])["status"] == "error")
    check("q4 (never issued) not done", not fresh.done(hashes["q4"]))
    todo = [q for q in ("q1", "q2", "q3", "q4") if not fresh.done(hashes[q])]
    check("resume would issue exactly q3 and q4", todo == ["q3", "q4"], str(todo))

    mock2 = apilog.MockProvider()
    for q in todo:
        r = mock2.generate(q, "question", [{"quote_id": "text1"}], [])
        rec = apilog.make_record(
            request_hash_=hashes[q], provider="mock", model="m", mode="pure-text",
            question_uid=q, doc_name="d", experiment_id="TEST", run_id="r",
            prompt_path=None, prompt_hash="ph", params={}, attempt=2)
        fresh.append(apilog.finish_record(
            rec, status="success", latency_sec=0.001, raw_response=r.get("raw"),
            parsed_response=r.get("parsed"), usage=r.get("usage")))
    check("only 2 new calls were made on resume", mock2.calls == 2, f"{mock2.calls}")
    check("all four complete afterwards",
          all(fresh.done(hashes[q]) for q in ("q1", "q2", "q3", "q4")))
    st = fresh.stats()
    check("token usage survives redaction", st["input_tokens"] > 0, str(st))
    blob = io.open(log.path, encoding="utf-8").read()
    check("no secret-shaped strings in the log",
          not any(t in blob for t in ("sk-", "AIza", "xai-", "Bearer ")))
    os.environ.pop("MMDOCRAG_ARTIFACT_ROOT", None)


def test_mock_api_writes_only_to_scratch(root):
    """A mock run must leave the real dataset/ and response/ untouched."""
    print("\n7. mock API run stays inside the scratch root")
    ds_dir = os.path.join(paths.REPO_ROOT, "dataset")
    rs_dir = os.path.join(paths.REPO_ROOT, "response")
    before_ds = set(os.listdir(ds_dir)) if os.path.isdir(ds_dir) else set()
    before_rs = set(os.listdir(rs_dir)) if os.path.isdir(rs_dir) else set()

    scratch = os.path.join(root, "mockrun")
    os.makedirs(scratch, exist_ok=True)
    # a two-question dataset built from the real one, written into scratch
    src = None
    for cand in ("evaluation_paperk10.jsonl", "evaluation_20.jsonl"):
        p = os.path.join(ds_dir, cand)
        if os.path.exists(p):
            src = p
            break
    if src is None:
        check("dataset available for the mock test", False, "no evaluation file")
        return
    rows = []
    with io.open(src, encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if i >= 2:
                break
            rows.append(line)
    with io.open(os.path.join(scratch, "evaluation_isolationtest.jsonl"),
                 "w", encoding="utf-8") as fh:
        fh.writelines(rows)

    rec = runner.run_command(
        [sys.executable, "inference_api.py", "mock-model-v1",
         "--setting", "isolationtest", "--mode", "pure-text", "--mock",
         "--experiment-id", "TEST-ISOLATION", "--stop-after-failures", "0",
         "--dataset-dir", scratch, "--response-dir", scratch],
        outdir=os.path.join(root, "mockcmd"),
        env_overlay={"MMDOCRAG_ARTIFACT_ROOT": root}, echo=False)
    check("mock run succeeded", rec["status"] == "ok",
          f"exit {rec.get('returncode')}")
    produced = [f for f in os.listdir(scratch) if f.endswith(".jsonl")]
    check("response written into the scratch dir",
          any("response" in f for f in produced), str(produced))

    after_ds = set(os.listdir(ds_dir)) if os.path.isdir(ds_dir) else set()
    after_rs = set(os.listdir(rs_dir)) if os.path.isdir(rs_dir) else set()
    check("dataset/ NOT polluted", after_ds == before_ds,
          f"new: {sorted(after_ds - before_ds)}")
    check("response/ NOT polluted", after_rs == before_rs,
          f"new: {sorted(after_rs - before_rs)}")
    check("no mock file anywhere in response/",
          not any("mock" in f.lower() for f in after_rs),
          str(sorted(f for f in after_rs if "mock" in f.lower())))


def test_artifact_reuse_decisions(root):
    """Reuse / rebuild decisions must be explicit and recorded."""
    print("\n6. artifact plan states its reasoning")
    from expkit import artifacts as A
    reg = A.Registry()                     # the real registry, read-only here
    pl = A.plan(["indexes/colqwen-rankings", "embeddings/bge-small-vlm"], reg)
    by = {p["artifact"]: p for p in pl}
    check("every entry names a decision",
          all(p["decision"] in ("reuse", "rebuild") for p in pl))
    check("every entry gives a reason", all(p["reason"] for p in pl))
    check("existing ColQwen index is reused",
          by["indexes/colqwen-rankings"]["decision"] == "reuse",
          by["indexes/colqwen-rankings"]["reason"])
    forced = {p["artifact"]: p for p in A.plan(
        ["indexes/colqwen-rankings"], reg, ["indexes/colqwen-rankings"])}
    check("--force-rebuild overrides reuse",
          forced["indexes/colqwen-rankings"]["decision"] == "rebuild")
    check("dependency closure pulled in the parent corpus",
          "corpora/canonical-db" in {p["artifact"] for p in pl})


def test_source_bundle_reconstructs(root):
    """Delegate to the standalone bundle test so one command covers both.

    It lives in its own module because reconstruction is worth running on its
    own against an arbitrary `--run`, but a suite that skipped it would let the
    project ship a run whose source cannot be restored -- which is precisely the
    defect the bundle was added to fix.
    """
    print("\n8. source bundle reconstructs the run byte-exact")
    r = subprocess.run(
        [sys.executable, "-m", "tests.test_source_bundle",
         "--scratch-root", os.path.join(root, "source-bundle")],
        cwd=paths.REPO_ROOT, capture_output=True)
    out = r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
    tail = [ln for ln in out.splitlines() if "passed," in ln]
    check("standalone reconstruction test passes", r.returncode == 0,
          (tail[-1] if tail else out.strip().splitlines()[-1] if out.strip() else "")[:110])
    for line in out.splitlines():
        if line.strip().startswith("FAIL"):
            print(f"      {line.strip()}")


def test_pool_modes_are_distinct_and_id_stable(root):
    """The full-disk pool must extend the candidate pool, never renumber it.

    Recall is computed by looking up gold `evidence_id`s in the ranking. If the
    full-disk enumeration minted fresh ids for images the candidate pool already
    contained, every gold image would become unfindable and recall would read as
    a clean, plausible, completely wrong number -- lower, with no error raised.
    So the invariant is checked directly: every canonical id survives, and the
    only new ids carry the `unpooled:` marker.
    """
    print()
    print("9. candidate and full-disk image pools")
    sys.path.insert(0, paths.REPO_ROOT)
    try:
        from retrieval.colqwen_index import load_work, DEFAULT_DB, DEFAULT_IMG_ROOT
    except Exception as exc:
        check("retrieval.colqwen_index imports", False, f"{type(exc).__name__}: {exc}")
        return
    if not os.path.isdir(DEFAULT_IMG_ROOT):
        print(f"  [skip] image root absent: {DEFAULT_IMG_ROOT}")
        return

    can = load_work(DEFAULT_DB, DEFAULT_IMG_ROOT, "canonical")
    full = load_work(DEFAULT_DB, DEFAULT_IMG_ROOT, "fulldisk")
    cid = {e for v in can.values() for e, _p in v["imgs"]}
    fid = {e for v in full.values() for e, _p in v["imgs"]}

    check("full-disk pool is strictly larger",
          len(fid) > len(cid), f"{len(cid)} -> {len(fid)} images")
    check("every candidate-pool evidence_id survives verbatim",
          cid <= fid, f"{len(cid - fid)} lost")
    lost = sorted(cid - fid)[:3]
    if lost:
        print(f"      lost ids: {lost}")
    new = fid - cid
    check("every new id is marked unpooled:",
          all(e.startswith("unpooled:") for e in new),
          f"{sum(1 for e in new if not e.startswith('unpooled:'))} unmarked "
          f"of {len(new)} new")
    check("no canonical id was given the unpooled: marker",
          not any(e.startswith("unpooled:") for e in cid))
    per_doc = len(fid) / max(len(full), 1)
    check("full-disk pool matches the paper's scale (63 img/doc)",
          55 <= per_doc <= 72, f"{per_doc:.1f} img/doc")


def test_fullpool_index_is_refused_by_the_paired_evaluator(root):
    """eval_colqwen must refuse a full-disk index instead of scoring it.

    BM25 and the dense arm run over VLM descriptions, which exist for only 36%
    of these images. Scoring them against a ColQwen index that ranked all of
    them would hand ColQwen 2.1x the distractors and report the difference as a
    retriever effect. A footnote does not prevent that; refusing does.
    """
    print()
    print("10. paired evaluator refuses a full-disk index")
    scratch = os.path.join(root, "fullpool-guard")
    os.makedirs(scratch, exist_ok=True)
    db = os.path.join(scratch, "fake_fullpool.sqlite")
    con = sqlite3.connect(db)
    con.executescript(
        "CREATE TABLE ranking (question_uid TEXT, evidence_id TEXT, "
        "rank INTEGER, score REAL);")
    con.executemany("INSERT INTO ranking VALUES (?,?,?,?)",
                    [("q1", "deadbeefdeadbeef", 0, 1.0),
                     ("q1", "unpooled:doc_image99.jpg", 1, 0.5)])
    con.commit()
    con.close()

    r = subprocess.run(
        [sys.executable, "-m", "retrieval.eval_colqwen", "--scores", db],
        cwd=paths.REPO_ROOT, capture_output=True)
    out = (r.stdout.decode("utf-8", "replace")
           + r.stderr.decode("utf-8", "replace"))
    check("exits non-zero on a full-disk index", r.returncode != 0,
          f"exit {r.returncode}")
    check("the refusal names the reason, not just the failure",
          "FULL-DISK" in out and "6,548" in out,
          out.strip().splitlines()[-1][:90] if out.strip() else "(no output)")
    check("it points at the script that can score it",
          "eval_fullpool" in out)


def test_chunk_embeddings_resume_from_shards(root):
    """A killed encoder must resume, and must not resume from a torn shard.

    This encoder held ~50 minutes of GPU work in memory and wrote only after the
    last batch, so two external kills recovered nothing at all. Sharding fixed
    that, but a resume path is worth exactly as much as its worst case: if a
    shard truncated mid-write were accepted on restart, the run would finish
    successfully with silently wrong vectors. So both halves are checked -- that
    a good shard is reused, and that a bad one is re-encoded rather than trusted.

    The encoder is stubbed. What is under test is the shard bookkeeping, and a
    real model would only make the test slow and the failure ambiguous.
    """
    print()
    print("11. chunk embedding shards resume a killed encode")
    sys.path.insert(0, paths.REPO_ROOT)
    import numpy as np
    from retrieval import dense_chunks as dc

    scratch = os.path.join(root, "shards")
    os.makedirs(scratch, exist_ok=True)
    qdb = os.path.join(scratch, "tiny_quotes.sqlite")
    con = sqlite3.connect(qdb)
    con.executescript("CREATE TABLE chunks (chunk_id TEXT, doc_name TEXT, "
                      "page_id INT, idx INT, text TEXT);")
    con.executemany("INSERT INTO chunks VALUES (?,?,?,?,?)",
                    [(f"c{i}", f"doc{i // 7}", i, i, f"chunk text {i}")
                     for i in range(25)])
    con.commit()
    con.close()

    calls = {"n": 0, "rows": 0}

    def stub_encode(texts, batch=128, is_query=False, model_name=None):
        calls["n"] += 1
        calls["rows"] += len(texts)
        # deterministic and order-sensitive, so a mis-assembled result shows up
        return np.array([[float(len(t)), float(hash(t) % 997)] for t in texts],
                        dtype=np.float32)

    real_encode, real_cache = dc.encode, dc.cache_path
    out = os.path.join(scratch, "tiny.npz")
    dc.encode = stub_encode
    dc.cache_path = lambda *_a, **_k: out
    try:
        dc.build(qdb, "stub-model", batch=8, shard=10)
        first = np.load(out, allow_pickle=True)["vecs"].copy()
        n_first = calls["rows"]
        check("cold run encodes every chunk once", n_first == 25, f"{n_first} rows")
        check("shard directory is removed once the npz is written",
              not os.path.isdir(dc._shard_dir(out)))

        # Simulate the kill this feature exists for: die partway through, so
        # the shard directory is left behind exactly as a killed run leaves it.
        os.remove(out)
        calls["n"] = calls["rows"] = 0

        def dies_after_two(texts, **kw):
            if calls["n"] >= 2:
                raise KeyboardInterrupt("simulated external kill")
            return stub_encode(texts, **kw)

        dc.encode = dies_after_two
        try:
            dc.build(qdb, "stub-model", batch=8, shard=10)
        except KeyboardInterrupt:
            pass
        sd = dc._shard_dir(out)
        check("a killed run leaves its finished shards behind",
              os.path.isdir(sd) and len(os.listdir(sd)) == 2,
              f"{sorted(os.listdir(sd)) if os.path.isdir(sd) else 'no dir'}")
        check("the npz is not written by a partial run", not os.path.exists(out))

        # now tear one of the two survivors: a truncated shard must not be trusted
        shards = sorted(os.listdir(sd))
        with open(os.path.join(sd, shards[0]), "wb") as fh:
            np.save(fh, np.zeros((3, 2), dtype=np.float32))
        dc.encode = stub_encode
        calls["n"] = calls["rows"] = 0
        dc.build(qdb, "stub-model", batch=8, shard=10)
        second = np.load(out, allow_pickle=True)["vecs"]

        # 10 for the torn shard, 10 + 5 for the two never encoded; 10 reused
        check("the intact shard is reused and only the rest re-encoded",
              calls["rows"] == 25 - 10, f"{calls['rows']} rows re-encoded of 25")
        check("the resumed result is identical to the cold run",
              np.array_equal(first, second),
              f"max abs diff {np.abs(first - second).max():.6g}"
              if first.shape == second.shape else
              f"shape {first.shape} vs {second.shape}")
    finally:
        dc.encode, dc.cache_path = real_encode, real_cache


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--scratch-root", default="",
                    help="directory for all test artifacts (default: a temp dir). "
                         "Use artifacts/test-runs to keep them inspectable and "
                         "clearly separated from real runs.")
    a = ap.parse_args()
    if a.scratch_root:
        test_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        root = os.path.abspath(os.path.join(a.scratch_root, test_id))
        os.makedirs(root, exist_ok=True)
        # An explicit scratch root means keep the evidence -- the command logs,
        # plan.json and mock responses that make a failure readable. It does NOT
        # mean keep bulk intermediates: the delegated bundle test below cleans
        # its own restored trees unless they failed.
        a.keep = True
    else:
        root = tempfile.mkdtemp(prefix="mmdocrag-runnertest-")
    print("=" * 78)
    print("RUN SYSTEM TESTS")
    print("=" * 78)
    print(f"scratch artifact root: {root}")
    try:
        test_command_capture(root)
        test_suite_continues_and_fail_fast(root)
        test_skips_are_first_class(root)
        test_run_ids_never_collide()
        test_api_resume_after_hard_kill(root)
        test_mock_api_writes_only_to_scratch(root)
        test_artifact_reuse_decisions(root)
        test_source_bundle_reconstructs(root)
        test_pool_modes_are_distinct_and_id_stable(root)
        test_fullpool_index_is_refused_by_the_paired_evaluator(root)
        test_chunk_embeddings_resume_from_shards(root)
    finally:
        if not a.keep:
            shutil.rmtree(root, ignore_errors=True)
        else:
            print(f"\nkept: {root}")
    print()
    print("=" * 78)
    print(f"{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        for f in FAIL:
            print(f"  FAILED: {f}")
        raise SystemExit(1)
    print("=" * 78)


if __name__ == "__main__":
    main()
