"""The demo API, and the built UI it serves alongside it.

    python -m demo.server                 # http://127.0.0.1:8000
    python -m demo.server --port 8001
    python -m demo.server --no-static     # API only, for `npm run dev` on :3000
    python -m demo.server --live          # also allow live, paid answers

Standard library only, because the research environment already carries enough
version-pinned weight and a demo that cannot start is worse than no demo. It
binds to the loopback interface and allows browser origins on localhost only:
the payloads carry a research corpus and per-question model output, and none of
that should become reachable from the network by accident.

Every route reads recorded artifacts through `demo.store`, with exactly one
exception: `POST /api/live`, which exists only when the server was started with
`--live`. That route runs retrieval for real and makes one paid API call per
question, and it is the only place in this package that produces something no
run recorded. Its answers are labelled that way in the payload and in the UI,
they are never scored as an experiment, and every attempt is written to
`artifacts/api/demo-live/requests.jsonl` before the answer is returned.

Without `--live` the server is what it was: a reader.
"""

import argparse
import json
import mimetypes
import os
import posixpath
import sys
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from demo import config as C          # noqa: E402
from demo import dashboard            # noqa: E402
from demo.store import Store          # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

STATIC_ROOT = os.path.join(C.REPO_ROOT, "webui", "dist")
MAX_BODY = 16384
MAX_CONVERSATIONS = 200
MAX_TURNS = 50

STORE = None
LIVE = None                 # a LiveEngine only when --live was passed
CONVERSATIONS = {}
LOCK = threading.Lock()
LIVE_LOCK = threading.Lock()


# -- payload shaping ---------------------------------------------------------

def _citations(arm):
    """The teammate UI's citation shape, widened with what we can prove."""
    out = []
    for quote in (arm or {}).get("quotes", []):
        out.append(dict(
            id=quote["localId"],
            localId=quote["localId"],
            evidenceId=quote["evidenceId"],
            documentName=quote["docName"],
            page=quote["page"],
            type="visual" if quote["branch"] == "visual" else "text",
            branch=quote["branch"],
            retriever=quote["retriever"],
            rank=quote["rank"],
            isGold=quote["isGold"],
            cited=quote["cited"],
            snippet=(quote.get("text") or quote.get("imgDescription") or "")[:600],
            imageUrl=quote.get("imageUrl")))
    return out


def _routing(replay):
    """The routing panel: the static configuration, then the per-question part.

    The configuration is not chosen per question -- nested CV selected one
    configuration for every question, and saying otherwise would sell a result
    this project did not get. What *is* per question is E36's escalation
    decision, so it is reported separately and labelled as a cost decision.
    """
    arm = (replay.get("arms") or {}).get("ours") or {}
    config = arm.get("config") or {}
    per_question = replay.get("routing")
    return dict(
        static=dict(
            textRetriever=config.get("textRetriever"),
            visualRetriever=config.get("visualRetriever"),
            quotaText=config.get("quotaText"),
            quotaVisual=config.get("quotaVisual"),
            topK=config.get("k"),
            pool=config.get("pool"),
            denseModel=config.get("denseModel"),
            selectedBy="nested cross-validation, document-grouped folds; the same "
                       "configuration won in all five folds",
            perQuestion=False),
        perQuestion=per_question,
        note="The retrieval configuration is static -- one configuration for "
             "every question. The per-question decision this project measured is "
             "whether to escalate to the GPU visual retriever, and it is a cost "
             "result: E36 found the CPU fusion decision unlearnable.")


