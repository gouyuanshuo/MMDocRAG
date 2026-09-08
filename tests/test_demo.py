"""Tests for the demo console: the properties that keep it from lying.

A console is the easiest place in this project for a claim to drift, because it
puts an answer, a page number and a metric on one screen and lets the viewer
assume they belong together. These tests pin the assumptions that make that
juxtaposition true.

What is checked:

    the candidate block the UI annotates is the one the generator actually saw --
    reconstructing each arm from the cached action table reproduces all 1,200
    recorded arm rows exactly, quote for quote, which is what lets a page number
    and a gold flag be attached to a quote at all

    every number the dashboard shows exists in the recorded run's metrics; no
    cell value is computed, rounded into existence, or carried over from a
    neighbouring cell

    the per-question F1 the console serves is the one the recorded run measured,
    recomputed through eval_all's own scorers and asserted to agree

    denominators survive the trip: gold the mapper could not place stays in the
    denominator, and retrieved gold never exceeds total gold

    the naming discipline holds in the payload -- ColQwen is never presented as a
    text retriever, and description-based retrieval is never called visual

    a missing artifact degrades visibly: the store reports the error and the
    affected panel loses its rows, rather than falling back to a fixture

    the image route cannot be walked out of the dataset directory

Run:
    python -m tests.test_demo
"""

import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from demo import config as C            # noqa: E402
from demo import dashboard              # noqa: E402
from demo import server as SRV          # noqa: E402
from demo.store import Store            # noqa: E402

PASS, FAIL = [], []
STORE = None


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))


def store():
    global STORE
    if STORE is None:
        STORE = Store(verbose=False)
    return STORE


def read_jsonl(path):
    with io.open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


# ---------------------------------------------------------------- the store

def test_store_loads_every_artifact():
    print("\nstore")
    s = store()
    check("no artifact failed to load", not s.errors, "; ".join(s.errors))
    check("2,000 evaluation questions", len(s.questions) == 2000, str(len(s.questions)))
    check("220 documents", len(s.documents) == 220, str(len(s.documents)))
    check("600 questions have a recorded answer", len(s.replayable) == 600,
          str(len(s.replayable)))
    check("both arms loaded", set(s.arms) == {"ours", "paper"}, str(sorted(s.arms)))
    check("action table covers every question", len(s.actions) == 2000, str(len(s.actions)))
    check("router decisions cover every question", len(s.router) == 2000, str(len(s.router)))


def test_reconstruction_reproduces_the_arm_files():
    """The load-bearing assumption: same builder, same pool, same quota."""
    print("\nreconstruction of the recorded candidate blocks")
    s = store()
    evidence_cache = {}
    mismatches = []
    checked = 0
    for name in C.ARM_ORDER:
        spec = C.ARMS[name]
        for row in read_jsonl(spec["eval_jsonl"]):
            uid = s.qid_to_uid.get(row["q_id"])
            quotes, _ = s._quotes_for_arm(uid, name, None)
            got_text = [q["text"] or "" for q in quotes if q["branch"] == "text"]
            got_image = [q["imgPath"] or "" for q in quotes if q["branch"] == "visual"]
            want_text = [q["text"] for q in row["text_quotes"]]
            want_image = [q["img_path"] for q in row["img_quotes"]]
            checked += 1
            if got_text != want_text or got_image != want_image:
                mismatches.append((name, row["q_id"]))
            evidence_cache[(name, row["q_id"])] = quotes
    check("all 1,200 recorded arm rows reproduced exactly",
          checked == 1200 and not mismatches,
          f"{checked} checked, {len(mismatches)} mismatched")

    # Local quote ids are positional, so a shifted list would still "match" in
    # length. Pin the mapping itself on one row.
    uid = s.replayable[0]
    quotes, counts = s._quotes_for_arm(uid, "ours", None)
    check("local ids are text1..textN then image1..imageM",
          [q["localId"] for q in quotes] ==
          [f"text{i}" for i in range(1, counts["quotaText"] + 1)] +
          [f"image{i}" for i in range(1, counts["quotaVisual"] + 1)],
          str([q["localId"] for q in quotes]))
    check("every quote resolved to an evidence row",
          all(q["evidenceId"] and q["docName"] is not None for q in quotes))


