# Working in this repository

Instructions for coding agents (Claude Code, Codex, Cursor, …) and for the
humans reviewing what they produce. `CLAUDE.md` imports this file, so there is
one copy to keep current.

This is a fork of the MMDocRAG benchmark. Everything the research adds sits on
`phase3-query-conditioned-routing`. **Read `docs/HANDOFF.md` before changing
anything** — this file is the short list of rules; that one is the map.

| Question | Where the answer lives |
|---|---|
| What has been done, and what is still open? | `docs/HANDOFF.md` §0, §2, §4 |
| What went wrong before? | `docs/HANDOFF.md` §5 — the most valuable section |
| What did experiment N conclude? | `python experiments.py show E27` |
| What is the state of every experiment? | `python experiments.py list` |
| How do I run anything from a fresh clone? | `REPRODUCE.md` |
| Why is this artifact in / out of Git? | `docs/artifacts-git-policy.md` |

## Claims discipline — the rules that produce wrong papers when broken

Every one of these was broken here at least once and cost real work.

1. **Resample the sampling unit.** The 2,000 questions come from 220
   documents, and questions within a document are highly correlated.
   Bootstrap **documents**, not questions, with a ratio-of-sums estimator.
   Report the point estimate, the 95% CI, and the number of documents.
   `tests/test_statistics.py` pins this: clustering widens the interval from
   0.0118 to 0.0446 under a document effect.
2. **Never change a denominator silently.** Gold evidence that cannot be
   mapped counts as a **miss** in unconditional recall. A figure computed only
   over the mappable subset must be named *conditional-on-mapped recall*.
   Print QA / gold / mapped / dropped counts on every evaluation.
3. **A CI whose lower bound touches zero is not significant.** Say so plainly,
   and declare the comparison family when testing several k or systems —
   Holm-Bonferroni over a family fixed *before* looking.
4. **Select first, slice second.** Slicing must never re-run selection; see
   `retrieval/slice_by_type.py`, which consumes `nested_cv`'s out-of-fold
   predictions rather than reselecting inside each slice.
5. **A split you have observed repeatedly is exploratory.** Only E27's
   out-of-fold, document-grouped result is confirmatory. Everything else is
   labelled exploratory, and must stay labelled that way.

## Naming discipline — two errors that read as fraud

- The comparator is a **local paper-style baseline**, never "the paper's
  configuration". The published system uses a larger text retriever plus a
  *visual* retriever (ColPali/ColQwen); the paper names no version, so it
  cannot be reproduced from the publication. E34 measured the consequence:
  restoring the full image pool moves recall@10 from 0.820 to 0.782, but the
  paper's 0.708 stays outside the interval at every k. Improvement over this
  baseline is improvement over *this baseline*.
- BM25 or dense retrieval over VLM-written image descriptions is
  **image-description retrieval**. Never "visual retrieval", never "raw-image
  retrieval" — no pixels are read.

## Running things

```bash
python experiments.py list                                   # the registry
python experiments.py run-suite replay --offline             # 7 experiments, metrics only
python experiments.py run-suite retrieval --offline          # 23
python experiments.py run-suite full-local --offline --include-expensive   # 29, hours
python experiments.py verify E27 --run <replay_run_id>
```

`verify` defaults to the newest run, which is usually one experiment. Against
the wrong run it prints FAILs that mean *"this run never measured that"*, not
*"the number moved"*. **Always pass `--run`.**

Any suite accepts `--dry-run`, which prints the dependency plan with a
reuse/rebuild decision and a reason per artifact. Use it before long jobs.

## Hard rules

- **Never `git checkout` / `git switch` in this working tree** to inspect
  another revision. It carries ~800 MB of untracked derived artifacts. Use
  `git show <rev>:<path>` or `git worktree add`.
- **Never commit** `artifacts/api/**`, bulk logs, `per_question.csv`,
  embeddings, indexes, or the model cache. `docs/artifacts-git-policy.md`
  is the classification; `.gitignore` enforces it.
- **Never bulk-delete** `response/` or `artifacts/api/` — those are paid API
  outputs and cannot be regenerated for free.
- **Long jobs redirect to a file** and carry their own checkpoints. Do not pipe
  them into `tail`/`grep`; background jobs get killed and a buffering consumer
  loses everything. Scratch logs belong in `artifacts/logs/`, which is ignored.
- **Any mechanism that writes a directory per run must record its own size.**
  38 undeleted trees once reached 36.6 GB while every test passed.
- **Report measured tokens, not guessed dollars.** Cost comes from `total_tok`
  at a verified per-model price, reconciled against the provider's console.
  CPU passes and GPU passes are two currencies and are never summed.

## Registry conventions

`experiments.py` holds every experiment. Valid `status` keys are exactly
`pass` / `neg` / `pos` / `fix` / `correct` / `pending`; anything else is a
`KeyError` at render time. Valid `lifecycle` values are `active` /
`superseded` / `manual` / `blocked`.

When a result changes, **append** `result2`, `result3`, … rather than editing
the original, and put superseded numbers in `corrections`. A retracted number
must stay visible with its retraction; the renderer prints every `resultN`.

An `active` entry that has `cmds` but `suites=()` needs a stated reason —
otherwise `run-suite` cannot recheck it, which is how a published negative
result (E36) went unrunnable for two phases.

## Definition of done

A change is not finished until all four suites pass:

```bash
python -m tests.test_runner --scratch-root artifacts/test-runs   # 64
python -m tests.test_source_bundle --scratch-root artifacts/test-runs  # 19
python -m tests.test_statistics                                  # 25
python -m tests.test_phase3                                      # 33
```

…and the advance is written into `docs/lab-notebook.html` and, if it changes
the map, `docs/HANDOFF.md`. **A result reported only in a chat transcript did
not happen.** If a test starts failing because the repository got *better*,
fix the assertion to test the invariant, not the old situation — and say so in
the commit message (see lesson 45).
