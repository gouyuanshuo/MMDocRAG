"""Build the canonical evidence layer from the shipped MMDocRAG jsonl files.

Why this exists
---------------
MMDocRAG identifies evidence by a *per-question local* label: "text5",
"image7". Those labels are positions in one question's candidate list, not
identities. The same question's gold evidence carries different labels in the
15-quote and 20-quote files -- only 4.6% of questions keep the same label
strings, while 100% keep the same underlying evidence. Any join on local
labels is therefore wrong ~95% of the time.

This module resolves every quote to a stable identity derived from
(doc_name, page_id, layout_id) so that swapping the retriever, the chunking or
the top-k later still lets us score against the original gold annotations.

A second trap this guards against: q_id is only unique *within* a split. dev
and evaluation both number their questions from zero, and all 2000 evaluation
ids collide with dev ids while sharing no actual question text. Rows are
therefore keyed by (split, q_id), exposed as `question_uid`.

Run:
    python -m canonical.build                 # build + Gate 1 report
    python -m canonical.build --db out.sqlite
"""

import argparse
import collections
import hashlib
import json
import os
import sqlite3
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO_ROOT, "canonical", "mmdocrag.sqlite")

# (split, setting, path) for every shipped annotation file.
SOURCES = [
    ("evaluation", "20", "dataset/evaluation_20.jsonl"),
    ("evaluation", "15", "dataset/evaluation_15.jsonl"),
    ("dev", "20", "dataset/dev_20.jsonl"),
    ("dev", "15", "dataset/dev_15.jsonl"),
]

SCHEMA = """
DROP TABLE IF EXISTS questions;
DROP TABLE IF EXISTS question_settings;
DROP TABLE IF EXISTS canonical_evidence;
DROP TABLE IF EXISTS question_candidates;
DROP TABLE IF EXISTS question_gold_evidence;

CREATE TABLE questions (
    question_uid            TEXT PRIMARY KEY,   -- "<split>:<q_id>"
    split                   TEXT NOT NULL,
    q_id                    INTEGER NOT NULL,
    old_id                  INTEGER,            -- global id, absent for 569 dev rows
    doc_name                TEXT NOT NULL,
    domain                  TEXT,
    question                TEXT NOT NULL,
    question_type           TEXT,
    evidence_modality_type  TEXT,               -- json list, sorted (source order varies)
    answer_short            TEXT,
    has_pdf                 INTEGER              -- 1 when doc_pdfs.zip ships this document
);

-- answer_interleaved lives here, not in `questions`, because it embeds the
-- per-setting local quote numbers: the same answer cites "46%[2]" in the
-- 15-quote file and "46%[6]" in the 20-quote file. 3,890 of 4,055 questions
-- differ between settings, so the reference text BLEU/ROUGE-L scores against
-- is itself setting-dependent.
CREATE TABLE question_settings (
    question_uid        TEXT NOT NULL,
    setting             TEXT NOT NULL,          -- 15 | 20
    answer_interleaved  TEXT,
    PRIMARY KEY (question_uid, setting)
);

CREATE TABLE canonical_evidence (
    evidence_id       TEXT PRIMARY KEY,          -- sha1(doc|page|layout)[:16]
    doc_name          TEXT NOT NULL,
    page_id           INTEGER NOT NULL,          -- 0-indexed, matches the PDF page
    layout_id         INTEGER NOT NULL,
    type              TEXT NOT NULL,             -- text | image | table
    modality          TEXT NOT NULL,             -- text | image  (table renders as an image)
    text              TEXT,
    img_path          TEXT,
    img_path_aliases  TEXT,                      -- json list; 14 items ship under two names
    img_description   TEXT
);

CREATE TABLE question_candidates (
    question_uid    TEXT NOT NULL,
    setting         TEXT NOT NULL,               -- 15 | 20
    local_quote_id  TEXT NOT NULL,               -- "text5" / "image7", position-scoped
    evidence_id     TEXT NOT NULL,
    is_gold         INTEGER NOT NULL,
    PRIMARY KEY (question_uid, setting, local_quote_id)
);

CREATE TABLE question_gold_evidence (
    question_uid    TEXT NOT NULL,
    setting         TEXT NOT NULL,
    evidence_id     TEXT NOT NULL,
    local_quote_id  TEXT NOT NULL,
    PRIMARY KEY (question_uid, setting, evidence_id)
);

CREATE INDEX idx_ev_doc  ON canonical_evidence(doc_name, page_id);
CREATE INDEX idx_cand_q  ON question_candidates(question_uid, setting);
CREATE INDEX idx_gold_q  ON question_gold_evidence(question_uid, setting);
CREATE INDEX idx_q_doc   ON questions(doc_name);
"""