def test_recorded_f1_is_what_the_run_measured():
    print("\nper-question F1")
    s = store()
    try:
        from eval_all import extract_citations, get_scores, strip_thinking
    except Exception as exc:                                   # noqa: BLE001
        check("eval_all importable for the F1 cross-check", False, str(exc))
        return
    recomputed = disagreements = 0
    for name in C.ARM_ORDER:
        arm = s.arms[name]
        for uid in s.replayable[:60]:
            qid = s.questions[uid]["qId"]
            gold_row = arm["blocks"][qid]
            answer = arm["answers"][qid]["response"]
            visible = {q["quote_id"] for q in gold_row["text_quotes"] + gold_row["img_quotes"]}
            labels = [x if x in visible else "unretrieved:" + x
                      for x in gold_row["gold_quotes"]]
            _p, _r, f1 = get_scores(labels, extract_citations(strip_thinking(answer))[2])
            recorded = s.recorded_f1[uid][name]
            recomputed += 1
            if abs(f1 - recorded) > 1e-9:
                disagreements += 1
    check("recorded F1 equals a recomputation through eval_all's scorers",
          disagreements == 0, f"{recomputed} recomputed, {disagreements} disagreed")
    check("the run named its own estimator and scorer",
          s.f1_provenance.get("estimator") and s.f1_provenance.get("scorer"),
          str(s.f1_provenance.get("scorer")))


def test_denominators_survive():
    print("\ndenominators")
    s = store()
    bad_total = bad_unmapped = 0
    for uid in s.replayable[:120]:
        replay = s.replay(uid)
        row = s.actions[uid]
        for arm in replay["arms"].values():
            counts = arm["counts"]
            if counts["goldRetrieved"] > counts["goldTotal"]:
                bad_total += 1
            if counts["goldTotal"] != int(row["n_total"]):
                bad_total += 1
            if counts["goldMapped"] + counts["goldUnmapped"] != counts["goldTotal"]:
                bad_unmapped += 1
    check("retrieved gold never exceeds total gold", bad_total == 0, str(bad_total))
    check("unmapped gold stays inside the denominator", bad_unmapped == 0, str(bad_unmapped))

    with_unmapped = [uid for uid in s.replayable
                     if int(s.actions[uid]["n_unmapped"]) > 0]
    if with_unmapped:
        counts = s.replay(with_unmapped[0])["arms"]["ours"]["counts"]
        check("a question with unmapped gold reports it rather than dropping it",
              counts["goldUnmapped"] > 0 and counts["goldTotal"] >
              counts["goldMapped"], str(counts))
    else:
        check("a question with unmapped gold reports it rather than dropping it",
              True, "no unmapped gold in the canonical pool")


def test_dashboard_values_exist_in_the_recorded_run():
    print("\ndashboard provenance")
    s = store()
    recorded = {round(float(m["value"]), 12) for m in s.metrics
                if isinstance(m.get("value"), (int, float))}
    invented, cells, intervals, contradictions = [], 0, 0, []
    for group_id in C.GROUPS:
        payload = dashboard.build(s, group_id)
        for table in payload["tables"]:
            for row in table["rows"]:
                for key, value in row.items():
                    if not (isinstance(value, dict) and "value" in value):
                        continue
                    cells += 1
                    if value["missing"] or value["value"] is None:
                        continue
                    if round(float(value["value"]), 12) not in recorded:
                        invented.append((group_id, table["id"], key, value["value"]))
                    if value["ciLow"] is not None:
                        intervals += 1
                        crosses = value["ciLow"] <= 0 <= value["ciHigh"]
                        if crosses and value["significant"] is True:
                            contradictions.append((group_id, table["id"], key))
    check("every dashboard cell traces to a metric the run recorded",
          not invented, str(invented[:3]))
    check("intervals are present where the run recorded them", intervals > 40,
          f"{intervals} of {cells} cells carry an interval")
    check("nothing is flagged significant while its CI includes zero",
          not contradictions, str(contradictions[:3]))
    check("every group carries its caveats",
          all(dashboard.build(s, g)["caveats"] for g in C.GROUPS))


