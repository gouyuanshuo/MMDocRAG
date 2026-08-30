"""Build and cache the router's input features.

What a router is allowed to see
-------------------------------
The question, and the shape of the candidate set it was handed. Nothing else.
In Phase 1A.5 the evidence is already retrieved, so the candidate list is
genuinely part of the router's input -- but its *labels* are not, and neither
is anything derived from them.

Deliberately excluded:

  gold_quotes            the answer. Using it, or any count derived from it,
                         would make the router a gold detector.
  evidence_modality_type the dataset's own statement of whether the answer is
                         in text or images. Same leak, one step removed.
  doc_name, domain       properties of the document, which a real query-time
                         router does not know. They also let a model memorise
                         documents, which is precisely what the
                         document-disjoint split exists to prevent.

Included:

  question embedding     BAAI/bge-small-en-v1.5, 384-d, normalised.
  question_type          one-hot over the 8 values in the release.
  candidate-set shape    n_img, n_txt, and log-scaled character counts of the
                         text quotes and of the image descriptions. The last
                         one matters: it measures how much the pure-text arm
                         actually gets to see in place of the images.

Run:
    python -m router.features --setting 20
"""

import argparse
import os
import sqlite3
import sys

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO_ROOT, "router", "outcomes.sqlite")
EMBED_MODEL = "BAAI/bge-small-en-v1.5"

QUESTION_TYPES = ["Comparative", "Descriptive", "Interpretative", "Analytical",
                  "Inferential", "Procedural", "Causal", "Application-based"]


def load_questions(db_path, setting):
    con = sqlite3.connect(db_path)
    rows = con.execute(
        "SELECT q_id, question, question_type, n_txt, n_img, txt_chars, "
        "img_desc_chars FROM questions WHERE setting = ? ORDER BY q_id",
        (setting,)).fetchall()
    con.close()
    return rows


def shallow(rows):
    """Non-textual features: candidate-set shape, one-hot question type."""
    out = []
    for _, _, qtype, n_txt, n_img, txt_chars, desc_chars in rows:
        onehot = [1.0 if qtype == t else 0.0 for t in QUESTION_TYPES]
        out.append([
            float(n_txt), float(n_img),
            # Logs, because the character counts span two orders of magnitude
            # (61 to 22,535) and a linear model would otherwise be dominated by
            # the few enormous questions.
            np.log1p(txt_chars), np.log1p(desc_chars),
            # Ratio of description text to quote text: how much of the
            # pure-text arm's input is standing in for an image.
            np.log1p(desc_chars) - np.log1p(txt_chars),
        ] + onehot)
    return np.asarray(out, dtype=np.float32)


def embed(questions, batch=64):
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(EMBED_MODEL)
    return model.encode(questions, batch_size=batch, normalize_embeddings=True,
                        show_progress_bar=True).astype(np.float32)


def build(db_path, setting, out_path):
    rows = load_questions(db_path, setting)
    q_ids = np.asarray([r[0] for r in rows], dtype=np.int32)
    questions = [r[1] or "" for r in rows]

    emb = embed(questions)
    sh = shallow(rows)
    print(f"embeddings {emb.shape}, shallow {sh.shape}")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    np.savez_compressed(out_path, q_ids=q_ids, emb=emb, shallow=sh,
                        shallow_names=np.asarray(
                            ["n_txt", "n_img", "log_txt_chars", "log_desc_chars",
                             "log_desc_over_txt"] + [f"qtype={t}" for t in QUESTION_TYPES]),
                        embed_model=EMBED_MODEL, setting=setting)
    print(f"wrote {out_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--setting", default="20", choices=["15", "20"])
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = args.out or os.path.join(REPO_ROOT, "router",
                                   f"features_{args.setting}.npz")
    build(args.db, args.setting, out)


if __name__ == "__main__":
    main()
