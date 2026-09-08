"""The five dashboard groups, assembled from the recorded run's metrics.

Each row carries its own interval, its own n, and the unit that was resampled,
because those three are what decide whether a number means anything. A row with
no interval in the artifact shows no interval here rather than borrowing one
from a neighbour.

Nothing is computed in this file. `store.find` selects metric rows the recorded
run wrote; the functions below only choose which of them to show and what to
call them. If a metric is absent the table says the run did not measure it.
"""

import demo.config as C

FORMAT = dict(
    TEXT="text", RECALL="recall", F1="f1", DELTA="delta", DELTA_F1="deltaF1",
    PCT="pct", INT="int", P="p")


def _cell(metric, digits=3):
    """value / ci / p from one metric row, or Nones if the run lacks it."""
    if metric is None:
        return dict(value=None, ciLow=None, ciHigh=None, pRaw=None, pHolm=None,
                    significant=None, missing=True)
    return dict(
        value=metric.get("value"),
        ciLow=metric.get("ci_low"), ciHigh=metric.get("ci_high"),
        pRaw=metric.get("p_raw", metric.get("p_two_sided", metric.get("p"))),
        pHolm=metric.get("p_holm"),
        significant=metric.get("significant", metric.get("significant_holm")),
        missing=False)


def _n(metric):
    if metric is None:
        return {}
    return dict(questions=metric.get("n_questions"),
                documents=metric.get("n_documents"),
                sampleUnit=metric.get("sample_unit"),
                bootstrap=metric.get("bootstrap"))


def _encoder(metric, default=None):
    if metric is None:
        return default
    name = metric.get("dense_model") or default
    return str(name).split("/")[-1] if name else None


def _visual_label(spec):
    """Only ColQwen reads pixels; everything else reads VLM-written text."""
    retriever = spec["visual_retriever"]
    return ("ColQwen visual (raw pixels)" if retriever == "colqwen"
            else f"{retriever} image-description")


# --------------------------------------------------------------------------
# end-to-end (E29)

def end_to_end(store):
    ours = store.one("E29", "final_f1_ours")
    paper = store.one("E29", "final_f1_paper")
    delta = store.one("E29", "delta_final_f1[ours - paper]")
    better = store.one("E29", "questions_better")
    worse = store.one("E29", "questions_worse")
    equal = store.one("E29", "questions_equal")

    rows = []
    for label, metric, spec_key, is_ours in (
            ("Nested-CV selected configuration", ours, "ours", True),
            ("Closest local paper-style baseline", paper, "paper", False)):
        spec = C.ARMS[spec_key]
        rows.append(dict(
            label=label,
            config=f"{spec['text_retriever']} text + {_visual_label(spec)}, "
                   f"quota {spec['quota'][0]}/{spec['quota'][1]}",
            f1=_cell(metric),
            delta=_cell(delta) if is_ours else _cell(None),
            n=_n(metric or delta),
            note=spec["desc"]))

    counts = [dict(label="Questions where the selected config cited better evidence",
                   value=_cell(better)),
              dict(label="Questions where it cited worse evidence", value=_cell(worse)),
              dict(label="Questions unchanged", value=_cell(equal))]

    return dict(
        id="end-to-end",
        title="Does the retrieval gain survive the generator?",
        subtitle="E29. Both arms answer the same 600 questions over 220 documents "
                 "with the same model and the same prompt. Only the retrieved "
                 "candidate block differs.",
        source=dict(experiments=["E29"], run=store.metrics_meta.get("run_id"),
                    model=C.GENERATION["model"]),
        notes=[
            "The metric is quote-selection F1 -- which evidence the answer cited. "
            "It is not answer correctness and not faithfulness; neither was measured.",
            "gemini-3.6-flash is not in the paper's model table, so the absolute "
            "F1 is not comparable to any published row. Only the paired "
            "difference is interpretable.",
            "The interval resamples documents. A question-unit bootstrap is also "
            "recorded in the run, marked as the wrong sampling unit and kept only "
            "as a contrast; it is not shown here and must not be cited.",
            "A gold quote the retriever never surfaced is scored as a miss -- the "
            "candidate block is all the generator can cite from.",
        ],
        tables=[
            dict(id="arms", title="Quote-selection F1 by arm",
                 columns=[dict(key="label", label="Arm", format=FORMAT["TEXT"]),
                          dict(key="config", label="Configuration", format=FORMAT["TEXT"]),
                          dict(key="f1", label="Citation F1", format=FORMAT["F1"]),
                          dict(key="delta", label="Paired Δ (95% CI, documents)",
                               format=FORMAT["DELTA_F1"])],
                 rows=rows,
                 chart=dict(kind="bar", valueKey="f1", labelKey="label", unit="F1 points")),
            dict(id="direction", title="Where the difference comes from",
                 columns=[dict(key="label", label="Per-question direction", format=FORMAT["TEXT"]),
                          dict(key="value", label="Questions", format=FORMAT["INT"])],
                 rows=counts, chart=None),
        ])