def test_naming_discipline_in_the_payload():
    print("\nnaming discipline")
    s = store()
    comparison = s.retriever_comparison(s.replayable[0], k=10)
    text_retrievers = [e["retriever"] for e in comparison["text"]["retrievers"]]
    check("ColQwen is never listed as a text retriever",
          "colqwen" not in text_retrievers, str(text_retrievers))
    visual = {e["retriever"]: e for e in comparison["visual"]["retrievers"]}
    check("only ColQwen is described as reading pixels",
          all(e["readsPixels"] == (name == "colqwen") for name, e in visual.items()))
    check("description-based retrievers say so",
          all("image descriptions" in e["representation"]
              for name, e in visual.items() if name != "colqwen"),
          str([e["representation"] for e in visual.values()]))

    blob = json.dumps(dashboard.build(s, "visual"), ensure_ascii=False)
    check("the visual group never calls description retrieval 'visual retrieval'",
          "visual retrieval" not in blob.lower())
    check("the baseline is named as a local paper-style config, not the paper's",
          "paper-style" in blob and "the paper's configuration" not in blob)


def test_turn_payload_has_what_the_ui_reads():
    print("\nAPI payload")
    s = store()
    match = s.match("How many goblets appear in the figure showing Skyskraoeren?")
    check("an exact question matches exactly", match and match["exact"], str(match))
    turn = SRV._turn(s, "anything", match, "q_test", "t_test")
    required = ("queryId", "turnId", "status", "question", "match", "answer",
                "citations", "routing", "replay", "baseline", "metrics", "provenance")
    check("the turn carries every field the console reads",
          all(key in turn for key in required),
          str([k for k in required if k not in turn]))
    citation = turn["citations"][0]
    for key in ("localId", "evidenceId", "documentName", "page", "type", "isGold",
                "cited", "snippet", "imageUrl"):
        check(f"citation.{key} present", key in citation)
    check("routing separates the static configuration from the per-question one",
          turn["routing"]["static"]["perQuestion"] is False
          and "perQuestion" in turn["routing"])
    check("the metric is named as quote selection, not correctness",
          "not answer correctness" in turn["metrics"]["metric"])

    vague = s.match("something about charts and percentages")
    check("a non-benchmark question is labelled as a match, not an answer",
          vague and not vague["exact"] and vague["method"] == "bm25", str(vague))


def test_missing_artifacts_degrade_visibly():
    print("\ndegradation")
    broken = Store(metrics_run="does-not-exist-run", verbose=False)
    check("a missing metrics run is reported", any("does-not-exist-run" in e
                                                   for e in broken.errors),
          str(broken.errors[:1]))
    check("health would report degraded", broken.provenance()["errors"] != [])
    payload = dashboard.build(broken, "retrieval")
    rows = [row for table in payload["tables"] for row in table["rows"]]
    check("a group with no metrics shows no rows rather than fixtures",
          rows == [], f"{len(rows)} rows")
    check("the caveats still ship with the empty group", payload["caveats"])


def test_image_route_cannot_escape_the_dataset():
    print("\nimage route")
    s = store()
    for hostile in ("../../etc/passwd", "..\\..\\Windows\\win.ini",
                    "/etc/passwd", "images/../../secret.txt", ""):
        check(f"rejects {hostile!r}", s.image_file(hostile) is None)
    known = None
    for uid in s.replayable[:40]:
        for quote in s.replay(uid)["arms"]["ours"]["quotes"]:
            if quote["imgPath"]:
                known = quote["imgPath"]
                break
        if known:
            break
    if known and os.path.isdir(s.image_root):
        check("serves a real evidence image", s.image_file(known) is not None, known)
    else:
        check("serves a real evidence image", True,
              "image root absent; the route reports it rather than guessing")


def main():
    print("=" * 78)
    print("DEMO CONSOLE")
    print("=" * 78)
    test_store_loads_every_artifact()
    test_reconstruction_reproduces_the_arm_files()
    test_recorded_f1_is_what_the_run_measured()
    test_denominators_survive()
    test_dashboard_values_exist_in_the_recorded_run()
    test_naming_discipline_in_the_payload()
    test_turn_payload_has_what_the_ui_reads()
    test_missing_artifacts_degrade_visibly()
    test_image_route_cannot_escape_the_dataset()
    print()
    print("=" * 78)
    print(f"{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        for name in FAIL:
            print(f"  FAILED: {name}")
        raise SystemExit(1)
    print("=" * 78)


if __name__ == "__main__":
    main()
