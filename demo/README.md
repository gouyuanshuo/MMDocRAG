# The demo console

A browsable front end over what this project measured: `demo/` serves the
recorded artifacts, `webui/` renders them. The UI is adapted from a group-mate's
interface, [kosuzu123/Multimodal-rag-UI](https://github.com/kosuzu123/Multimodal-rag-UI);
the design is theirs, the data underneath is this repository's.

**By default nothing here generates anything.** No model is called, no retrieval
is re-run, no metric is recomputed at serve time. Every answer is replayed from
`response/`, every ranking comes from the cached action table E27's builder
wrote, and every number on the dashboard is a row in a recorded run's
`metrics.jsonl`. That is the property the console is built around: if an
artifact is missing, the affected panel says so instead of falling back to a
plausible value.

There is exactly one exception, and it is opt-in: `--live` lets you type your own
question, retrieves for it over the corpus, and calls the API. See
[Live mode](#live-mode-real-retrieval-a-real-api-call) below. A live answer is
new work, is labelled that way everywhere it appears, and is never a result.

## Run it

```bash
python -m demo.server                 # http://127.0.0.1:8000
```

That serves the API and the built UI together. If `webui/dist` has not been
built yet:

```bash
cd webui && npm install && npm run build
```

While working on the front end, run the two separately so Vite can hot-reload:

```bash
python -m demo.server --no-static     # API on 8000
cd webui && npm run dev               # UI on 3000, proxying /api to 8000
```

Useful flags: `--port`, `--metrics-run <run_id>`, `--image-root <dir>`,
`--verbose`.

## What the four views show

| View | What it is |
|---|---|
| RAG Console | **Replay:** ask one of the 600 questions the recorded end-to-end run covered. Free text is matched to the closest benchmark question by BM25 and the match is stated in the transcript. The answer is replayed with its images and citations resolved against the candidate block the model was actually given. **Live** (with `--live`): ask anything, and retrieval and generation happen now. |
| Query Analysis | The same question under both retrieval configurations, side by side — same model, same prompt, same gold, different candidate block. Plus what each retriever would have surfaced, and the per-question escalation decision. |
| Experiments | Five groups of recorded comparisons (E29, E27/E40/E41, E24/E34, E37, E35/E36), each row with its interval, its n, and the unit that was resampled. Then the full 42-experiment registry. |
| Provenance | Which artifact every panel reads, which run the metrics come from, and the standing caveats — including the ones this project has already had to correct once. |

## A three-minute walk-through

1. **RAG Replay** → open *Browse the 600 recorded questions* and search
   `median investments in Europe`. Pick
   *"How do the trends of median investments in Europe and the U.S. from 2004 to
   2009 compare across different investment stages?"* (`evaluation:52`). The
   selected configuration retrieved both gold charts and the answer cites them
   inline; the citation F1 tile reads 1.00 against 0.00 for the baseline arm.
2. **Query Analysis** → the same question with both arms side by side. The
   paper-style arm's candidate block never contained the gold charts, which is
   why its answer talks around them. Below that, each retriever's top 10 with
   the gold positions marked.
3. **Experiments** → *End-to-end* for the paired difference that actually
   carries an interval (+2.90 F1, 95% CI [+1.01, +4.77] over 220 documents),
   then *Routing budget* for the recall-against-budget curve.
4. **Provenance** → which file each of those panels read.

Step 1 is an anecdote and the UI says so: one question proves nothing, and the
interval in step 3 is the claim. Showing them in that order is the point —
`evaluation:1428` ("the price of the keyboard in Figure 111") is a second
single-question case if a second is wanted.

## Live mode: real retrieval, a real API call

```bash
python -m demo.server --live                          # adds the Live switch to the UI
python -m demo.server --live --live-mode multimodal   # send the images, not their descriptions
python -m demo.server --live --live-budget 50 --live-model gemini-3.6-flash
```

Everything above replays. Live mode is the one thing that does new work: type
any question, and the console retrieves over the corpus now and asks the model
now. It is off by default because each answer costs money.

What it runs is this project's own configuration, not an approximation:
canonical pool, RRF text + RRF image-description, quota 4/6 at k=10 — the
configuration nested CV selected — with `models/bge-large-en-v1.5`, the encoder
E40 re-checked the headline on. Generation goes through
`inference_wrapper.Gemini_Inference` with `prompt_bank/pure_text_infer.txt`, the
same class and prompt the recorded runs used.

One stage exists only here. A benchmark question arrives with the document it is
about; a typed question does not, so live mode retrieves the document first with
BM25 over each document's own text. Measured on 200 benchmark questions against
their annotated document:

```
python -m demo.live --check-document-selection      # top1 80.0%  top3 89.2%  top5 90.8%
```

The UI shows which document was picked and offers the runners-up, because a
wrong document produces a confidently wrong answer and that should be visible
rather than mysterious.

`--live-mode` picks what the model is given for an image. `pure-text` (the
default, and the recorded arms' mode) sends the VLM-written description;
`multimodal` opens the JPEG and sends the image itself, so the model reads the
chart rather than someone's summary of it. Measured on this machine, one
question through each: pure-text 2,131 input / 348 output tokens, multimodal
7,204 input / 220 output — six images cost roughly three times the input. Both
numbers come from the provider's own usage field; no price is asserted. If an
image file is missing, multimodal refuses the question rather than dropping the
image, because a silently shortened candidate block is a changed quota that
nothing on screen would report.

**A live answer is not a result.** No run recorded it, no experiment scored it,
and it must not be quoted as one — the UI says so on every live turn. Two
differences from the E29 arms are structural: the document stage above, and the
encoder (live uses bge-large; the recorded arms were built on bge-small), so a
live candidate block can differ from the recorded one for the same question.

When the typed question *is* exactly a benchmark question, its gold is known, so
retrieved gold is flagged and a citation F1 is computed with `eval_all`'s own
scorer. That number is a diagnostic for the person watching: computed now, over
a retrieval no run performed, and written nowhere.

Cost control, in three parts: live mode is off unless asked for; a per-process
budget (default 25 calls) refuses the request rather than spending quietly; and
every attempt — including failures — is written to
`artifacts/api/demo-live/requests.jsonl` before the answer is returned. Tokens
are reported as measured, verbatim from the provider. No dollar figure is
asserted anywhere in the console.

Startup with `--live` takes ~25 seconds: the corpus index, the passage vectors
and the encoder are all loaded before the first question rather than in front of
an audience. After that a query encodes in milliseconds and retrieval is well
under a second; the wait you see is the model.

## Inputs it reads

| Input | In Git? | If missing |
|---|---|---|
| `dataset/evaluation_{ours,paper}k10.jsonl` | tracked | the replay views lose their arms |
| `response/gemini-3.6-flash_pure-text_quotes{ours,paper}k10_response.jsonl` | tracked | no answers to replay |
| `canonical/mmdocrag.sqlite` | ignored, rebuildable | no page numbers or evidence text |
| `router/cache/actions_canonical_bge-small-en-v1.5.pkl` | ignored, rebuildable with `python -m router.actions --pool canonical` | no rankings, no gold flags |
| `artifacts/runs/<run>/metrics.jsonl` | ignored, rebuilt by `python reproduce.py` | the dashboard falls back to the newest run on disk and says which |
| `artifacts/e39/20260905/router/per_question.csv` | ignored | the per-question routing panel disappears |
| The 14,826 dataset images | never in Git | evidence images 404 with a pointer to `images/README.md`; set `MMDOCRAG_IMAGE_ROOT` if they live elsewhere |

An explicitly requested `--metrics-run` is never substituted. Only the default
falls back, and the run id in use is printed at startup and shown in the UI.

## Why the arms can be annotated at all

The arm files carry local quote ids (`text3`, `image7`) and no evidence ids, so
a page number cannot be read off them. `demo/store.py` reconstructs each arm's
candidate block from the cached action table — same builder, same pool, same
encoder, same quota — which recovers the evidence id behind every quote.
`tests/test_demo.py` asserts that this reconstruction reproduces all 1,200
recorded arm rows exactly. Without that assertion the page numbers and gold
flags in the UI would be a guess.

## Tests

```bash
python -m tests.test_demo             # 60 assertions, no server and no API calls
cd webui && npm run check:render      # renders every component against the live API
```

`test_demo` covers live mode without spending: it runs the real retrieval path,
checks the quota and the document stage, and asserts that the engine refuses to
call anything without a key or a budget. The render check has an opt-in live
section (`MMDOCRAG_RENDER_CHECK_LIVE=1`) that does make one paid call.

`check:render` needs `python -m demo.server` running. There is no browser in
this environment, so the console has not had a visual pass; what the render
check establishes is that every component renders the real payloads, that no
table silently drops rows, and that the values in the HTML are the values in the
artifacts.

## Two things the console deliberately does not claim

The retrieval configuration is **static** — nested CV chose one configuration
for every question. The per-question decision this project measured is whether
to escalate to the GPU visual retriever, and it is a cost result (E36), so it is
shown separately and labelled that way.

`citationF1` is **quote-selection F1**: which evidence the answer cited. Answer
correctness and faithfulness were not measured, and the console says so on every
screen that shows the number.