# --------------------------------------------------------------------------
# retrieval stack (E27 / E40 / E41)

_ENCODER_OF = {"E27": "bge-small-en-v1.5", "E40": "bge-large-en-v1.5"}


def retrieval(store):
    deltas = []
    for metric in store.find("E41"):
        name = metric.get("name", "")
        if not name.startswith("delta:"):
            continue
        _, exp, pool, k = name.split(":")
        deltas.append(dict(
            label=f"{pool} pool, k={k}",
            experiment=exp,
            encoder=_ENCODER_OF.get(exp, "?"),
            delta=_cell(metric),
            n=_n(metric),
            family=metric.get("family_size"),
            note="out-of-fold selected configuration minus the closest local "
                 "paper-style hybrid"))
    deltas.sort(key=lambda r: (r["experiment"], r["label"]))

    absolute = []
    for exp in ("E40", "E27"):
        for pool in ("canonical", "selfbuilt"):
            for k in (10, 20):
                oof = store.one(exp, "recall_nested_cv_oof", pool=pool, k=k)
                base = store.one(exp, "recall_paper_style_E", pool=pool, k=k)
                surrogate = store.one(exp, "recall_surrogate_A", pool=pool, k=k)
                if oof is None and base is None:
                    continue
                absolute.append(dict(
                    label=f"{pool} pool, k={k}",
                    experiment=exp,
                    encoder=_encoder(oof or base, _ENCODER_OF.get(exp)),
                    oof=_cell(oof), paperStyle=_cell(base), surrogate=_cell(surrogate),
                    n=_n(oof or base),
                    stable=(oof or {}).get("selection_stable_across_folds")))

    return dict(
        id="retrieval",
        title="The static retrieval configuration",
        subtitle="E27 (bge-small) and E40 (bge-large), audited for multiplicity "
                 "by E41. Recall@k over 2,000 questions in 220 documents, "
                 "out-of-fold with document-grouped folds.",
        source=dict(experiments=["E27", "E40", "E41"],
                    run=store.metrics_meta.get("run_id")),
        notes=[
            "Exploratory, not confirmatory. The folds are document-grouped and "
            "the configuration is chosen without the question it is scored on, "
            "but the method space was developed on these same questions.",
            "E41 is a post-hoc multiplicity audit over the family of eight "
            "comparisons; it is not a preregistered analysis.",
            "Unmapped gold counts as a miss, so these are unconditional recalls.",
            "The comparator is the closest local paper-style hybrid, not the "
            "published system: the paper pairs BGE-large-en-v1.5 with "
            "ColQwen2-v0.1, this fork runs ColQwen2-v1.0 over a different pool.",
        ],
        tables=[
            dict(id="deltas",
                 title="Selected configuration minus paper-style baseline",
                 subtitle="95% CI resamples documents; Holm correction over the "
                          "family of eight.",
                 columns=[dict(key="label", label="Cell", format=FORMAT["TEXT"]),
                          dict(key="encoder", label="Encoder", format=FORMAT["TEXT"]),
                          dict(key="delta", label="Δ recall (95% CI)", format=FORMAT["DELTA"]),
                          dict(key="delta", label="p (Holm)", format=FORMAT["P"],
                               variant="p")],
                 rows=deltas,
                 chart=dict(kind="bar", valueKey="delta", labelKey="label",
                            unit="Δ recall", groupKey="encoder")),
            dict(id="absolute", title="What each arm actually scores",
                 columns=[dict(key="label", label="Cell", format=FORMAT["TEXT"]),
                          dict(key="encoder", label="Encoder", format=FORMAT["TEXT"]),
                          dict(key="oof", label="Out-of-fold selected", format=FORMAT["RECALL"]),
                          dict(key="paperStyle", label="Paper-style hybrid", format=FORMAT["RECALL"]),
                          dict(key="surrogate", label="Dense surrogate", format=FORMAT["RECALL"])],
                 rows=absolute, chart=None),
        ])


