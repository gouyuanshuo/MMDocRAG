"""Read-only access to what this project recorded, shaped for the console.

Every value the demo shows comes from an artifact on disk. Three of them do the
work:

    dataset/evaluation_{ours,paper}k10.jsonl   the candidate block each arm's
        generator actually saw, and the gold labels it was scored against
    response/gemini-3.6-flash_pure-text_quotes{ours,paper}k10_response.jsonl
        the answers that run produced, replayed verbatim
    router/cache/actions_canonical_bge-small-en-v1.5.pkl
        every retriever's ranking for all 2,000 questions, from E27's builder

The arm files carry local quote ids ("text3", "image7") and no evidence ids, so
a page number cannot be read off them. Reconstructing each arm's block from the
action table -- same builder, same pool, same encoder, same quota -- recovers
the evidence id behind every quote, and `tests/test_demo.py` asserts that the
reconstruction reproduces all 1,200 arm rows exactly. Without that assertion the
page numbers in the UI would be a guess.

What is *not* here: any recomputation of a headline number. Per-question F1 is
read from the run that measured it, intervals are read from that run's metrics,
and a missing artifact becomes a visible error rather than a fallback value.
"""

import collections
import csv
import io
import json
import os
import pickle
import sqlite3
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from demo import config as C  # noqa: E402


def _read_jsonl(path):
    with io.open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _read_csv(path):
    # Written by expkit with a BOM; utf-8-sig keeps the first header name clean.
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


class MissingArtifact(Exception):
    pass


