# Reproducing this fork's experiments

This is a fork of [MMDocRAG/MMDocRAG](https://github.com/MMDocRAG/MMDocRAG). The
upstream benchmark is unchanged; everything this fork adds sits on top of
`2fd7505` as a linear series of commits on the default branch,
`phase3-query-conditioned-routing`.

The authoritative record is **not** this file:

| Where | What |
|---|---|
| `docs/HANDOFF.md` | the project map — every experiment, every lesson, every known limit |
| `docs/lab-notebook.html` | the running lab notebook, entry per experiment |
| `python experiments.py list` | the registry: id, phase, status, suite, what it costs |
| `python experiments.py show E27` | one experiment's design, result, corrections and argv |

This file only answers one question: **what do I have to do, starting from a
fresh clone, before those commands produce numbers?**

## 1. The thing that will bite you first

A fresh clone **cannot** run the replay suite. `run-suite replay` recomputes
metrics from derived artifacts it does not rebuild — and those artifacts are
deliberately not in Git, because they are ~800 MB of vectors and databases:

| Not in the clone | Size |
|---|---|
| `retrieval/embeddings/` | 641 MB |
| `retrieval/quotes.sqlite` | 57 MB |
| `canonical/mmdocrag.sqlite` | 48 MB |
| `router/outcomes.sqlite` | 45 MB |
| `retrieval/colqwen_scores.sqlite` | 8.6 MB |

They are all regenerable from data that *is* in the clone, plus the image set
below. If you ask for an experiment whose inputs are missing, the artifact
layer refuses with the exact command that builds them rather than running on
absent inputs.

## 2. Setup

```bash
git clone git@github.com:gouyuanshuo/MMDocRAG.git
cd MMDocRAG
python -m venv .venv && . .venv/Scripts/activate   # Python 3.13.7 on Windows
pip install -r requirements.txt
```

Then fetch the image quotes, which are not in Git (see `images/README.md`):
download [`images.zip`](https://huggingface.co/datasets/MMDocIR/MMDocRAG/blob/main/images.zip)
and unzip it into `images/` — 14,826 JPEGs.

ColQwen needs a **second** environment: `colpali-engine` requires
transformers >= 5, while the main environment is pinned at 4.57.3. Create
`.venv-colpali` for it. Only the ColQwen indexing step uses it, and only that
step needs a GPU.

## 3. Building the derived artifacts

```bash
python experiments.py run-suite full-local --offline --include-expensive
```

Hours, not minutes. It builds the corpora, embeddings and rankings, then runs
the 29 experiments that depend on them. Add `--dry-run` first to see the plan:
every dependency is printed with a reuse / rebuild decision and the reason.

To rebuild one artifact only:

```bash
python experiments.py run-suite full-local --include-expensive --force-rebuild corpora/canonical-db
```

## 4. Once the artifacts exist

```bash
python experiments.py run-suite replay --offline        # 7 experiments, metrics only
python experiments.py run-suite retrieval --offline     # 23 experiments
python experiments.py verify E24 --run <replay_run_id>  # assert the contested numbers
python experiments.py verify E27 --run <replay_run_id>
```

`verify` defaults to the latest run, which is usually a single experiment — pass
`--run` explicitly or you will get FAILs that mean "this run never measured
that", not "the number moved".

Every `run-suite` also reconstructs its own source tree from
`artifacts/runs/<id>/source_bundle.zip` and rechecks a SHA-256 per source file,
so a run that claims a result also proves which bytes produced it.

## 5. What you cannot reproduce from this clone

Honest list:

| | Why |
|---|---|
| **E34** (full pool) | GPU + `.venv-colpali`, ~2.5 h to index 220 documents |
| **E29** | `run-suite api --allow-api` — costs money, needs a Gemini key |
| **E39** | never run; registered `blocked` pending budget approval |
| **E22** | manual verification of four papers, deliberately not automated |
| **E31 / E32 / E33** | they *are* the run system, not experiments over data |

## 6. Tests

```bash
python -m tests.test_runner --scratch-root artifacts/test-runs   # 64
python -m tests.test_source_bundle --scratch-root artifacts/test-runs  # 19
python -m tests.test_statistics                                  # 25
python -m tests.test_phase3                                      # 33
```

All four pass at the head of this branch. `test_statistics` is the one to read
first if you intend to trust any interval in this repository: it pins that the
bootstrap resamples **documents, not questions**, because the 2,000 questions
come from 220 documents and resampling questions understates every interval.

## 7. Reading the results critically

Three things the numbers do not say on their own, all documented at length in
`docs/HANDOFF.md`:

- The comparator is a **local paper-style baseline**, not the published system.
  The paper names no retriever version, so its configuration cannot be
  reproduced from the publication. E34 measured this: restoring the full image
  pool moves recall@10 from 0.820 to 0.782, but the paper's 0.708 stays outside
  the interval at every k, so pool size explains only about a third of the gap.
- BM25 and dense retrieval over VLM-written image descriptions is
  **image-description retrieval**, never "visual retrieval" — no pixels are read.
- The test split has been observed repeatedly and used to select methods.
  Apart from the out-of-fold, document-grouped result in E27, the slice-level
  findings are **exploratory**, not confirmatory.