# --------------------------------------------------------------------------
# visual branch (E24 / E34)

_VISUAL = [
    ("colqwen", "ColQwen2 over raw image pixels", True),
    ("rrf_desc", "RRF(BM25, BGE) over VLM-written image descriptions", False),
    ("rrf", "RRF(BM25 descriptions, ColQwen)", True),
    ("bm25", "BM25 over VLM-written image descriptions", False),
    ("dense", "BGE dense over VLM-written image descriptions", False),
]


def visual(store):
    rows = []
    for key, description, pixels in _VISUAL:
        cells = {f"r{k}": _cell(store.one("E24", f"recall@{k}_{key}"))
                 for k in (1, 5, 10, 20)}
        if all(c["missing"] for c in cells.values()):
            continue
        rows.append(dict(label=key, description=description,
                         readsPixels=pixels, **cells,
                         n=_n(store.one("E24", f"recall@10_{key}"))))

    paired = []
    for metric in store.find("E24"):
        if not metric.get("name", "").startswith("paired_delta["):
            continue
        label = metric["name"][len("paired_delta["):].split("]")[0]
        at_k = metric["name"].rsplit("@", 1)[-1]
        paired.append(dict(label=label, k=at_k, delta=_cell(metric),
                           n=_n(metric), note=metric.get("desc")))
    paired.sort(key=lambda r: (r["label"], r["k"]))

    fullpool = []
    for k in (10, 15, 20):
        full = store.one("E34", f"recall@{k}_colqwen_fullpool")
        quota = store.one("E34", f"recall@{k}_colqwen_fullpool_quota")
        delta = store.one("E34", f"paired_full_minus_candidate_recall_at_{k}")
        if full is None:
            continue
        fullpool.append(dict(
            label=f"k={k}", full=_cell(full), quota=_cell(quota),
            deltaVsCandidatePool=_cell(delta), n=_n(full),
            paperValue=full.get("paper_value"),
            paperInsideCi=full.get("paper_inside_ci")))

    return dict(
        id="visual",
        title="The visual branch, and what ColQwen is worth here",
        subtitle="E24 compares retrievers over the same image pool; E34 restores "
                 "the full document image pool the paper indexes.",
        source=dict(experiments=["E24", "E34"], run=store.metrics_meta.get("run_id")),
        notes=[
            "BM25 or dense retrieval over VLM-written image descriptions is "
            "image-description retrieval. It reads no pixels. Only ColQwen does.",
            "3,231 visual gold pairs, all mapped; 1,995 of 2,000 questions have "
            "visual gold and only those enter the denominator.",
            "E34's full-pool recall@10 of 0.782 sits above the paper's 0.708, and "
            "the paper's value stays outside the interval at every k -- which "
            "measures a pool and pipeline difference, not a better system.",
        ],
        tables=[
            dict(id="retrievers", title="Visual recall@k by retriever",
                 columns=[dict(key="label", label="Retriever", format=FORMAT["TEXT"]),
                          dict(key="description", label="What it reads", format=FORMAT["TEXT"]),
                          dict(key="r1", label="R@1", format=FORMAT["RECALL"]),
                          dict(key="r5", label="R@5", format=FORMAT["RECALL"]),
                          dict(key="r10", label="R@10", format=FORMAT["RECALL"]),
                          dict(key="r20", label="R@20", format=FORMAT["RECALL"])],
                 rows=rows,
                 chart=dict(kind="bar", valueKey="r10", labelKey="label",
                            unit="recall@10")),
            dict(id="paired", title="Paired contrasts, same questions and gold",
                 columns=[dict(key="label", label="Contrast", format=FORMAT["TEXT"]),
                          dict(key="k", label="k", format=FORMAT["TEXT"]),
                          dict(key="delta", label="Δ recall (95% CI)", format=FORMAT["DELTA"])],
                 rows=paired, chart=None),
            dict(id="fullpool", title="Full document image pool (E34)",
                 subtitle="220/220 documents indexed; ranked images the official "
                          "candidate pool never contained are what makes this "
                          "comparable to the paper's setup.",
                 columns=[dict(key="label", label="Budget", format=FORMAT["TEXT"]),
                          dict(key="full", label="Recall, full pool", format=FORMAT["RECALL"]),
                          dict(key="quota", label="Visual slots only", format=FORMAT["RECALL"]),
                          dict(key="deltaVsCandidatePool",
                               label="Δ vs candidate pool", format=FORMAT["DELTA"])],
                 rows=fullpool, chart=None),
        ])


