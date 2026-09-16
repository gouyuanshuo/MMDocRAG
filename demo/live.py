"""Live mode: real retrieval over the corpus, one real API call, per question.

The rest of this console replays what runs recorded. This module is the one
place that does new work, and it is off unless the server is started with
`--live`, because every answer it produces costs money.

What "real" means here, precisely
---------------------------------
Retrieval is this project's own recipe, not an approximation of it. The units,
the normalisation, the tokeniser, the BM25 parameters, the dense vectors, the
RRF constant and the 4/6 quota are the ones `retrieval.eval_stack_v2.build`
uses for the canonical pool at k=10 -- the configuration nested CV selected.
The only thing that cannot be reused is the query vector, which for benchmark
questions was precomputed; a typed question is encoded on the spot with the
same encoder and the same query prefix.

Generation goes through `inference_wrapper.Gemini_Inference`, the same class
the recorded runs called, with the same prompt file. A different prompt or a
hand-rolled request would produce answers that look like the recorded ones and
are not comparable to them.

What a live answer is NOT
-------------------------
It is not part of any recorded run, it was not scored by any experiment, and it
must never be quoted as one. Two differences from the E29 arms are structural
and cannot be papered over:

    the document. A benchmark question comes with the document it is about;
    a typed question does not, so this module retrieves the document first
    (BM25 over each document's own text) and says which one it picked.

    the encoder. The recorded arms were built on bge-small in August; live mode
    uses bge-large, the headline encoder since E40. Same recipe, different
    vectors, so a live candidate block can differ from the recorded one for the
    same question.

Where the question *is* a benchmark question, its gold is known, so retrieved
gold is flagged and a citation F1 is computed with `eval_all`'s own scorer. That
number is a diagnostic for the person watching -- it is computed now, over a
retrieval no run performed, and it is written nowhere.

Cost control: a per-process call budget (default 25), every attempt written to
`artifacts/api/demo-live/requests.jsonl` before the answer is returned, and
tokens reported as measured while price is not.
"""

import hashlib
import os
import sys
import threading
import time

# sentence-transformers imports whichever backends transformers can find, and
# on this machine that means TensorFlow: the encoder took 92 seconds to load,
# of which ~84 were Keras initialising a backend nothing here uses. Pinned to
# torch, the same load is 8 seconds and a query encodes in ~13 ms. Set before
# any transformers import, which is why it sits above the imports.
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("USE_TORCH", "1")

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from demo import config as C                                      # noqa: E402
from expkit import apilog                                         # noqa: E402
from retrieval.bm25 import BM25                                   # noqa: E402
from retrieval.corpus import normalize, tokenize                  # noqa: E402
from retrieval.eval_stack_v2 import RRF_C, rrf                    # noqa: E402

# The configuration nested CV selected at k=10, and the encoder E40 re-checked
# it on. Both are reported with every answer.
DENSE_MODEL = os.environ.get("MMDOCRAG_LIVE_ENCODER", "models/bge-large-en-v1.5")
MODEL = os.environ.get("MMDOCRAG_LIVE_MODEL", "gemini-3.6-flash")
# The benchmark's two input modes, with the prompt file each one uses.
# pure-text sends the VLM-written description of an image; multimodal sends the
# image itself. The recorded E29 arms are pure-text, so that is the default --
# switching modes changes what the model is given and makes the answer even less
# comparable to them.
MODES = {"pure-text": "pure_text_infer.txt", "multimodal": "multimodal_infer.txt"}
MODE = os.environ.get("MMDOCRAG_LIVE_MODE", "pure-text")
K = 10
QUOTA = (4, 6)
DEFAULT_BUDGET = 25


def prompt_path(mode):
    return os.path.join(C.REPO_ROOT, "prompt_bank", MODES[mode])


class LiveUnavailable(Exception):
    """Raised with a reason a person can act on."""


