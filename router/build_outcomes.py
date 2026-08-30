"""Per-question outcomes for every model that has both generation-input modes.

Phase 1A.5 asks a question that needs no API budget and no retrieval: the
evidence is already given, so should each image be handed to the model as a
real image (multimodal) or as its text description (pure-text)?

The benchmark ships paired pure-text / multimodal responses for the same 2000
evaluation questions, so the counterfactual "what would the other mode have
scored on this question" is already on disk. This module turns those files into
a per-question table -- the raw material for oracle labels, router training and
the quality/cost Pareto.

Scoring goes through eval_all.strip_thinking / extract_citations / get_scores,
i.e. the benchmark's own implementation. Re-deriving F1 with a private copy
would silently drift from the published numbers.

Run:
    python -m router.build_outcomes --setting 20
    python -m router.build_outcomes --setting 15 --setting 20
"""

import argparse
import collections
import json
import os
import sqlite3
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eval_all import strip_thinking, extract_citations, get_scores  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO_ROOT, "router", "outcomes.sqlite")

SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
    setting        TEXT    NOT NULL,
    q_id           INTEGER NOT NULL,
    doc_name       TEXT,
    domain         TEXT,
    question       TEXT,
    question_type  TEXT,
    -- candidate-set shape. Available to a router at inference time: the
    -- candidate list is the input, only the gold labels are hidden.
    n_txt          INTEGER,
    n_img          INTEGER,
    txt_chars      INTEGER,
    img_desc_chars INTEGER,
    -- label side. ANALYSIS ONLY -- never a router feature, it leaks the answer.
    n_gold         INTEGER,
    n_gold_txt     INTEGER,
    n_gold_img     INTEGER,
    PRIMARY KEY (setting, q_id)
);

CREATE TABLE IF NOT EXISTS outcomes (
    model     TEXT    NOT NULL,
    mode      TEXT    NOT NULL,
    setting   TEXT    NOT NULL,
    q_id      INTEGER NOT NULL,
    precision REAL,
    recall    REAL,
    f1        REAL,
    n_pred    INTEGER,
    in_tok    INTEGER,
    out_tok   INTEGER,
    PRIMARY KEY (model, mode, setting, q_id)
);

CREATE INDEX IF NOT EXISTS idx_outcomes_q ON outcomes (setting, q_id, mode);
"""


def discover(response_dir, setting):
    """Map a case-normalised model name to its available {mode: filename}.

    File naming is inconsistent in the release: the same checkpoint appears as
    `internvl3-38B_pure-text` and `Internvl3-38b_multimodal`. Matching on the
    exact string would drop five InternVL3 pairs, so names are lowercased. The
    `pure-text_ocr` arm is a different experiment (OCR'd text instead of image
    descriptions) and is excluded here.
    """
    suffix = f"_quotes{setting}_response.jsonl"
    found = collections.defaultdict(dict)
    for name in sorted(os.listdir(response_dir)):
        if not name.endswith(suffix):
            continue
        stem = name[: -len(suffix)]
        for mode in ("multimodal", "pure-text_ocr", "pure-text"):
            if stem.endswith("_" + mode):
                model = stem[: -len(mode) - 1].lower()
                if mode == "pure-text_ocr":
                    break
                if mode in found[model]:
                    print(f"[warn] {model}/{mode}: two files differ only by case, "
                          f"keeping {found[model][mode]}, ignoring {name}")
                    break
                found[model][mode] = name
                break
    return found


def load_responses(path):
    rows = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rec = json.loads(line)
                rows.setdefault(rec["q_id"], rec)
    return rows


def score_file(gold_idx, path, model, mode, setting):
    responses = load_responses(path)
    out, missing = [], 0
    for q_id, gold in gold_idx.items():
        rec = responses.get(q_id)
        if rec is None:
            missing += 1
            continue
        answer = strip_thinking(rec.get("response"))
        _, _, pred = extract_citations(answer)
        p, r, f1 = get_scores(gold["gold_quotes"], pred)
        out.append((model, mode, setting, q_id, p, r, f1, len(pred),
                    rec.get("in_tok"), rec.get("out_tok")))
    return out, missing


def question_rows(gold_data, setting):
    rows = []
    for g in gold_data:
        gold = g["gold_quotes"]
        rows.append((
            setting, g["q_id"], g.get("doc_name"), g.get("domain"),
            g.get("question"), g.get("question_type"),
            len(g["text_quotes"]), len(g["img_quotes"]),
            sum(len(t.get("text") or "") for t in g["text_quotes"]),
            sum(len(i.get("img_description") or "") for i in g["img_quotes"]),
            len(gold),
            sum(1 for x in gold if x.startswith("text")),
            sum(1 for x in gold if x.startswith("image")),
        ))
    return rows


def build(settings, response_dir, dataset_dir, db_path):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)

    for setting in settings:
        gold_path = os.path.join(dataset_dir, f"evaluation_{setting}.jsonl")
        with open(gold_path, encoding="utf-8") as fh:
            gold_data = [json.loads(l) for l in fh if l.strip()]
        gold_idx = {g["q_id"]: g for g in gold_data}
        con.executemany(
            "INSERT OR REPLACE INTO questions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            question_rows(gold_data, setting))

        found = discover(response_dir, setting)
        paired = sorted(m for m, v in found.items()
                        if "pure-text" in v and "multimodal" in v)
        single = sorted(set(found) - set(paired))
        print(f"\n=== setting {setting}: {len(gold_idx)} gold questions ===")
        print(f"paired models (both modes): {len(paired)}")
        print(f"single-mode models        : {len(single)}  (scored too, "
              f"but cannot contribute a routing label)")

        total_missing = 0
        for model in sorted(found):
            for mode, fname in sorted(found[model].items()):
                rows, missing = score_file(
                    gold_idx, os.path.join(response_dir, fname), model, mode, setting)
                total_missing += missing
                if missing:
                    print(f"[warn] {model}/{mode}: {missing} question(s) absent "
                          f"from the response file, excluded")
                con.executemany(
                    "INSERT OR REPLACE INTO outcomes VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
        con.commit()
        print(f"scored rows written; {total_missing} question(s) missing overall")

    n_q = con.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    n_o = con.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0]
    print(f"\ndb: {db_path}\nquestions {n_q}, outcome rows {n_o}")
    con.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--setting", action="append", choices=["15", "20"],
                    help="repeatable; default is both")
    ap.add_argument("--response-dir", default=os.path.join(REPO_ROOT, "response"))
    ap.add_argument("--dataset-dir", default=os.path.join(REPO_ROOT, "dataset"))
    ap.add_argument("--db", default=DEFAULT_DB)
    args = ap.parse_args()
    build(args.setting or ["15", "20"], args.response_dir, args.dataset_dir, args.db)


if __name__ == "__main__":
    main()