# --------------------------------------------------------------------------
# question slices (E37)

_SLICE_FAMILIES = {
    "evidence_modality": "evidence modality",
    "gold_page_span": "gold page span",
    "question_type": "question type",
}


def _split_slice(rest):
    """'question_type_Descriptive' -> ('question type', 'Descriptive')."""
    for prefix, label in _SLICE_FAMILIES.items():
        if rest.startswith(prefix + "_"):
            return label, rest[len(prefix) + 1:]
    return rest.replace("_", " "), rest


def slices(store):
    tables = []
    for pool in ("canonical", "selfbuilt"):
        rows = []
        for metric in store.find("E37", pool=pool):
            name = metric.get("name", "")
            if not name.startswith("delta_k"):
                continue
            _, ktag, rest = name.split("_", 2)
            family, slice_name = _split_slice(rest)
            rows.append(dict(
                label=slice_name,
                family=family,
                k=ktag.replace("k", "k="),
                delta=_cell(metric), n=_n(metric),
                note=metric.get("desc")))
        if not rows:
            continue
        rows.sort(key=lambda r: (r["k"], r["family"], r["label"]))
        contrasts = [dict(label=m["name"].replace("contrast_", "").replace("_", " "),
                          delta=_cell(m), n=_n(m), note=m.get("desc"))
                     for m in store.find("E37", pool=pool)
                     if m.get("name", "").startswith("contrast_")]
        tables.append(dict(
            id=f"slices-{pool}", title=f"{pool} pool",
            columns=[dict(key="label", label="Slice", format=FORMAT["TEXT"]),
                     dict(key="family", label="Family", format=FORMAT["TEXT"]),
                     dict(key="k", label="Budget", format=FORMAT["TEXT"]),
                     dict(key="delta", label="Δ recall (95% CI)", format=FORMAT["DELTA"]),
                     dict(key="delta", label="p (Holm)", format=FORMAT["P"], variant="p")],
            rows=rows,
            chart=dict(kind="bar", valueKey="delta", labelKey="label",
                       unit="Δ recall", filterKey="k", filterValue="k=10")))
        if contrasts:
            tables.append(dict(
                id=f"contrasts-{pool}", title=f"{pool} pool — heterogeneity",
                subtitle="difference in improvement between two slices of the "
                         "same family; this is the test of whether the gain is "
                         "uneven, not the gain itself",
                columns=[dict(key="label", label="Contrast", format=FORMAT["TEXT"]),
                         dict(key="delta", label="Difference (95% CI)", format=FORMAT["DELTA"])],
                rows=contrasts, chart=None))

    return dict(
        id="slices",
        title="Where the static gain actually lands",
        subtitle="E37 slices the same out-of-fold predictions by question type, "
                 "evidence modality and page span. Selection is never re-run "
                 "inside a slice.",
        source=dict(experiments=["E37"], run=store.metrics_meta.get("run_id")),
        notes=[
            "Slices consume nested_cv's out-of-fold predictions. Re-running "
            "selection inside a slice would make every slice its own winner.",
            "The gain concentrates on pure-visual questions at k=10 and is much "
            "smaller at k=20 -- it is largely a visual-recall improvement.",
            "Two of the five classes the proposal asked for cannot be evaluated "
            "on this benchmark: pure-text has 1 question and unanswerable has 0.",
        ],
        tables=tables)


# --------------------------------------------------------------------------
# routing budget (E35 / E36 / E39)