class LiveEngine:
    def __init__(self, store, dense_model=DENSE_MODEL, model=MODEL,
                 budget=DEFAULT_BUDGET, mode=MODE, verbose=True):
        if mode not in MODES:
            raise ValueError(f"mode must be one of {sorted(MODES)}")
        self.store = store
        self.dense_model = dense_model
        self.model = model
        self.mode = mode
        self.budget = budget
        self.calls = 0
        self.verbose = verbose
        self._lock = threading.Lock()
        self._corpus = None
        self._doc_index = None
        self._doc_bm25 = None
        self._vectors = None
        self._encoder_loaded = False
        self._log = None
        self._prompt_hash = None

    # -- availability --------------------------------------------------------

    def status(self):
        key = os.environ.get("GEMINI_API_KEY", "")
        return dict(
            enabled=True,
            model=self.model,
            encoder=self.dense_model,
            k=K, quotaText=QUOTA[0], quotaVisual=QUOTA[1],
            pool="canonical",
            budget=self.budget,
            callsMade=self.calls,
            callsLeft=max(self.budget - self.calls, 0),
            apiKeyPresent=bool(key),
            mode=self.mode,
            sendsImages=self.mode == "multimodal",
            note="Live answers are new API calls. They are not part of any "
                 "recorded run and are not scored by any experiment."
                 + (" This server sends the images themselves, not their "
                    "descriptions." if self.mode == "multimodal" else ""))

    def require_ready(self):
        if not os.environ.get("GEMINI_API_KEY", ""):
            raise LiveUnavailable(
                "GEMINI_API_KEY is not set in this server's environment. "
                "Set it and restart: $env:GEMINI_API_KEY = \"...\"")
        if self.calls >= self.budget:
            raise LiveUnavailable(
                f"This server has already made its {self.budget} live calls. "
                f"Restart with --live-budget N to allow more; the budget exists "
                f"so a demo cannot spend without anyone noticing.")

    # -- corpus --------------------------------------------------------------

    def _load_corpus(self):
        """Text and image units per document, exactly as eval_stack_v2 builds them."""
        import sqlite3
        text_by_doc, image_by_doc = {}, {}
        con = sqlite3.connect(C.CANONICAL_DB)
        for eid, doc, text in con.execute(
                "SELECT evidence_id, doc_name, text FROM canonical_evidence "
                "WHERE type = 'text' ORDER BY doc_name, evidence_id"):
            text_by_doc.setdefault(doc, []).append((eid, normalize(text or "")))
        for eid, doc, desc in con.execute(
                "SELECT evidence_id, doc_name, img_description FROM canonical_evidence "
                "WHERE type <> 'text' ORDER BY doc_name, evidence_id"):
            image_by_doc.setdefault(doc, []).append((eid, normalize(desc or "")))
        con.close()
        self._corpus = dict(text=text_by_doc, image=image_by_doc)
        # First stage: one BM25 whose documents are the 220 corpus documents,
        # so a typed question can find the document it is about. A benchmark
        # question never needs this -- it arrives with its document.
        docs = sorted(set(text_by_doc) | set(image_by_doc))
        bags = []
        for doc in docs:
            tokens = []
            for _eid, text in text_by_doc.get(doc, []):
                tokens.extend(tokenize(text))
            for _eid, desc in image_by_doc.get(doc, []):
                tokens.extend(tokenize(desc))
            bags.append(tokens)
        self._doc_bm25 = (BM25(bags), docs)
        self._doc_index = {}

    def _corpus_ready(self):
        if self._corpus is None:
            t0 = time.time()
            self._load_corpus()
            if self.verbose:
                print(f"[live] corpus indexed in {time.time() - t0:.1f}s "
                      f"({len(self._doc_bm25[1])} documents)", flush=True)
        return self._corpus

    def _vectors_ready(self):
        """The passage vectors E27's builder uses, for this encoder."""
        if self._vectors is None:
            from retrieval import dense
            bundle, _questions = dense.load("vlm", self.dense_model)
            self._vectors = (bundle["vecs"],
                             {str(e): i for i, e in enumerate(bundle["eids"])})
        return self._vectors

    def _encode_query(self, question):
        from retrieval import dense
        if not self._encoder_loaded and self.verbose:
            print(f"[live] loading {self.dense_model} for query encoding", flush=True)
        vec = dense.encode([question], is_query=True, model_name=self.dense_model)[0]
        self._encoder_loaded = True
        return np.asarray(vec, dtype=np.float32)

    def warmup(self):
        """Pay the corpus index, the vectors and the encoder load up front.

        Otherwise the first person to ask a question waits ~10 seconds for the
        encoder while a room watches, and concludes the retrieval is slow. The
        per-query cost after this is milliseconds; what is slow is starting.
        """
        t0 = time.time()
        self._corpus_ready()
        self._vectors_ready()
        self._encode_query("warmup")
        return round(time.time() - t0, 1)

    def _branch_index(self, doc, branch):
        key = (doc, branch)
        cached = self._doc_index.get(key)
        if cached is not None:
            return cached
        units = self._corpus["text" if branch == "text" else "image"].get(doc, [])
        ids = [eid for eid, _ in units]
        bm = BM25([tokenize(t) for _, t in units])
        _vecs, position = self._vectors_ready()
        rows = np.asarray([position[e] for e in ids]) if ids else None
        self._doc_index[key] = (bm, ids, rows, units)
        return self._doc_index[key]

    # -- retrieval -----------------------------------------------------------

    def pick_document(self, question, top=5):
        self._corpus_ready()
        bm, docs = self._doc_bm25
        order, scores = bm.rank(tokenize((question or "").lower()))
        return [dict(docName=docs[int(i)], score=round(float(scores[int(i)]), 4))
                for i in order[:top]]

    def retrieve(self, question, doc):
        """One document's candidate block, by the selected configuration."""
        self._corpus_ready()
        vecs, _position = self._vectors_ready()
        query_vec = self._encode_query(question)
        query_tokens = tokenize((question or "").lower())
        timings, ranked = {}, {}
        for branch, quota in (("text", QUOTA[0]), ("visual", QUOTA[1])):
            bm, ids, rows, units = self._branch_index(doc, branch)
            if not ids:
                ranked[branch] = []
                continue
            t0 = time.perf_counter()
            order, _bm_scores = bm.rank(query_tokens)
            bm25_ranking = [ids[i] for i in order]
            timings[f"bm25_{branch}"] = time.perf_counter() - t0
            t0 = time.perf_counter()
            sims = vecs[rows] @ query_vec
            dense_order = np.lexsort((np.arange(len(ids)), -sims))
            dense_ranking = [ids[i] for i in dense_order]
            timings[f"dense_{branch}"] = time.perf_counter() - t0
            t0 = time.perf_counter()
            fused = rrf(bm25_ranking, dense_ranking)
            timings[f"rrf_{branch}"] = time.perf_counter() - t0
            sim_of = {ids[i]: float(sims[i]) for i in range(len(ids))}
            bm_rank_of = {e: i for i, e in enumerate(bm25_ranking)}
            dense_rank_of = {e: i for i, e in enumerate(dense_ranking)}
            ranked[branch] = [dict(evidenceId=e, denseScore=round(sim_of[e], 4),
                                   bm25Rank=bm_rank_of[e] + 1,
                                   denseRank=dense_rank_of[e] + 1)
                              for e in fused[:quota]]
        return ranked, timings, {b: len(self._branch_index(doc, b)[1])
                                 for b in ("text", "visual")}

    # -- generation ----------------------------------------------------------

    def _api_log(self):
        if self._log is None:
            self._log = apilog.APILog("demo-live", experiment_id="demo")
        return self._log

    def _prompt(self):
        if self._prompt_hash is None:
            with open(prompt_path(self.mode), encoding="utf-8") as fh:
                self._prompt_hash = apilog.sha(fh.read())
        return self._prompt_hash

    def generate(self, question, texts, images, question_uid, doc):
        """One call, through the same wrapper the recorded runs used."""
        from inference_wrapper import Gemini_Inference
        log = self._api_log()
        payload = dict(texts=[t["text"] for t in texts],
                       images=[i.get("img_description") or i.get("img_path")
                               for i in images])
        request_hash = apilog.request_hash(
            provider="gemini", model=self.model, mode=self.mode,
            prompt_hash=self._prompt(), question_uid=question_uid, payload=payload)
        record = apilog.make_record(
            request_hash_=request_hash, provider="gemini", model=self.model,
            mode=self.mode, question_uid=question_uid, doc_name=doc,
            experiment_id="demo", run_id="", prompt_path=prompt_path(self.mode),
            prompt_hash=self._prompt(),
            params=dict(k=K, quota=list(QUOTA), pool="canonical",
                        dense_model=self.dense_model, source="demo live mode"))
        client = Gemini_Inference(api_key=os.environ["GEMINI_API_KEY"],
                                  model=self.model, mode=self.mode)
        t0 = time.time()
        result = client.get_api_response(question_uid, question, texts, images)
        latency = time.time() - t0
        error = result.get("error")
        usage = dict(input_tokens=result.get("in_tok"),
                     output_tokens=result.get("out_tok"),
                     total_tokens=result.get("total_tok"))
        log.append(apilog.finish_record(
            record, status="error" if error else "success", latency_sec=latency,
            raw_response=result.get("response"), usage=usage, error=error))
        log.save_index()
        self.calls += 1
        if error:
            raise LiveUnavailable(f"The API call failed: {error}")
        return dict(answer=result.get("response") or "", usage=usage,
                    latencySec=round(latency, 2), requestHash=request_hash)

    # -- the whole path ------------------------------------------------------

    def answer(self, question, doc_name=None):
        self.require_ready()
        question = (question or "").strip()
        if not question:
            raise LiveUnavailable("Ask something first.")

        t0 = time.time()
        candidates = self.pick_document(question, top=5)
        if doc_name:
            if doc_name not in self._corpus["text"] and doc_name not in self._corpus["image"]:
                raise LiveUnavailable(f"No document named {doc_name!r} in the corpus.")
            chosen, method = doc_name, "chosen in the UI"
        elif candidates:
            chosen, method = candidates[0]["docName"], "BM25 over each document's own text"
        else:
            raise LiveUnavailable("No document matched that question.")

        ranked, timings, pools = self.retrieve(question, chosen)
        select_seconds = time.time() - t0

        evidence = self.store.evidence(
            [q["evidenceId"] for branch in ranked.values() for q in branch])

        # Gold is known only when the typed question IS a benchmark question.
        benchmark = self._benchmark_match(question, chosen)
        gold = set()
        if benchmark:
            row = self.store.actions.get(benchmark["questionUid"])
            gold = set(row["gold_mapped"]) if row else set()

        quotes, texts, images = [], [], []
        for branch, prefix in (("text", "text"), ("visual", "image")):
            for n, item in enumerate(ranked.get(branch, []), 1):
                ev = evidence.get(item["evidenceId"], {})
                local = f"{prefix}{n}"
                quotes.append(dict(
                    localId=local, rank=n, branch=branch, retriever="rrf",
                    evidenceId=item["evidenceId"], docName=ev.get("docName"),
                    page=ev.get("page"), layoutId=ev.get("layoutId"),
                    type=ev.get("type"),
                    isGold=item["evidenceId"] in gold,
                    cited=None,
                    denseScore=item["denseScore"], bm25Rank=item["bm25Rank"],
                    denseRank=item["denseRank"],
                    text=ev.get("text"), imgDescription=ev.get("imgDescription"),
                    imgPath=ev.get("imgPath"),
                    imageUrl=f"/api/image?path={ev['imgPath']}" if ev.get("imgPath") else None))
                if branch == "text":
                    texts.append(dict(text=ev.get("text") or ""))
                else:
                    # multimodal opens the file, so it needs the resolved path;
                    # a missing file is refused rather than quietly dropped,
                    # because dropping one would change the 4/6 quota without
                    # anything on screen saying so.
                    resolved = self.store.image_file(ev.get("imgPath"))
                    if self.mode == "multimodal" and resolved is None:
                        raise LiveUnavailable(
                            f"multimodal mode sends the images themselves, and "
                            f"{ev.get('imgPath')!r} is not on disk. Download the "
                            f"dataset images (images/README.md) or set "
                            f"MMDOCRAG_IMAGE_ROOT, or run pure-text mode.")
                    images.append(dict(img_description=ev.get("imgDescription") or "",
                                       img_path=resolved or ev.get("imgPath") or ""))

        question_uid = benchmark["questionUid"] if benchmark else (
            "live:" + hashlib.sha1(question.encode("utf-8")).hexdigest()[:12])
        generated = self.generate(question, texts, images, question_uid, chosen)

        cited = self.store._cited_labels(generated["answer"])
        for quote in quotes:
            quote["cited"] = None if cited is None else quote["localId"] in cited

        scoring = self._score(benchmark, cited, quotes, gold)
        return dict(
            mode="live",
            question=question,
            document=dict(name=chosen, method=method, candidates=candidates,
                          poolText=pools["text"], poolVisual=pools["visual"]),
            benchmarkMatch=benchmark,
            quotes=quotes,
            answer=generated["answer"],
            usage=generated["usage"],
            timings=dict(retrievalSec=round(select_seconds, 2),
                         generationSec=generated["latencySec"],
                         perStage={k: round(v, 4) for k, v in timings.items()}),
            scoring=scoring,
            config=dict(textRetriever="rrf", visualRetriever="rrf",
                        quotaText=QUOTA[0], quotaVisual=QUOTA[1], k=K,
                        pool="canonical", denseModel=self.dense_model,
                        model=self.model, mode=self.mode,
                        sendsImages=self.mode == "multimodal",
                        promptTemplate="prompt_bank/" + MODES[self.mode]),
            budget=dict(callsMade=self.calls, callsLeft=max(self.budget - self.calls, 0),
                        budget=self.budget),
            recorded=False,
            provenance=dict(
                retrieval="Live: BM25 + dense over the canonical pool, fused with "
                          f"RRF (c={RRF_C}), quota {QUOTA[0]}/{QUOTA[1]} at k={K} -- "
                          "the configuration nested CV selected, run now rather "
                          "than replayed.",
                generation=f"Live: one {self.model} call through "
                           f"inference_wrapper.Gemini_Inference in {self.mode} "
                           f"mode with prompt_bank/{MODES[self.mode]}, the same "
                           f"class and prompt files the recorded runs used"
                           + ("; the images themselves are sent, not their "
                              "descriptions." if self.mode == "multimodal"
                              else "."),
                logged="artifacts/api/demo-live/requests.jsonl",
                warning="This answer is not part of any recorded run. It was not "
                        "produced by an experiment, no experiment scored it, and "
                        "it must not be quoted as a result. The encoder "
                        "(bge-large) also differs from the recorded E29 arms "
                        "(bge-small), so the candidate block can differ from the "
                        "one that run showed the model.",
                tokens="Token counts are measured and reported verbatim from the "
                       "provider. No dollar figure is asserted here."))

    def _benchmark_match(self, question, doc):
        """Exact text match only -- gold may be attached to nothing weaker."""
        lowered = question.strip().lower()
        for uid, row in self.store.questions.items():
            if row["question"].strip().lower() == lowered and row["docName"] == doc:
                return dict(questionUid=uid, qId=row["qId"],
                            docName=row["docName"],
                            goldCount=row["goldCount"],
                            recordedInE29=uid in self.store.replayable_set)
        return None

    def check_document_selection(self, n=200, seed=7):
        """How often the first stage finds the document a question is about.

        Truth is the document the benchmark annotates for that question. This is
        a property of the live path only -- benchmark questions arrive with their
        document, so no recorded number depends on it -- but a demo that picks
        the wrong document produces a confidently wrong answer, so the rate is
        worth knowing and worth printing rather than assuming.
        """
        import random
        self._corpus_ready()
        uids = list(self.store.questions)
        random.Random(seed).shuffle(uids)
        sample = uids[:n]
        hits = {1: 0, 3: 0, 5: 0}
        for uid in sample:
            row = self.store.questions[uid]
            names = [h["docName"] for h in self.pick_document(row["question"], top=5)]
            for cut in hits:
                if row["docName"] in names[:cut]:
                    hits[cut] += 1
        total = len(sample) or 1
        return dict(n=len(sample), seed=seed,
                    top1=hits[1] / total, top3=hits[3] / total, top5=hits[5] / total)

    def _score(self, benchmark, cited, quotes, gold):
        """A diagnostic, and only where gold exists."""
        if not benchmark or cited is None:
            return dict(scored=False, reason=(
                "This question is not in the benchmark, so there is no gold "
                "evidence to score the answer against. Retrieval and generation "
                "are real; the evaluation is the part that cannot exist here."))
        from eval_all import get_scores
        # Gold that retrieval never surfaced gets a sentinel label nothing can
        # match, so it stays in the denominator as a miss -- the same trick
        # eval_e29_paired uses, and what makes this F1 sensitive to retrieval.
        local_of = {q["evidenceId"]: q["localId"] for q in quotes}
        labels = [local_of.get(e, "unretrieved:" + e) for e in gold]
        # Predictions are passed through unfiltered. A citation to a quote the
        # model was never given is a false positive, exactly as it is in the
        # recorded path; filtering those out would quietly inflate precision and
        # make this number stop meaning what E29's means.
        precision, recall, f1 = get_scores(labels, sorted(cited))
        return dict(
            scored=True, precision=round(precision, 4), recall=round(recall, 4),
            f1=round(f1, 4),
            goldTotal=len(gold),
            goldRetrieved=sum(1 for q in quotes if q["isGold"]),
            metric="quote-selection F1, computed now with eval_all's scorer",
            warning="Computed live over a retrieval no run performed. It is not "
                    "E29's number, it is not comparable to E29's arms, and it is "
                    "recorded nowhere.")


def main():
    """Diagnostics that need no API key and spend nothing.

        python -m demo.live --check-document-selection
    """
    import argparse
    from demo.store import Store

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check-document-selection", action="store_true")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    engine = LiveEngine(Store(verbose=False), budget=0)
    if args.check_document_selection:
        result = engine.check_document_selection(n=args.n, seed=args.seed)
        print(f"document selection, {result['n']} benchmark questions "
              f"(seed {result['seed']}), truth = the annotated document:")
        for cut in (1, 3, 5):
            print(f"  top{cut}  {result[f'top{cut}']:.1%}")
        print("Live mode only. A benchmark question already carries its "
              "document, so no recorded number depends on this stage.")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
