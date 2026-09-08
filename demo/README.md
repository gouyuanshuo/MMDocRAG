# The demo console

A browsable front end over what this project measured: `demo/` serves the
recorded artifacts, `webui/` renders them. The UI is adapted from a group-mate's
interface, [kosuzu123/Multimodal-rag-UI](https://github.com/kosuzu123/Multimodal-rag-UI);
the design is theirs, the data underneath is this repository's.

**Nothing here generates anything.** No model is called, no retrieval is re-run,
no metric is recomputed at serve time. Every answer is replayed from
`response/`, every ranking comes from the cached action table E27's builder
wrote, and every number on the dashboard is a row in a recorded run's
`metrics.jsonl`. That is the property the console is built around: if an
artifact is missing, the affected panel says so instead of falling back to a
plausible value.

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
| RAG Replay | Ask one of the 600 questions the recorded end-to-end run covered. Free text is matched to the closest benchmark question by BM25 and the match is stated in the transcript. The answer is replayed with its images and citations resolved against the candidate block the model was actually given. |
| Query Analysis | The same question under both retrieval configurations, side by side — same model, same prompt, same gold, different candidate block. Plus what each retriever would have surfaced, and the per-question escalation decision. |
| Experiments | Five groups of recorded comparisons (E29, E27/E40/E41, E24/E34, E37, E35/E36), each row with its interval, its n, and the unit that was resampled. Then the full 41-experiment registry. |
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
python -m tests.test_demo             # 48 assertions, no server needed
cd webui && npm run check:render      # renders every component against the live API
```

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