def _turn(store, question_text, match, query_id, turn_id):
    replay = store.replay(match["questionUid"])
    ours = (replay.get("arms") or {}).get("ours") or {}
    paper = (replay.get("arms") or {}).get("paper") or {}
    return dict(
        queryId=query_id, turnId=turn_id, status="completed",
        question=question_text,
        match=dict(match, question=replay.get("question"),
                   docName=replay.get("docName")),
        answer=ours.get("answer"),
        answerAvailable=bool(ours.get("answer")),
        citations=_citations(ours),
        routing=_routing(replay),
        replay=replay,
        baseline=dict(
            label=paper.get("label"), answer=paper.get("answer"),
            citations=_citations(paper), citationF1=paper.get("citationF1"),
            config=paper.get("config")),
        metrics=dict(
            citationF1=ours.get("citationF1"),
            baselineCitationF1=paper.get("citationF1"),
            deltaF1=(replay.get("paired") or {}).get("deltaF1"),
            counts=ours.get("counts"),
            tokens=ours.get("tokens"),
            metric="quote-selection F1 (which evidence the answer cited); "
                   "not answer correctness, not faithfulness"),
        provenance=replay.get("provenance"))


# -- HTTP --------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "MMDocRAG-demo"
    quiet = True

    def log_message(self, fmt, *args):
        if not self.quiet:
            super().log_message(fmt, *args)

    # -- helpers

    def _cors(self):
        origin = self.headers.get("Origin", "")
        parsed = urllib.parse.urlparse(origin)
        if parsed.scheme in ("http", "https") and parsed.hostname in ("localhost", "127.0.0.1"):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def reply(self, status, data):
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_file(self, path, cache="no-store"):
        try:
            with open(path, "rb") as fh:
                body = fh.read()
        except OSError:
            return self.reply(404, {"detail": "File not found"})
        kind = mimetypes.guess_type(path)[0] or "application/octet-stream"
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_OPTIONS(self):
        self.reply(200, {})

    # -- routes

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(url.query)
        path = url.path
        parts = [p for p in path.strip("/").split("/") if p]

        if not path.startswith("/api/"):
            return self.serve_static(path)

        if path == "/api/health":
            return self.reply(200, dict(
                status="ok" if not STORE.errors else "degraded",
                mode="replay",
                questions=len(STORE.questions),
                replayable=len(STORE.replayable),
                metricsRun=STORE.metrics_meta.get("run_id"),
                live=LIVE.status() if LIVE else dict(
                    enabled=False,
                    note="Live mode is off. Start the server with --live to run "
                         "retrieval and call the API for a typed question; every "
                         "live answer is a paid request."),
                errors=STORE.errors))

        if path == "/api/documents":
            term = query.get("search", [""])[0].strip().lower()
            items = [dict(docName=doc, questions=n)
                     for doc, n in sorted(STORE.documents.items())
                     if not term or term in doc.lower()]
            limit = _clamp(query.get("limit", ["30"])[0], 1, 240, 30)
            return self.reply(200, dict(items=items[:limit], total=len(items)))

        if path == "/api/provenance":
            return self.reply(200, STORE.provenance())

        if path == "/api/questions":
            limit = _clamp(query.get("limit", ["25"])[0], 1, 200, 25)
            replayable = query.get("replayable", ["true"])[0] != "false"
            hits = STORE.search(query.get("search", [""])[0], limit=limit,
                                replayable_only=replayable)
            return self.reply(200, dict(
                items=hits, total=len(STORE.replayable) if replayable
                else len(STORE.questions),
                replayableOnly=replayable))

        if path == "/api/queries":
            with LOCK:
                runs = [dict(queryId=c["queryId"], question=c["title"],
                             turns=len(c["turns"]))
                        for c in reversed(list(CONVERSATIONS.values()))]
            return self.reply(200, {"runs": runs})

        if len(parts) == 3 and parts[:2] == ["api", "queries"]:
            with LOCK:
                conversation = CONVERSATIONS.get(parts[2])
            if not conversation:
                return self.reply(404, {"detail": "Conversation not found. Start a new query."})
            return self.reply(200, conversation)

        if len(parts) == 4 and parts[:2] == ["api", "queries"] and parts[3] == "analysis":
            with LOCK:
                conversation = CONVERSATIONS.get(parts[2])
            if not conversation or not conversation["turns"]:
                return self.reply(404, {"detail": "Query not found. Send a question first."})
            return self.reply(200, conversation["turns"][-1])

        if path == "/api/experiments":
            return self.reply(200, dict(
                groups=[dict(id=g, title=dashboard.build(STORE, g)["title"])
                        for g in C.GROUPS],
                registry=STORE.registry(),
                run=STORE.metrics_meta))

        if len(parts) == 4 and parts[:2] == ["api", "experiments"] and parts[3] == "results":
            group = query.get("group", ["end-to-end"])[0]
            payload = dashboard.build(STORE, group)
            if payload is None:
                return self.reply(400, {"detail": f"Unknown group '{group}'. "
                                                  f"Valid: {', '.join(C.GROUPS)}"})
            return self.reply(200, payload)

        if len(parts) == 3 and parts[:2] == ["api", "replay"]:
            uid = urllib.parse.unquote(parts[2])
            replay = STORE.replay(uid)
            if replay is None:
                return self.reply(404, {"detail": f"No such question: {uid}"})
            return self.reply(200, replay)

        if len(parts) == 3 and parts[:2] == ["api", "retrievers"]:
            uid = urllib.parse.unquote(parts[2])
            k = _clamp(query.get("k", ["10"])[0], 1, 32, 10)
            data = STORE.retriever_comparison(uid, k=k)
            if data is None:
                return self.reply(404, {"detail": f"No rankings for {uid}"})
            return self.reply(200, dict(questionUid=uid, k=k, branches=data,
                                        source=getattr(STORE, "action_meta", {})))

        if path == "/api/image":
            img_path = query.get("path", [""])[0]
            full = STORE.image_file(img_path)
            if full is None:
                return self.reply(404, {
                    "detail": "Image not available. The 14,826 JPEGs are "
                              "downloaded separately; see images/README.md, then "
                              "set MMDOCRAG_IMAGE_ROOT."})
            return self.send_file(full, cache="public, max-age=3600")

        return self.reply(404, {"detail": f"Route not found: {path}"})

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        if self.path == "/api/live":
            return self.do_live()
        if self.path != "/api/chat":
            return self.reply(404, {"detail": "Route not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.reply(400, {"detail": "Invalid Content-Length"})
        if not 0 < length <= MAX_BODY:
            return self.reply(413, {"detail": f"Request must be 1-{MAX_BODY} bytes"})
        try:
            payload = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeError):
            return self.reply(400, {"detail": "Invalid JSON body"})
        if not isinstance(payload, dict):
            return self.reply(400, {"detail": "Body must be a JSON object"})

        question = payload.get("question")
        if not isinstance(question, str) or not question.strip() or len(question) > 2000:
            return self.reply(400, {
                "detail": "question must be a non-empty string of at most 2000 characters"})
        question = question.strip()
        query_id = payload.get("queryId")
        if query_id is not None and (not isinstance(query_id, str) or not query_id):
            return self.reply(400, {"detail": "queryId must be a non-empty string"})

        uid = payload.get("questionUid")
        if isinstance(uid, str) and uid in STORE.questions:
            match = dict(questionUid=uid, method="selected", score=None, exact=True)
        else:
            match = STORE.match(question)
        if match is None:
            return self.reply(404, {
                "detail": "No benchmark question matched. This console replays "
                          "the 600 questions the recorded end-to-end run covered; "
                          "it does not generate new answers."})

        turn = _turn(STORE, question, match,
                     query_id or "q_" + uuid.uuid4().hex[:12],
                     "t_" + uuid.uuid4().hex[:12])

        with LOCK:
            conversation = CONVERSATIONS.get(query_id) if query_id else None
            if query_id and conversation is None:
                return self.reply(404, {
                    "detail": "Conversation not found. Click New query to start again."})
            if conversation and len(conversation["turns"]) >= MAX_TURNS:
                return self.reply(409, {
                    "detail": f"This conversation reached {MAX_TURNS} turns. Start a new query."})
            key = turn["queryId"]
            previous = conversation["turns"] if conversation else []
            if not conversation and len(CONVERSATIONS) >= MAX_CONVERSATIONS:
                CONVERSATIONS.pop(next(iter(CONVERSATIONS)))
            CONVERSATIONS.pop(key, None)
            CONVERSATIONS[key] = dict(
                queryId=key, title=conversation["title"] if conversation else question,
                created=conversation["created"] if conversation else time.time(),
                turns=[*previous, turn])
        return self.reply(200, turn)

    # -- live

    def do_live(self):
        """One real retrieval and one real API call. Serialised on purpose.

        Two people clicking at once would be two paid requests and two encoder
        loads competing for the same weights, so the lock makes the budget in
        LiveEngine mean what it says.
        """
        if LIVE is None:
            return self.reply(503, {
                "detail": "Live mode is off on this server. Restart it with "
                          "--live to run retrieval and call the API; every live "
                          "answer is a paid request."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.reply(400, {"detail": "Invalid Content-Length"})
        if not 0 < length <= MAX_BODY:
            return self.reply(413, {"detail": f"Request must be 1-{MAX_BODY} bytes"})
        try:
            payload = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeError):
            return self.reply(400, {"detail": "Invalid JSON body"})
        question = (payload or {}).get("question") if isinstance(payload, dict) else None
        if not isinstance(question, str) or not question.strip() or len(question) > 2000:
            return self.reply(400, {
                "detail": "question must be a non-empty string of at most 2000 characters"})
        doc_name = payload.get("docName")
        if doc_name is not None and not isinstance(doc_name, str):
            return self.reply(400, {"detail": "docName must be a string"})

        from demo.live import LiveUnavailable
        with LIVE_LOCK:
            try:
                result = LIVE.answer(question.strip(), doc_name or None)
            except LiveUnavailable as exc:
                return self.reply(409, {"detail": str(exc)})
            except Exception as exc:                          # noqa: BLE001
                return self.reply(500, {"detail": f"{exc.__class__.__name__}: {exc}"})
        result["turnId"] = "l_" + uuid.uuid4().hex[:12]
        return self.reply(200, result)

    # -- static

    def serve_static(self, path):
        if not os.path.isdir(STATIC_ROOT):
            return self.reply(404, {
                "detail": "The built UI is not present. Either run the API alone "
                          "with --no-static and start the dev server in webui/, "
                          "or build it: cd webui && npm install && npm run build"})
        clean = posixpath.normpath(urllib.parse.unquote(path)).lstrip("/")
        if clean in ("", "."):
            clean = "index.html"
        full = os.path.abspath(os.path.join(STATIC_ROOT, clean.replace("/", os.sep)))
        root = os.path.abspath(STATIC_ROOT)
        if os.path.commonpath([root, full]) != root:
            return self.reply(403, {"detail": "Forbidden"})
        if not os.path.isfile(full):
            full = os.path.join(root, "index.html")     # SPA fallback
        cache = "no-store" if full.endswith("index.html") else "public, max-age=600"
        return self.send_file(full, cache=cache)


class QuietServer(ThreadingHTTPServer):
    """Refuse to start on a port that is already serving.

    ThreadingHTTPServer sets allow_reuse_address, which on Windows lets a second
    process bind a port another process is already listening on. Both then
    "run", connections go to whichever the OS picks, and a restart appears to
    have changed nothing -- which cost half an hour here: an old server kept
    answering while the new one printed its banner beside it. Failing to bind is
    the more useful outcome.
    """

    allow_reuse_address = False


def _clamp(raw, low, high, default):
    try:
        return max(low, min(high, int(raw)))
    except (TypeError, ValueError):
        return default


def main():
    global STORE, LIVE
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--live", action="store_true",
                    help="allow live answers: real retrieval plus a real, paid "
                         "API call per question. Off by default.")
    ap.add_argument("--live-budget", type=int, default=None,
                    help="how many live calls this process may make (default 25)")
    ap.add_argument("--live-model", default=None,
                    help="generation model for live mode (default gemini-3.6-flash)")
    ap.add_argument("--live-encoder", default=None,
                    help="query encoder for live mode (default models/bge-large-en-v1.5)")
    ap.add_argument("--live-mode", default=None,
                    choices=("pure-text", "multimodal"),
                    help="what the model is given for an image: its VLM-written "
                         "description (pure-text, the recorded arms' mode) or "
                         "the image itself (multimodal)")
    ap.add_argument("--metrics-run", default=None,
                    help=f"run id under artifacts/runs (default {C.METRICS_RUN})")
    ap.add_argument("--image-root", default=None,
                    help="directory holding the dataset's images/ folder")
    ap.add_argument("--no-static", action="store_true",
                    help="serve the API only; use the Vite dev server for the UI")
    ap.add_argument("--verbose", action="store_true", help="log every request")
    args = ap.parse_args()

    t0 = time.time()
    STORE = Store(metrics_run=args.metrics_run, image_root=args.image_root)
    _ = STORE.actions                       # pay the pickle load before serving
    Handler.quiet = not args.verbose
    if args.no_static:
        globals()["STATIC_ROOT"] = os.path.join(C.REPO_ROOT, "webui", "does-not-exist")

    warmup_seconds = None
    if args.live:
        from demo.live import DEFAULT_BUDGET, DENSE_MODEL, MODE, MODEL, LiveEngine
        LIVE = LiveEngine(
            STORE,
            dense_model=args.live_encoder or DENSE_MODEL,
            model=args.live_model or MODEL,
            mode=args.live_mode or MODE,
            budget=args.live_budget if args.live_budget is not None else DEFAULT_BUDGET)
        print("[live] warming up the corpus index, vectors and encoder", flush=True)
        warmup_seconds = LIVE.warmup()

    provenance = STORE.provenance()
    print("=" * 78)
    print("MMDocRAG demo console -- recorded runs replayed"
          + ("; live answers ENABLED (each one is a paid API call)"
             if LIVE else "; live mode off"))
    print("=" * 78)
    print(f"  questions        {len(STORE.questions)} in {len(STORE.documents)} documents")
    print(f"  replayable       {len(STORE.replayable)} (the recorded end-to-end run)")
    print(f"  metrics run      {STORE.metrics_meta.get('run_id')} "
          f"({len(STORE.metrics)} metrics)")
    print(f"  action table     {provenance['retrieval']['actionTable'].get('source')}")
    print(f"  images           {STORE.image_root} "
          f"({'found' if provenance['imageRoot']['available'] else 'MISSING'})")
    print(f"  static UI        {STATIC_ROOT if not args.no_static else 'disabled'}")
    print(f"  loaded in        {time.time() - t0:.1f}s")
    if LIVE:
        live = LIVE.status()
        print(f"  live mode        {live['model']} + {live['encoder']}, "
              f"quota {live['quotaText']}/{live['quotaVisual']} at k={live['k']}, "
              f"{live['mode']}"
              + (" (the images themselves are sent)" if live.get("sendsImages") else ""))
        print(f"                   budget {live['budget']} calls, API key "
              f"{'present' if live['apiKeyPresent'] else 'MISSING'}; "
              f"every attempt logged to artifacts/api/demo-live/")
        print(f"                   warmed up in {warmup_seconds}s; "
              f"a query encodes in milliseconds after this")
    for error in STORE.errors:
        print(f"  [missing] {error}")
    # serve_forever blocks from here on, so a redirected log would otherwise
    # sit empty in its buffer until the process is killed.
    print(f"\n  http://{args.host}:{args.port}\n", flush=True)

    server = QuietServer((args.host, args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