def evidence_id(doc_name, page_id, layout_id):
    raw = f"{doc_name}|{page_id}|{layout_id}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def pdf_doc_names(pdf_zip):
    """Document names shipped as PDFs, or None when the archive is unavailable."""
    if not pdf_zip or not os.path.exists(pdf_zip):
        return None
    import zipfile
    with zipfile.ZipFile(pdf_zip) as z:
        return {os.path.basename(n)[:-4] for n in z.namelist()
                if n.lower().endswith(".pdf")}


def load_sources(data_root):
    for split, setting, rel in SOURCES:
        path = os.path.join(data_root, os.path.basename(rel))
        if not os.path.exists(path):
            path = os.path.join(REPO_ROOT, rel)
        if not os.path.exists(path):
            raise SystemExit(f"missing annotation file: {rel}")
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield split, setting, json.loads(line)


def build(db_path, data_root, pdf_zip):
    have_pdf = pdf_doc_names(pdf_zip)

    questions = {}            # question_uid -> row
    q_settings = {}           # (question_uid, setting) -> setting-scoped row
    question_conflicts = []   # same uid described differently across settings
    evidence = {}             # evidence_id -> row
    ev_text_conflicts = []
    ev_path_aliases = collections.defaultdict(set)
    ev_type_conflicts = []
    candidates = []
    golds = []

    unresolved = []           # gold labels with no matching candidate  <- Gate 1
    label_collisions = []     # one local label naming two distinct evidence items
    duplicate_labels = []     # one local label repeated for the same evidence
    gold_total = 0

    for split, setting, rec in load_sources(data_root):
        uid = f"{split}:{rec['q_id']}"
        # Source order of evidence_modality_type varies between the two files
        # for 229 questions; sorting makes the value setting-invariant.
        modality = sorted(rec.get("evidence_modality_type", []))
        qrow = (uid, split, rec["q_id"], rec.get("old_id"), rec["doc_name"],
                rec.get("domain"), rec["question"], rec.get("question_type"),
                json.dumps(modality, ensure_ascii=False),
                rec.get("answer_short"),
                None if have_pdf is None else int(rec["doc_name"] in have_pdf))
        if uid in questions:
            # The 15- and 20-quote files repeat each question; the shared fields
            # must agree or the (split, q_id) key is not actually stable.
            if questions[uid] != qrow:
                question_conflicts.append(uid)
        else:
            questions[uid] = qrow
        q_settings[(uid, setting)] = (uid, setting, rec.get("answer_interleaved"))

        local_index = {}
        for quote in rec["text_quotes"] + rec["img_quotes"]:
            page_id, layout_id = quote["page_id"], quote["layout_id"]
            eid = evidence_id(rec["doc_name"], page_id, layout_id)
            qtype = quote.get("type") or ("text" if "text" in quote else "image")
            modality = "text" if qtype == "text" else "image"
            text = quote.get("text")
            img_path = quote.get("img_path")
            desc = quote.get("img_description")

            if eid in evidence:
                prev = evidence[eid]
                if prev["type"] != qtype:
                    ev_type_conflicts.append((eid, prev["type"], qtype))
                if modality == "text" and text is not None and prev["text"] != text:
                    ev_text_conflicts.append(eid)
                if img_path:
                    ev_path_aliases[eid].add(img_path)
            else:
                evidence[eid] = {
                    "evidence_id": eid, "doc_name": rec["doc_name"],
                    "page_id": page_id, "layout_id": layout_id,
                    "type": qtype, "modality": modality,
                    "text": text, "img_path": img_path, "img_description": desc,
                }
                if img_path:
                    ev_path_aliases[eid].add(img_path)

            # A local label is normally unique inside one candidate list, but
            # two dev questions repeat one. dev:938/image6 repeats the very
            # same evidence (harmless); dev:486/text11 labels two *different*
            # layout blocks that carry identical text. Keep the first
            # occurrence so the mapping is deterministic, and surface the
            # collision rather than resolving it silently.
            prev_eid = local_index.get(quote["quote_id"])
            if prev_eid is None:
                local_index[quote["quote_id"]] = eid
            elif prev_eid != eid:
                label_collisions.append((uid, setting, quote["quote_id"], prev_eid, eid))
            else:
                duplicate_labels.append((uid, setting, quote["quote_id"]))

        gold_labels = rec.get("gold_quotes", [])
        gold_total += len(gold_labels)
        gold_eids = set()
        for label in gold_labels:
            eid = local_index.get(label)
            if eid is None:
                unresolved.append((uid, setting, label))
                continue
            gold_eids.add(eid)
            golds.append((uid, setting, eid, label))

        for label, eid in local_index.items():
            candidates.append((uid, setting, label, eid, int(eid in gold_eids)))

    # 14 evidence items ship under two image filenames. Pick the
    # lexicographically smaller path so the choice is deterministic, and keep
    # the other under aliases rather than dropping it.
    for eid, paths in ev_path_aliases.items():
        if len(paths) > 1:
            chosen = sorted(paths)[0]
            evidence[eid]["img_path"] = chosen
            evidence[eid]["img_path_aliases"] = json.dumps(
                sorted(p for p in paths if p != chosen), ensure_ascii=False)

    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if os.path.exists(db_path):
        os.remove(db_path)
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    con.executemany("INSERT INTO questions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    list(questions.values()))
    con.executemany("INSERT INTO question_settings VALUES (?,?,?)",
                    list(q_settings.values()))
    con.executemany(
        "INSERT INTO canonical_evidence VALUES (?,?,?,?,?,?,?,?,?,?)",
        [(e["evidence_id"], e["doc_name"], e["page_id"], e["layout_id"],
          e["type"], e["modality"], e["text"], e["img_path"],
          e.get("img_path_aliases"), e["img_description"])
         for e in evidence.values()])
    con.executemany("INSERT INTO question_candidates VALUES (?,?,?,?,?)", candidates)
    con.executemany("INSERT INTO question_gold_evidence VALUES (?,?,?,?)", golds)
    con.commit()

    return {
        "db_path": db_path,
        "questions": len(questions),
        "question_settings": len(q_settings),
        "evidence": len(evidence),
        "candidates": len(candidates),
        "gold_rows": len(golds),
        "gold_total": gold_total,
        "unresolved": unresolved,
        "question_conflicts": question_conflicts,
        "ev_text_conflicts": sorted(set(ev_text_conflicts)),
        "ev_type_conflicts": ev_type_conflicts,
        "label_collisions": label_collisions,
        "duplicate_labels": duplicate_labels,
        "alias_count": sum(1 for v in ev_path_aliases.values() if len(v) > 1),
        "have_pdf": have_pdf is not None,
        "con": con,
    }


def report(stats):
    con = stats["con"]
    print("=" * 66)
    print("CANONICAL LAYER BUILD")
    print("=" * 66)
    print(f"db                  : {stats['db_path']}")
    print(f"questions           : {stats['questions']}")
    print(f"question_settings   : {stats['question_settings']}")
    print(f"canonical_evidence  : {stats['evidence']}")
    print(f"question_candidates : {stats['candidates']}")
    print(f"gold rows           : {stats['gold_rows']}")

    print()
    print("-- table shapes --")
    for split, n in con.execute(
            "SELECT split, COUNT(*) FROM questions GROUP BY split ORDER BY split"):
        print(f"  questions[{split}]      : {n}")
    for typ, n in con.execute(
            "SELECT type, COUNT(*) FROM canonical_evidence GROUP BY type ORDER BY COUNT(*) DESC"):
        print(f"  evidence[type={typ:<5}] : {n}")
    for mod, n in con.execute(
            "SELECT modality, COUNT(*) FROM canonical_evidence GROUP BY modality"):
        print(f"  evidence[{mod:<9}] : {n}")

    print()
    print("-- integrity --")
    print(f"  image path aliases resolved : {stats['alias_count']}")
    print(f"  question field conflicts    : {len(stats['question_conflicts'])}")
    print(f"  evidence text conflicts     : {len(stats['ev_text_conflicts'])}")
    print(f"  evidence type conflicts     : {len(stats['ev_type_conflicts'])}")
    print(f"  repeated local labels       : {len(stats['duplicate_labels'])} "
          f"(same evidence listed twice)")
    print(f"  ambiguous local labels      : {len(stats['label_collisions'])} "
          f"(one label, two evidence items -- first kept)")
    for row in stats['label_collisions']:
        print(f"      {row[0]} setting={row[1]} label={row[2]} kept={row[3]} dropped={row[4]}")
    if stats["have_pdf"]:
        row = con.execute(
            "SELECT SUM(has_pdf), COUNT(*) FROM questions").fetchone()
        missing_docs = [r[0] for r in con.execute(
            "SELECT DISTINCT doc_name FROM questions WHERE has_pdf=0 ORDER BY doc_name")]
        print(f"  questions with a PDF        : {row[0]}/{row[1]}")
        print(f"  documents without a PDF     : {len(missing_docs)} {missing_docs}")

    print()
    print("=" * 66)
    resolved = stats["gold_total"] - len(stats["unresolved"])
    pct = resolved / stats["gold_total"] * 100 if stats["gold_total"] else 0
    print(f"GATE 1  gold -> canonical : {resolved}/{stats['gold_total']} ({pct:.2f}%)")
    if stats["unresolved"]:
        print("  FAILED. Unresolved gold labels (first 10):")
        for row in stats["unresolved"][:10]:
            print("   ", row)
    else:
        print("  PASS")
    print("=" * 66)
    return not stats["unresolved"]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB, help="output sqlite path")
    ap.add_argument("--data-root", default=os.path.join(REPO_ROOT, "dataset"),
                    help="directory holding the *_15/_20 jsonl files")
    ap.add_argument("--pdf-zip", default=r"D:\Dataset\MMDocRAG\doc_pdfs.zip",
                    help="doc_pdfs.zip, used to flag which questions have a PDF")
    ap.add_argument("--no-manifest", action="store_true")
    args = ap.parse_args()

    stats = build(args.db, args.data_root, args.pdf_zip)
    ok = report(stats)

    if not args.no_manifest:
        sys.path.insert(0, REPO_ROOT)
        import manifest
        out = manifest.write(
            "canonical/build",
            data_files=[os.path.join(REPO_ROOT, rel) for _, _, rel in SOURCES],
            extra={"db": args.db, "pdf_zip": args.pdf_zip},
            results={k: v for k, v in stats.items()
                     if k in ("questions", "evidence", "candidates", "gold_rows",
                              "gold_total", "alias_count")}
            | {"gate1_pass": ok, "unresolved": len(stats["unresolved"])},
        )
        print("manifest:", os.path.relpath(out, REPO_ROOT))

    stats["con"].close()
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