def routing(store):
    curve = []
    curve_cell = None
    for metric in sorted((m for m in store.find("E36")
                          if m.get("name", "").startswith("recall_router_B")),
                         key=lambda m: m.get("budget", 0.0)):
        budget = metric.get("budget")
        tag = metric["name"].rsplit("_B", 1)[-1]
        random_ = store.one("E36", f"recall_random_B{tag}")
        oracle = store.one("E36", f"recall_oracle_B{tag}")
        curve_cell = curve_cell or metric
        curve.append(dict(
            label=f"B={budget:.2f}" if budget is not None else tag,
            budget=budget,
            router=_cell(metric), random=_cell(random_), oracle=_cell(oracle),
            n=_n(metric)))

    survival = []
    for cascade in ("gpu", "cpu"):
        for pool in ("canonical", "selfbuilt"):
            for k in (10, 20):
                name = f"router_minus_random [{cascade}/{pool}/k={k}]"
                metric = store.one("E36", name)
                if metric is None:
                    continue
                survival.append(dict(
                    label=f"{cascade.upper()} cascade, {pool}, k={k}",
                    cascade=cascade,
                    delta=_cell(metric), n=_n(metric),
                    budget=metric.get("declared_budget"),
                    note=metric.get("desc")))

    ceiling = []
    for pool in ("canonical", "selfbuilt"):
        for k in (10, 20):
            oracle = store.one("E35", "recall_oracle", pool=pool, k=k)
            fixed = store.one("E35", "recall_best_fixed", pool=pool, k=k)
            static = store.one("E35", "recall_static_rrf", pool=pool, k=k)
            gap = store.one("E35", "oracle_minus_fixed", pool=pool, k=k)
            if oracle is None:
                continue
            ceiling.append(dict(
                label=f"{pool} pool, k={k}",
                oracle=_cell(oracle), bestFixed=_cell(fixed), staticRrf=_cell(static),
                gap=_cell(gap), n=_n(oracle)))

    plan = store.e39_plan or {}
    return dict(
        id="routing",
        title="Per-question routing: a cost result, not a quality result",
        subtitle="E35 measures the ceiling a perfect router could reach; E36 asks "
                 "whether a learned router reaches any of it; E39 is designed and "
                 "not run.",
        source=dict(experiments=["E35", "E36", "E39"],
                    run=store.metrics_meta.get("run_id")),
        notes=[
            "CPU passes and GPU passes are two currencies and are never summed. "
            "The budget B is the fraction of questions allowed the GPU retriever.",
            "The budget at which the router's recall curve meets the static "
            "system is read off the curve. It is not itself a hypothesis test, "
            "and no equivalence test was run.",
            "The GPU escalation decision is partly learnable; the CPU fusion "
            "decision is not -- it does not beat random allocation at the same "
            "budget once Holm correction is applied.",
            f"E39 status: {plan.get('status', 'unknown')}. "
            f"{plan.get('api_calls_made', 0)} API calls made. A prepared "
            "experiment is not a generated one.",
        ],
        tables=[
            dict(id="curve", title="Recall against GPU budget",
                 subtitle="Router, random allocation at the same budget, and the "
                          "oracle. One cell of the design: "
                          f"{(curve_cell or {}).get('pool', '?')} pool, "
                          f"k={(curve_cell or {}).get('k', '?')}, policy "
                          f"{(curve_cell or {}).get('policy', '?')}, features "
                          f"{(curve_cell or {}).get('features', '?')}.",
                 columns=[dict(key="label", label="Budget", format=FORMAT["TEXT"]),
                          dict(key="router", label="Router", format=FORMAT["RECALL"]),
                          dict(key="random", label="Random at same budget", format=FORMAT["RECALL"]),
                          dict(key="oracle", label="Oracle", format=FORMAT["RECALL"])],
                 rows=curve,
                 chart=dict(kind="line", xKey="budget",
                            seriesKeys=["random", "router", "oracle"],
                            unit="recall")),
            dict(id="survival", title="Router minus random, at the same budget",
                 subtitle="The comparison that was actually tested. A CI touching "
                          "zero is not significant.",
                 columns=[dict(key="label", label="Cell", format=FORMAT["TEXT"]),
                          dict(key="delta", label="Δ recall (95% CI)", format=FORMAT["DELTA"]),
                          dict(key="delta", label="p (Holm)", format=FORMAT["P"], variant="p")],
                 rows=survival, chart=None),
            dict(id="ceiling", title="What a perfect router could buy (E35)",
                 columns=[dict(key="label", label="Cell", format=FORMAT["TEXT"]),
                          dict(key="oracle", label="Oracle", format=FORMAT["RECALL"]),
                          dict(key="bestFixed", label="Best fixed action", format=FORMAT["RECALL"]),
                          dict(key="staticRrf", label="Static RRF", format=FORMAT["RECALL"]),
                          dict(key="gap", label="Oracle − best fixed", format=FORMAT["DELTA"])],
                 rows=ceiling, chart=None),
        ])


GROUPS = {
    "end-to-end": end_to_end,
    "retrieval": retrieval,
    "visual": visual,
    "slices": slices,
    "routing": routing,
}


def build(store, group_id):
    fn = GROUPS.get(group_id)
    if fn is None:
        return None
    payload = fn(store)
    payload["caveats"] = list(C.CAVEATS)
    return payload


def index(store):
    return [dict(id=gid, title=build(store, gid)["title"]) for gid in C.GROUPS]
