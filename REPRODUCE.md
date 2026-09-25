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


## Current workspace: one command (2026-09-05)

```powershell
python reproduce.py --dry-run
python reproduce.py
```

Runs all four required test suites, then **37 cached experiments**, then checks
E24/E27 against that exact run. This includes E29 saved API responses, E34 saved
full-pool rankings, the previously omitted phase-3 evaluations, and the new E41
OOF comparison-family audit. It makes **zero API requests**, downloads no models,
and does not re-encode embeddings. CPU routing fits are still recomputed when
their checked caches do not match the source/input/configuration hashes.

```powershell
python reproduce.py --only E29 --skip-tests
python reproduce.py --skip-tests --resume <cached_run_id>
```

Pass the same `--only` list when resuming a restricted run. Resume rejects changed
sources, inputs or options. Successful commands have checkpoints; failures and
missing inputs return nonzero. Logs go to `artifacts/logs/reproduce_*.log` and the
run report to `artifacts/runs/<run_id>/summary.html`. Every run records its size.
E41 must run after both E27 and E40 in the same run; `--only E27,E40,E41` is valid.

This is **recomputation from this workspace's saved data**, not a claim that a
fresh clone contains all paid generations, PDFs, images and model weights.
Read the [plain-language research status](docs/research-status.html) before
interpreting recall or quote F1 as answer correctness.

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

They are regenerable from the JSONL data in the clone **plus the PDF archive,
cropped images and model weights outside Git**. The 2026-09-25 migration package
preserves the existing derived bytes instead. If you ask for an experiment whose
inputs are missing, the artifact layer refuses with the exact command that
builds them rather than running on absent inputs.

## 2. Setup

For a clone restored from the 2026-09-25 Windows workspace, follow
[`docs/UBUNTU_MIGRATION.md`](docs/UBUNTU_MIGRATION.md) first. It names the
off-repository archives, checksums, exact Ubuntu extraction paths and the
separate ColQwen environment. The commands below describe the original Windows
environment and are **not** an Ubuntu cold-start validation.

```powershell
git clone git@github.com:gouyuanshuo/MMDocRAG.git
cd MMDocRAG
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install torch==2.6.0+cu124 --index-url https://download.pytorch.org/whl/cu124
python -m pip install -r requirements.txt
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

To force a derived artifact and its selected downstream dependencies to rebuild:

```bash
python experiments.py run-suite full-local --include-expensive --force-rebuild corpora/canonical-db
```

The dependency plan is now actually executed (fixed 2026-09-05). Explicit
rebuilds keep replaced derived files under `artifacts/derived/rebuild-backups/`
with a size record; inspect those backups before deliberately cleaning them.
`--force-rebuild` is rejected in replay/cached suites.

A complete cold build has **not** been validated in this audit. Supply the PDFs
as well as cropped images. Builders use the existing `D:\Dataset\MMDocRAG`
directory on this Windows machine and `<repo>/data` plus `<repo>/images` on
Ubuntu; `MMDOCRAG_DATA_ROOT` and `MMDOCRAG_IMAGE_ROOT` override these defaults.
See the [Ubuntu migration guide](docs/UBUNTU_MIGRATION.md) for the exact layout.
An offline rebuild requires model weights already present. `full-local` also does not
magically regenerate paid API responses. The granularity-sweep chunk databases
must be prepared separately if absent:

```powershell
foreach ($chunkSize in 100,600,1200,2400) {
  python -m retrieval.quote_corpus --target-chars $chunkSize --no-gold-map --out "retrieval/quotes_t$chunkSize.sqlite"
}
```

Keep the existing 300-character database at `retrieval/quotes.sqlite`.

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

## 4b. Looking at it instead of running it

```bash
cd webui && npm install && npm run build     # once
python -m demo.server                        # http://127.0.0.1:8000
```

A browsable console over the same artifacts: replayed end-to-end answers with
their evidence, the two retrieval arms side by side, and the recorded metrics
with their intervals. The front end is a group-mate's interface
([kosuzu123/Multimodal-rag-UI](https://github.com/kosuzu123/Multimodal-rag-UI))
rewired to this backend.

It **reads** artifacts and nothing else — no model call, no retrieval, no metric
recomputed at serve time — so it is only ever as good as the run it points at,
and it says which run that is on every screen. Missing inputs show as missing.
`demo/README.md` lists what it needs and what to do when a panel is empty.

## 5. What you cannot reproduce from this clone

Honest list:

| | Why |
|---|---|
| **E34** (full pool) | Cached evaluation is offline and included in `cached`; rebuilding the index needs GPU + `.venv-colpali`. The local saved index covers 220 documents. |
| **E29** | Cached scoring is offline and included in `cached`. New generation needs a provider key and budget; old paid responses must be restored separately when absent. |
| **E39** | Correct GPU inputs prepared under `artifacts/e39/20260905/`; new generation pending model, thinking, budget and noninferiority-margin decisions. |
| **E22** | manual verification of four papers, deliberately not automated |
| **E31 / E32 / E33** | they *are* the run system, not experiments over data |

## 6. Tests

```bash
python -m tests.test_runner --scratch-root artifacts/test-runs   # 67
python -m tests.test_source_bundle --scratch-root artifacts/test-runs  # 25
python -m tests.test_statistics                                  # 30
python -m tests.test_phase3                                      # 35
python -m tests.test_demo                                        # 48, the console
```

All four passed after the 2026-09-05 reconstruction fix (157 assertions total).
The earlier closing run failed on LF/CRLF patch preimages; see
`docs/RESEARCH_STATUS.md` for the retained failure and final validation records.
`test_statistics` is the one to read
first if you intend to trust any interval in this repository: it pins that the
bootstrap resamples **documents, not questions**, because the 2,000 questions
come from 220 documents and resampling questions understates every interval.

## 7. Reading the results critically

Three things the numbers do not say on their own, all documented at length in
`docs/HANDOFF.md`:

- The comparator is a **local paper-style baseline**, not the published system.
  Appendix C.3 Table 14 specifies BGE-large-en-v1.5 and ColQwen2-v0.1.
  The local visual checkpoint is v1.0, and the corpus/pool pipeline also differs.
  The old claim that the paper gives no model versions is retracted; see
  [the source audit](docs/2026-09-05-paper-appendix-correction.md). E34 measured this: restoring the full image
  pool moves recall@10 from 0.820 to 0.782, but the paper's 0.708 stays outside
  the interval at every k, so pool size explains only about a third of the gap.
- BM25 and dense retrieval over VLM-written image descriptions is
  **image-description retrieval**, never "visual retrieval" — no pixels are read.
- The test split has been observed repeatedly and used to select methods.
  E27/E40 use document-grouped out-of-fold selection, but their method space
  was developed on the same data. They are internal validation, not an untouched
  confirmatory set. Slice results and E41's post-hoc family audit remain exploratory.