class Store:
    """Loads once, serves many. Thread-safe for the lazy parts."""

    def __init__(self, metrics_run=None, image_root=None, verbose=True):
        self.metrics_run = metrics_run or C.METRICS_RUN
        self.image_root = image_root or C.IMAGE_ROOT
        self.verbose = verbose
        self.errors = []          # artifact-level problems, surfaced by /api/health
        self._lock = threading.Lock()
        self._actions = None
        self._bm25 = None
        self._citation_reader = None
        self._registry = None

        self._load_questions()
        self._load_arms()
        self._load_recorded_f1()
        self._load_router_decisions()
        self._load_metrics()

    # -- loading -------------------------------------------------------------

    def _fail(self, what, exc):
        message = f"{what}: {exc.__class__.__name__}: {exc}"
        self.errors.append(message)
        if self.verbose:
            print("[demo] MISSING " + message, flush=True)

    def _load_questions(self):
        self.questions = {}
        self.qid_to_uid = {}
        self.documents = collections.Counter()
        try:
            con = sqlite3.connect(C.CANONICAL_DB)
            rows = con.execute(
                "SELECT question_uid, q_id, doc_name, domain, question, "
                "       question_type, evidence_modality_type, answer_short "
                "FROM questions WHERE split = ? ORDER BY q_id", (C.EVAL_SPLIT,)).fetchall()
            gold = dict(con.execute(
                "SELECT question_uid, COUNT(*) FROM question_gold_evidence "
                "WHERE setting = '20' GROUP BY question_uid").fetchall())
            con.close()
        except sqlite3.Error as exc:
            self._fail(C.CANONICAL_DB, exc)
            return
        for uid, qid, doc, domain, question, qtype, modality, short in rows:
            try:
                modality_list = json.loads(modality) if modality else []
            except ValueError:
                modality_list = [modality] if modality else []
            self.questions[uid] = dict(
                questionUid=uid, qId=qid, docName=doc, domain=domain,
                question=question, questionType=qtype,
                evidenceModality=modality_list, answerShort=short,
                goldCount=gold.get(uid, 0))
            self.qid_to_uid[qid] = uid
            self.documents[doc] += 1

    def _load_arms(self):
        """Candidate blocks and replayed answers, keyed by question_uid."""
        self.arms = {}
        self.replayable = []
        for name in C.ARM_ORDER:
            spec = C.ARMS[name]
            try:
                blocks = _read_jsonl(spec["eval_jsonl"])
                answers = _read_jsonl(spec["response_jsonl"])
            except OSError as exc:
                self._fail(f"arm {name}", exc)
                continue
            by_qid = {r["q_id"]: r for r in blocks}
            resp = {r["q_id"]: r for r in answers}
            if set(by_qid) != set(resp):
                self._fail(f"arm {name}", ValueError(
                    "response file does not cover the arm's question set; "
                    "a partial arm would silently change the denominator"))
            self.arms[name] = dict(spec=spec, blocks=by_qid, answers=resp)
        if self.arms:
            shared = set.intersection(*(set(a["blocks"]) for a in self.arms.values()))
            self.replayable = sorted(
                self.qid_to_uid[q] for q in shared if q in self.qid_to_uid)
        self.replayable_set = set(self.replayable)

    def _load_recorded_f1(self):
        """Per-question F1 for both arms, as the recorded run measured it."""
        self.recorded_f1 = {}
        self.f1_provenance = {}
        try:
            rows = _read_csv(C.E29_PER_QUESTION)
        except OSError as exc:
            self._fail("E29 per-question F1", exc)
            return
        for row in rows:
            raw = row.get("question_uid", "")
            uid = raw if ":" in raw else self.qid_to_uid.get(_int(raw))
            if uid is None:
                continue
            self.recorded_f1[uid] = dict(
                ours=_num(row.get("f1_ours")), paper=_num(row.get("f1_paper")),
                delta=_num(row.get("delta")))
        if rows:
            first = rows[0]
            self.f1_provenance = {k: first.get(k) for k in (
                "model", "mode", "k", "n_questions", "sample_unit", "n_documents",
                "bootstrap", "estimator", "scorer", "comparable_to_paper")}
            self.f1_provenance["source"] = os.path.relpath(C.E29_PER_QUESTION, C.REPO_ROOT)

    def _load_router_decisions(self):
        """E36's escalation decisions -- read, never re-derived (see config)."""
        self.router = {}
        self.router_config = {}
        self.router_rates = {}
        try:
            rows = _read_csv(C.ROUTER_DECISIONS)
        except OSError as exc:
            self._fail("router per-question decisions", exc)
            rows = []
        counts = collections.Counter()
        for row in rows:
            uid = row.get("question_uid")
            if not uid:
                continue
            decision = dict(
                recallCheap=_num(row.get("recall_cheap")),
                recallExpensive=_num(row.get("recall_expensive")),
                trueGain=_num(row.get("true_gain")),
                predictedGain=_num(row.get("predicted_gain")),
                escalate={b: row.get(f"escalate_at_B{b}") == "1"
                          for b in ("005", "015", "050")})
            self.router[uid] = decision
            for b, flag in decision["escalate"].items():
                counts[b] += int(flag)
        if rows:
            first = rows[0]
            self.router_config = {k: first.get(k) for k in (
                "experiment", "pool", "k", "quota", "quota_family", "dense_model",
                "policy", "features", "n_features", "folds", "inner_folds",
                "cheap_action", "expensive_action", "sample_unit")}
            self.router_config["n_questions"] = len(self.router)
            self.router_config["source"] = os.path.relpath(C.ROUTER_DECISIONS, C.REPO_ROOT)
            self.router_rates = {b: counts[b] / len(self.router) for b in counts}
        try:
            with io.open(C.E39_PLAN, encoding="utf-8") as fh:
                self.e39_plan = json.load(fh)
        except OSError:
            self.e39_plan = {}

    def _load_metrics(self):
        self.metrics = []
        self.metrics_meta = {}
        self.metrics_fallback = None
        try:
            self.metrics = _read_jsonl(C.metrics_path(self.metrics_run))
        except OSError as exc:
            # A run the caller asked for by name is never substituted -- that is
            # the difference between "this run measured it" and "some run did".
            # The default is allowed to fall back to the newest run on disk,
            # because a fresh clone has different run ids, and the run actually
            # used is printed and served either way.
            substitute = self._newest_run() if self.metrics_run == C.METRICS_RUN else None
            if substitute is None:
                self._fail(f"metrics run {self.metrics_run}", exc)
            else:
                self.metrics_fallback = dict(requested=self.metrics_run, used=substitute)
                self.metrics_run = substitute
                self.metrics = _read_jsonl(C.metrics_path(substitute))
                if self.verbose:
                    print(f"[demo] metrics run {self.metrics_fallback['requested']} "
                          f"is absent; using {substitute}", flush=True)
        try:
            with io.open(C.run_json(self.metrics_run), encoding="utf-8") as fh:
                run = json.load(fh)
            self.metrics_meta = {k: run.get(k) for k in
                                 ("run_id", "started_utc", "finished_utc", "suite",
                                  "offline", "python", "platform", "git_head")}
        except (OSError, ValueError):
            self.metrics_meta = {"run_id": self.metrics_run}
        if self.metrics_fallback:
            self.metrics_meta["substituted_for"] = self.metrics_fallback["requested"]

    @staticmethod
    def _newest_run():
        root = os.path.join(C.REPO_ROOT, "artifacts", "runs")
        try:
            candidates = [name for name in os.listdir(root)
                          if os.path.isfile(os.path.join(root, name, "metrics.jsonl"))]
        except OSError:
            return None
        return sorted(candidates)[-1] if candidates else None

    # -- lazy inputs ---------------------------------------------------------

    @property
    def actions(self):
        """Per-question rankings for every retriever, from E27's builder."""
        with self._lock:
            if self._actions is None:
                try:
                    with open(C.ACTION_TABLE, "rb") as fh:
                        blob = pickle.load(fh)
                    self._actions = {r["quid"]: r for r in blob["rows"]}
                    self.action_meta = dict(
                        pool=blob["meta"].get("pool"),
                        denseModel=blob["meta"].get("dense_model"),
                        top=blob.get("top"),
                        nQuestions=blob["meta"].get("n_questions"),
                        source=os.path.relpath(C.ACTION_TABLE, C.REPO_ROOT))
                except (OSError, KeyError, pickle.UnpicklingError) as exc:
                    self._fail("action table", exc)
                    self._actions = {}
                    self.action_meta = {}
        return self._actions

    @property
    def question_index(self):
        """BM25 over the 2,000 question strings, using this project's own BM25."""
        with self._lock:
            if self._bm25 is None:
                from retrieval.bm25 import BM25
                from retrieval.corpus import tokenize
                uids = list(self.questions)
                self._bm25 = (BM25([tokenize(self.questions[u]["question"]) for u in uids]),
                              uids, tokenize)
        return self._bm25

    def _cited_labels(self, answer):
        """Which local quote ids an answer cited, via eval_all's own extractor.

        Imported lazily: eval_all pulls in nltk and rouge_score, and one of those
        can try to download a corpus. If the import fails the demo drops the
        cited-quote highlight and says so -- it does not fall back to a private
        regex, because a second extractor would quietly stop agreeing with the
        F1 the recorded run measured.
        """
        if self._citation_reader is None:
            try:
                from eval_all import extract_citations, strip_thinking
                self._citation_reader = (extract_citations, strip_thinking)
            except Exception as exc:                      # noqa: BLE001
                self._fail("eval_all citation extractor", exc)
                self._citation_reader = False
        if not self._citation_reader:
            return None
        extract_citations, strip_thinking = self._citation_reader
        return set(extract_citations(strip_thinking(answer or ""))[2])

    # -- questions -----------------------------------------------------------

    def question(self, uid):
        return self.questions.get(uid)

    def search(self, text, limit=20, replayable_only=False):
        text = (text or "").strip()
        pool = [u for u in self.questions
                if not replayable_only or u in self.replayable_set]
        if not text:
            return [dict(self.questions[u], matchScore=None) for u in pool[:limit]]
        bm25, uids, tokenize = self.question_index
        order, scores = bm25.rank(tokenize(text))
        allowed = set(pool)
        out = []
        for i in order:
            uid = uids[int(i)]
            if uid not in allowed:
                continue
            out.append(dict(self.questions[uid], matchScore=round(float(scores[int(i)]), 4)))
            if len(out) >= limit:
                break
        return out

    def match(self, text, replayable_only=True):
        """The benchmark question a free-text input replays.

        Exact text wins; otherwise BM25 picks the closest, and the caller is
        told the score so the UI can label it as a match rather than pretend the
        user's own question was answered.
        """
        text = (text or "").strip()
        lowered = text.lower()
        allowed = self.replayable_set if replayable_only else set(self.questions)
        for uid in (self.replayable if replayable_only else self.questions):
            if self.questions[uid]["question"].strip().lower() == lowered:
                return dict(questionUid=uid, method="exact", score=None, exact=True)
        hits = [h for h in self.search(text, limit=1, replayable_only=replayable_only)
                if h["questionUid"] in allowed]
        if not hits:
            return None
        return dict(questionUid=hits[0]["questionUid"], method="bm25",
                    score=hits[0]["matchScore"], exact=False)

    # -- evidence ------------------------------------------------------------

    def evidence(self, evidence_ids):
        """canonical_evidence rows for a list of ids, keyed by id."""
        if not evidence_ids:
            return {}
        con = sqlite3.connect(C.CANONICAL_DB)
        marks = ",".join("?" * len(evidence_ids))
        rows = con.execute(
            f"SELECT evidence_id, doc_name, page_id, layout_id, type, modality, "
            f"text, img_path, img_description FROM canonical_evidence "
            f"WHERE evidence_id IN ({marks})", list(evidence_ids)).fetchall()
        con.close()
        out = {}
        for eid, doc, page, layout, kind, modality, text, img, desc in rows:
            out[eid] = dict(evidenceId=eid, docName=doc, page=page, layoutId=layout,
                            type=kind, modality=modality, text=text,
                            imgPath=img, imgDescription=desc)
        return out

    def image_file(self, img_path):
        """Absolute path for an `img_path`, or None if it escapes the root."""
        if not img_path:
            return None
        root = os.path.abspath(self.image_root)
        full = os.path.abspath(os.path.join(root, img_path.replace("/", os.sep)))
        if os.path.commonpath([root, full]) != root or not os.path.isfile(full):
            return None
        return full

    # -- the replay ----------------------------------------------------------

    def _quotes_for_arm(self, uid, arm_name, cited):
        """One arm's candidate block, with the evidence behind every quote."""
        spec = C.ARMS[arm_name]
        row = self.actions.get(uid)
        if row is None:
            return [], {}
        quota_text, quota_visual = spec["quota"]
        text_ids = row["rank"][spec["text_retriever"]]["text"][:quota_text]
        image_ids = row["rank"][spec["visual_retriever"]]["visual"][:quota_visual]
        records = self.evidence(list(text_ids) + list(image_ids))
        gold = row["gold_mapped"]
        quotes = []
        for branch, ids, prefix in (("text", text_ids, "text"),
                                    ("visual", image_ids, "image")):
            for n, eid in enumerate(ids, 1):
                local = f"{prefix}{n}"
                ev = records.get(eid, {})
                quotes.append(dict(
                    localId=local, rank=n, branch=branch,
                    retriever=spec["text_retriever"] if branch == "text"
                    else spec["visual_retriever"],
                    evidenceId=eid, docName=ev.get("docName"), page=ev.get("page"),
                    layoutId=ev.get("layoutId"), type=ev.get("type"),
                    isGold=eid in gold,
                    cited=None if cited is None else local in cited,
                    text=ev.get("text"), imgDescription=ev.get("imgDescription"),
                    imgPath=ev.get("imgPath"),
                    imageUrl=f"/api/image?path={ev['imgPath']}"
                    if ev.get("imgPath") else None))
        retrieved_gold = sum(1 for q in quotes if q["isGold"])
        counts = dict(
            goldTotal=int(row["n_total"]),
            goldMapped=int(row["n_total"]) - int(row["n_unmapped"]),
            goldUnmapped=int(row["n_unmapped"]),
            goldRetrieved=retrieved_gold,
            quotesShown=len(quotes),
            quotaText=quota_text, quotaVisual=quota_visual)
        return quotes, counts

    def replay(self, uid):
        """Everything the recorded run holds about one benchmark question."""
        question = self.questions.get(uid)
        if question is None:
            return None
        qid = question["qId"]
        row = self.actions.get(uid)
        out = dict(question, replayable=uid in self.replayable_set, arms={},
                   routing=self.routing(uid),
                   provenance=dict(
                       generation=dict(C.GENERATION),
                       actionTable=getattr(self, "action_meta", {}),
                       f1=self.f1_provenance))
        if row is not None:
            out["retrieval"] = dict(
                poolText=int(row["scores"]["text"]["n_pool"]),
                poolVisual=int(row["scores"]["visual"]["n_pool"]),
                goldTotal=int(row["n_total"]),
                goldUnmapped=int(row["n_unmapped"]),
                goldText=len(row["gold_text"]),
                goldVisual=len(row["gold_visual"]),
                hasColqwen=bool(row["has_colqwen"]))
        recorded = self.recorded_f1.get(uid, {})
        for name in C.ARM_ORDER:
            arm = self.arms.get(name)
            if arm is None:
                continue
            answer_row = arm["answers"].get(qid)
            answer = (answer_row or {}).get("response")
            cited = self._cited_labels(answer) if answer else None
            quotes, counts = self._quotes_for_arm(uid, name, cited)
            spec = arm["spec"]
            out["arms"][name] = dict(
                label=spec["label"], description=spec["desc"],
                config=dict(textRetriever=spec["text_retriever"],
                            visualRetriever=spec["visual_retriever"],
                            quotaText=spec["quota"][0], quotaVisual=spec["quota"][1],
                            k=C.GENERATION["k"], pool=C.GENERATION["pool"],
                            denseModel=C.GENERATION["dense_model"]),
                answer=answer,
                answerAvailable=answer is not None,
                tokens=None if not answer_row else dict(
                    inTok=answer_row.get("in_tok"), outTok=answer_row.get("out_tok"),
                    totalTok=answer_row.get("total_tok"), model=answer_row.get("model")),
                citedLocalIds=sorted(cited) if cited else ([] if cited == set() else None),
                quotes=quotes, counts=counts,
                citationF1=recorded.get(name))
        if len(out["arms"]) == 2 and recorded:
            out["paired"] = dict(
                deltaF1=recorded.get("delta"),
                metric="quote-selection F1 (which evidence the answer cited)",
                notAnswerCorrectness=True)
        return out

    def routing(self, uid):
        """E36's per-question decision, plus what it would have bought."""
        decision = self.router.get(uid)
        if decision is None:
            return None
        return dict(decision, config=self.router_config, rates=self.router_rates)

    def retriever_comparison(self, uid, k=10):
        """What each retriever would have put in the top k, per branch."""
        row = self.actions.get(uid)
        if row is None:
            return None
        gold = row["gold_mapped"]
        out = {}
        for branch in ("text", "visual"):
            entries = []
            for retriever, ranks in row["rank"].items():
                # The builder aliases colqwen's text branch to dense's ranking so
                # an action pair can be scored; ColQwen never ranks text. Showing
                # it as a text retriever would be a mislabel.
                if retriever == "colqwen" and branch == "text":
                    continue
                ranked = ranks.get(branch) or []
                if not ranked:
                    continue
                top = list(ranked[:k])
                entries.append(dict(
                    retriever=retriever,
                    readsPixels=retriever == "colqwen" and branch == "visual",
                    representation="raw image pixels"
                    if (retriever == "colqwen" and branch == "visual")
                    else ("VLM-written image descriptions" if branch == "visual"
                          else "document text chunks"),
                    goldInTopK=sum(1 for e in top if e in gold),
                    topK=[dict(evidenceId=e, isGold=e in gold) for e in top]))
            out[branch] = dict(
                pool=int(row["scores"][branch]["n_pool"]),
                goldTotal=len(row["gold_text"] if branch == "text" else row["gold_visual"]),
                retrievers=sorted(entries, key=lambda e: -e["goldInTopK"]))
        return out

    # -- metrics -------------------------------------------------------------

    def find(self, experiment, name=None, **filters):
        """Metric rows from the recorded run, filtered on their own fields."""
        out = []
        for row in self.metrics:
            if row.get("experiment") != experiment:
                continue
            if name is not None and row.get("name") != name:
                continue
            if any(row.get(key) != value for key, value in filters.items()):
                continue
            out.append(row)
        return out

    def one(self, experiment, name, **filters):
        hits = self.find(experiment, name, **filters)
        return hits[0] if hits else None

    def registry(self):
        """experiments.py itself: id, status, lifecycle, title, current result."""
        if self._registry is None:
            try:
                import experiments as X
                rows = []
                for entry in X.E:
                    meta = X.META.get(entry["id"], {})
                    rows.append(dict(
                        id=entry["id"], phase=entry.get("phase"),
                        status=entry.get("status"),
                        statusLabel=X.STATUS_LABEL.get(entry.get("status"), entry.get("status")),
                        lifecycle=meta.get("lifecycle"),
                        title=entry.get("title"),
                        asks=entry.get("asks"),
                        suites=list(meta.get("suites", ())),
                        hasCorrections=bool(entry.get("superseded") or entry.get("corrections")),
                        result=_latest_result(entry),
                        limits=entry.get("limits")))
                self._registry = rows
            except Exception as exc:                      # noqa: BLE001
                self._fail("experiments registry", exc)
                self._registry = []
        return self._registry

    # -- provenance ----------------------------------------------------------

    def provenance(self):
        images_ok = os.path.isdir(self.image_root)
        return dict(
            mode="replay",
            claim="Every number and every answer here was recorded by a run in "
                  "artifacts/. The demo reads them; it calls no model and "
                  "computes no new result.",
            generation=dict(C.GENERATION, arms={
                name: dict(label=spec["label"], description=spec["desc"],
                           textRetriever=spec["text_retriever"],
                           visualRetriever=spec["visual_retriever"],
                           quota=list(spec["quota"]))
                for name, spec in C.ARMS.items()}),
            retrieval=dict(
                actionTable=getattr(self, "action_meta", {}) or dict(
                    source=os.path.relpath(C.ACTION_TABLE, C.REPO_ROOT),
                    pool=C.ACTION_POOL, denseModel=C.ACTION_DENSE_MODEL),
                note="Rankings come from retrieval.eval_stack_v2.build, the same "
                     "builder E27 reports; unmapped gold counts as a miss."),
            router=dict(self.router_config, escalationRates=self.router_rates,
                        plan={k: self.e39_plan.get(k) for k in
                              ("status", "exploratory", "budget_population",
                               "n_escalated_subset", "escalation_rate_subset",
                               "api_calls_made", "noninferiority_margin_f1_points",
                               "margin_status")} if self.e39_plan else {}),
            metricsRun=self.metrics_meta,
            counts=dict(questions=len(self.questions),
                        documents=len(self.documents),
                        replayable=len(self.replayable),
                        metrics=len(self.metrics)),
            imageRoot=dict(path=self.image_root, available=images_ok,
                           note="14,826 JPEGs, downloaded separately; see "
                                "images/README.md" if not images_ok else None),
            caveats=list(C.CAVEATS),
            errors=list(self.errors))


def _latest_result(entry):
    """The registry appends result2, result3...; the last one is current."""
    keys = sorted((k for k in entry if k.startswith("result")),
                  key=lambda k: (len(k), k))
    return entry.get(keys[-1]) if keys else None


def _int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None
