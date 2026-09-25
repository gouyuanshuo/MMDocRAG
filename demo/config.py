"""Which recorded artifact each part of the demo reads, and why that one.

Every path here is an input the demo only ever *reads*. The demo has no way to
produce a number: if an artifact is missing, the affected panel says so instead
of falling back to a plausible-looking value. That rule is the whole point --
a console that silently degrades to fixtures would put invented numbers in
front of an audience under this project's name.

Two encoders appear below and they are not interchangeable:

    bge-small   the E29 generation arms were built with it (August 25), so the
                replayed answers, the candidate blocks the model actually saw,
                and the per-question routing decisions all carry it.
    bge-large   the headline retrieval numbers (E40) were re-checked on it
                after bge-small was retired as the headline encoder.

The dashboard therefore labels the encoder per row rather than claiming one
number for the project.
"""

import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _p(*parts):
    return os.path.join(REPO_ROOT, *parts)


# --- corpora and question metadata -----------------------------------------

CANONICAL_DB = _p("canonical", "mmdocrag.sqlite")
EVAL_SPLIT = "evaluation"

# The 14,826 images are outside Git. Ubuntu restoration places them under
# <repo>/images/images; the existing Windows corpus remains the default there.
# MMDOCRAG_IMAGE_ROOT can override either location. `img_path` values already
# start with "images/" relative to this root.
from expkit import paths
IMAGE_ROOT = paths.image_root()


# --- the recorded end-to-end run (E29) --------------------------------------

# Both arms answer the same 600 questions over the same 220 documents with the
# same model and prompt; only the retrieved candidate block differs. That is
# what makes the paired difference interpretable and the absolute F1 not
# comparable to any published row (gemini-3.6-flash is not in the paper's table).
ARMS = {
    "ours": dict(
        label="Nested-CV selected configuration",
        eval_jsonl=_p("dataset", "evaluation_oursk10.jsonl"),
        response_jsonl=_p(
            "response", "gemini-3.6-flash_pure-text_quotesoursk10_response.jsonl"),
        text_retriever="rrf",
        visual_retriever="rrf",
        quota=(4, 6),
        desc="RRF text + RRF image-description, quota 4/6 "
             "(the configuration nested CV selected in all five folds)",
    ),
    "paper": dict(
        label="Closest local paper-style baseline",
        eval_jsonl=_p("dataset", "evaluation_paperk10.jsonl"),
        response_jsonl=_p(
            "response", "gemini-3.6-flash_pure-text_quotespaperk10_response.jsonl"),
        text_retriever="dense",
        visual_retriever="colqwen",
        quota=(7, 3),
        desc="dense text + ColQwen visual, quota 7/3 (closest local paper-style "
             "config; NOT a reproduction of the published system)",
    ),
}
ARM_ORDER = ("ours", "paper")

GENERATION = dict(
    model="gemini-3.6-flash",
    mode="pure-text",
    k=10,
    pool="canonical",
    dense_model="BAAI/bge-small-en-v1.5",
    n_questions=600,
    n_documents=220,
    subset_manifest=_p("manifests", "e29_subset.json"),
    note="Answers are replayed from the recorded API run. The demo makes no "
         "API call and generates no new text.",
)


# --- per-question artifacts --------------------------------------------------

# Rankings for every retriever on both branches, for all 2,000 questions, from
# E27's own builder (retrieval.eval_stack_v2.build). Reconstructing an arm's
# candidate block from this table reproduces the arm files exactly, which
# tests/test_demo.py asserts -- that is what lets the demo show a page number
# and a gold flag next to a quote the generator saw.
ACTION_TABLE = _p("router", "cache", "actions_canonical_bge-small-en-v1.5.pkl")
ACTION_POOL = "canonical"
ACTION_DENSE_MODEL = "BAAI/bge-small-en-v1.5"

# E36's per-question escalation decisions, written by router/budget_router.py.
# The decisions themselves are on disk, not re-derived here: re-deriving them
# would let a tie-break difference silently swap which questions escalate.
ROUTER_DECISIONS = _p("artifacts", "e39", "20260905", "router", "per_question.csv")
E39_PLAN = _p("artifacts", "e39", "20260905", "generation", "plan.json")

# Per-question F1 for both arms, as the recorded run measured them with
# eval_all.extract_citations + get_scores. Read, never recomputed at serve time:
# tests/test_demo.py recomputes a sample through eval_all's own code path and
# asserts agreement, so the demo can serve the recorded value.
E29_PER_QUESTION = _p("artifacts", "runs", "20260905T073315Z_cached",
                      "experiments", "E29", "cmd2", "per_question.csv")


# --- metrics for the dashboard ----------------------------------------------

# The newest run that measured every experiment the dashboard shows. Named
# explicitly rather than resolved through artifacts/runs/latest.json: `latest`
# points at whatever ran last (currently an E29-only run), and a dashboard that
# silently followed it would drop most of its rows without saying so.
METRICS_RUN = os.environ.get("MMDOCRAG_METRICS_RUN", "20260905T073315Z_cached")


def metrics_path(run_id=None):
    return _p("artifacts", "runs", run_id or METRICS_RUN, "metrics.jsonl")


def run_json(run_id=None):
    return _p("artifacts", "runs", run_id or METRICS_RUN, "run.json")


# The dashboard's five groups. Each is a real comparison this project ran; the
# rows are assembled from the metrics above in demo/store.py, and every row
# carries its own n, sampling unit and interval.
GROUPS = ("end-to-end", "retrieval", "visual", "slices", "routing")

# Standing caveats, shown in the UI rather than buried in a README. Each one is
# a claim this project has already had to correct once.
CAVEATS = [
    "E27/E40 are document-grouped out-of-fold internal validation. The method "
    "space was developed on these same questions, so they are exploratory, not "
    "an untouched confirmation set.",
    "The comparator is a local paper-style baseline, not the published system: "
    "the paper pairs BGE-large-en-v1.5 with ColQwen2-v0.1, this fork runs "
    "ColQwen2-v1.0 over a different corpus and pool pipeline.",
    "BM25 or dense retrieval over VLM-written image descriptions is "
    "image-description retrieval. Only ColQwen reads pixels.",
    "Gold evidence the 8-gram mapper could not place counts as a miss. Every "
    "recall here is unconditional unless a row says conditional-on-mapped.",
    "Intervals resample documents, not questions: 2,000 questions come from "
    "220 documents and questions within a document are correlated.",
    "E29's +2.90 is quote-selection F1 -- which evidence the generator cited -- "
    "not answer correctness and not faithfulness.",
]
