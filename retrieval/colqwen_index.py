"""Score image quotes with ColQwen2 late interaction. Runs in .venv-colpali.

Why a separate interpreter
--------------------------
colpali-engine requires transformers >= 5, and this project's main environment
is pinned at 4.57.3 for sentence-transformers. Upgrading in place would break
the BGE pipeline every earlier experiment depends on, so this module runs under
`.venv-colpali`, which inherits the system torch and shadows only transformers.
Nothing it writes is version-dependent -- just rankings and scores.

What it measures
----------------
Every retrieval result in this project so far came from a *text* retriever:
BM25 over VLM descriptions, or BGE over the same. The paper's Table 6 crossover
is between text retrievers and a *visual* one, and the visual half has never
been tested here. ColQwen is the exact model that row uses, so this closes the
gap rather than approximating it.

MaxSim over multi-vector representations, per the ColBERT/ColPali formulation:
each query token takes its best-matching image patch and the scores are summed.
That is what lets it read a chart without OCR.

    CAVEAT. ColPali-family models are trained on full page images; the image
    quotes here are cropped figure and table regions. That is what makes them
    comparable to the paper's quote-level Table 6, but the crops are somewhat
    off-distribution for the encoder, and a page-level index would be a
    different (and much more expensive) experiment.

Documents are processed one at a time and the cache is emptied between them:
the encoder is 2B parameters in bf16 on an 8.6 GB card, so nothing beyond a
single document's images is ever resident.

Run (from the repo root):
    .venv-colpali/Scripts/python.exe -m retrieval.colqwen_index
    .venv-colpali/Scripts/python.exe -m retrieval.colqwen_index --limit-docs 3
"""

import argparse
import collections
import json
import os
import sqlite3
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO_ROOT, "canonical", "mmdocrag.sqlite")
DEFAULT_IMG_ROOT = r"D:\Dataset\MMDocRAG\images"
DEFAULT_OUT = os.path.join(REPO_ROOT, "retrieval", "colqwen_scores.sqlite")
# Local directory, not a hub id. huggingface_hub cannot create the snapshot
# symlinks on this Windows box without developer mode (WinError 1314), so the
# cache resolves as empty even with the blobs present; and its xet transfer
# backend hangs on the adapter. Materialising both repos into plain folders and
# repointing adapter_config.base_model_name_or_path at the local base sidesteps
# both. See docs/lab-notebook.html E24.
MODEL = os.path.join(REPO_ROOT, "models", "colqwen2-v1.0")

SCHEMA = """
CREATE TABLE IF NOT EXISTS ranking (
    question_uid TEXT NOT NULL,
    evidence_id  TEXT NOT NULL,
    rank         INTEGER NOT NULL,
    score        REAL,
    PRIMARY KEY (question_uid, evidence_id)
);
CREATE INDEX IF NOT EXISTS idx_rank_q ON ranking (question_uid, rank);
CREATE TABLE IF NOT EXISTS done_docs (doc_name TEXT PRIMARY KEY);
"""


IMG_EXT = (".jpg", ".jpeg", ".png")


def _disk_images(img_root, docs):
    """Every image file belonging to `docs`, keyed by document.

    The candidate pool in canonical_evidence is the union of the questions' own
    candidate lists, so it holds 29.8 images per document against the paper's
    63. Ranking against a pool that was itself selected per question inflates
    recall: most of the document's images were never in the running. The files
    are all on disk, so the full pool is recoverable even though the released
    jsonl only names the candidates.
    """
    root = os.path.join(img_root, "images")
    if not os.path.isdir(root):                 # zip layout without the nesting
        root = img_root
    want = set(docs)
    by_doc = collections.defaultdict(list)
    for f in sorted(os.listdir(root)):
        if not f.lower().endswith(IMG_EXT) or "_image" not in f:
            continue
        doc = f.rsplit("_image", 1)[0]
        if doc in want:
            by_doc[doc].append(f)
    return by_doc


def load_work(db_path, img_root=None, source="canonical"):
    """Documents to index, as {doc: {imgs: [(evidence_id, path)], qs: [...]}}.

    `source="canonical"` ranks the official candidate pool -- what every earlier
    experiment used, and what keeps a comparison against the description-side
    retrievers fair, since those have no representation for an image outside the
    pool. `source="fulldisk"` ranks every image in the document, which is the
    only pool comparable to the paper's Table 6. The two answer different
    questions and neither replaces the other; see docs/paper-baseline-audit.md.
    """
    con = sqlite3.connect(db_path)
    imgs = con.execute(
        "SELECT doc_name, evidence_id, img_path FROM canonical_evidence "
        "WHERE type <> 'text' AND img_path IS NOT NULL AND img_path <> '' "
        "ORDER BY doc_name, evidence_id").fetchall()
    qs = con.execute(
        "SELECT doc_name, question_uid, question FROM questions "
        "WHERE split = 'evaluation' ORDER BY doc_name, question_uid").fetchall()
    con.close()

    by_doc = collections.OrderedDict()
    for doc, eid, path in imgs:
        by_doc.setdefault(doc, {"imgs": [], "qs": []})["imgs"].append((eid, path))

    if source == "fulldisk":
        # Gold carries canonical evidence_ids, so an image already in the pool
        # must keep its id or recall becomes uncomputable. Only the images the
        # pool never contained get a synthesised one, and the "unpooled:" prefix
        # keeps them distinguishable in the ranking table forever after.
        # One image file can carry several evidence_ids: 60 basenames in the
        # evaluation documents are shared by more than one canonical row. A
        # basename -> single id map silently drops 61 of them, and a dropped id
        # is a gold quote that can never be found again -- recall would come out
        # lower, plausible, and wrong, with nothing raised. So every alias is
        # emitted. ColQwen re-encodes those 61 files (0.4% of 13,999), which is
        # cheaper than carrying an alias table through the scoring path.
        eids_of = collections.defaultdict(list)
        for _d, e, p in imgs:
            eids_of[os.path.basename(p).lower()].append(e)
        docs = {d for d, _q, _t in qs}
        disk = _disk_images(img_root or DEFAULT_IMG_ROOT, docs)
        n_new = n_alias = 0
        for doc, files in disk.items():
            entry = by_doc.setdefault(doc, {"imgs": [], "qs": []})
            entry["imgs"] = []
            for f in files:
                known = eids_of.get(f.lower())
                if not known:
                    entry["imgs"].append(("unpooled:" + f, "images/" + f))
                    n_new += 1
                    continue
                n_alias += len(known) - 1
                for eid in known:
                    entry["imgs"].append((eid, "images/" + f))
        print(f"full-disk pool: {sum(len(v) for v in disk.values())} images "
              f"over {len(disk)} documents ({n_new} outside the candidate pool, "
              f"{n_alias} extra alias id(s) sharing a file)")

    for doc, quid, q in qs:
        if doc in by_doc:
            by_doc[doc]["qs"].append((quid, q or ""))
    return collections.OrderedDict(
        (d, v) for d, v in by_doc.items() if v["qs"] and v["imgs"])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--img-root", default=DEFAULT_IMG_ROOT)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--img-batch", type=int, default=2,
                    help="images per forward pass; 2 is safe on 8.6 GB")
    ap.add_argument("--q-batch", type=int, default=16)
    ap.add_argument("--limit-docs", type=int, default=0)
    ap.add_argument("--doc-order", default="name", choices=("name", "random"),
                    help="random makes any partial index a simple random sample "
                         "of documents, so an interrupted run is still reportable")
    ap.add_argument("--seed", type=int, default=20260830)
    ap.add_argument("--checkpoint-dir", default=None,
                    help="where per-document image embeddings are cached so a "
                         "killed run resumes mid-document (default: alongside "
                         "--out). Deleted per document once its rankings are "
                         "committed.")
    ap.add_argument("--image-source", default="canonical",
                    choices=("canonical", "fulldisk"),
                    help="canonical = the official candidate pool (29.8 img/doc, "
                         "what every earlier experiment used); fulldisk = every "
                         "image in the document (63.6/doc, the only pool "
                         "comparable to the paper's Table 6). Write fulldisk to "
                         "its own --out; the two are not interchangeable.")
    args = ap.parse_args()
    if args.image_source == "fulldisk" and args.out == DEFAULT_OUT:
        raise SystemExit(
            "Refusing to write a full-disk index over the canonical one.\n"
            "They rank different pools, so mixing them would silently change "
            "what every recall number in this project means. Pass an explicit "
            "--out, e.g. retrieval/colqwen_scores_fullpool.sqlite")

    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    import torch
    from PIL import Image
    from colpali_engine.models import ColQwen2, ColQwen2Processor

    work = load_work(args.db, args.img_root, args.image_source)
    if args.doc_order == "random":
        # Documents are processed one at a time and the run resumes wherever it
        # stopped, so whatever has been indexed when time runs out IS the
        # sample. In name order that sample is an alphabetical prefix -- fine if
        # nothing correlates with the name, which is not something to assume of
        # a corpus where names encode the exchange and year. Seeded shuffling
        # makes every stopping point a simple random sample of documents, so a
        # partial index can be reported with an honest interval instead of a
        # caveat about which documents happened to come first.
        import random
        keys = list(work)
        random.Random(args.seed).shuffle(keys)
        work = collections.OrderedDict((k, work[k]) for k in keys)
    if args.limit_docs:
        work = collections.OrderedDict(list(work.items())[:args.limit_docs])
    n_img = sum(len(v["imgs"]) for v in work.values())
    n_q = sum(len(v["qs"]) for v in work.values())
    print(f"{len(work)} documents, {n_img} image quotes, {n_q} questions")

    con = sqlite3.connect(args.out)
    con.executescript(SCHEMA)
    done = {r[0] for r in con.execute("SELECT doc_name FROM done_docs")}
    todo = [d for d in work if d not in done]
    print(f"already done {len(done)}, to process {len(todo)}")
    if not todo:
        con.close()
        return

    print(f"loading {args.model} ...", flush=True)
    model = ColQwen2.from_pretrained(
        args.model, dtype=torch.bfloat16, device_map="cuda:0").eval()
    proc = ColQwen2Processor.from_pretrained(args.model)
    print(f"loaded; VRAM {torch.cuda.memory_allocated()/1e9:.2f} GB", flush=True)

    # Unreadable images used to be swallowed by `except: pass`, which meant a
    # document could silently index fewer candidates than the evaluator later
    # assumed were there -- and the recall computed from it would look normal.
    # Every failure is now written to failed_images.jsonl with its cause, and
    # the count is reported at the end.
    failed_path = os.path.join(os.path.dirname(args.out) or ".",
                               "colqwen_failed_images.jsonl")
    failed_fh = open(failed_path, "a", encoding="utf-8")
    n_failed = 0

    # Image embeddings are cached per document and per slice. A document's
    # images must all be resident to score MaxSim against its questions, but
    # they do not have to be encoded in one sitting -- and the largest document
    # here (660 images) takes longer to encode than most execution windows
    # allow. Without this, such documents can never be completed, and the
    # partial index silently becomes a small-document sample.
    ckpt_root = args.checkpoint_dir or (os.path.splitext(args.out)[0] + ".ckpt")
    os.makedirs(ckpt_root, exist_ok=True)

    def _slice_path(doc, i):
        # The batch size is part of the identity: slice "0" means images 0-1 at
        # --img-batch 2 and images 0-3 at 4. Keying on the offset alone let a
        # rerun with a different batch load the wrong span and skip the
        # remainder, which is how one document came out with 106 of 192 images.
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in doc)
        return os.path.join(ckpt_root, f"{safe}__b{args.img_batch}__{i:06d}.pt")

    started, n_done = time.time(), 0
    for di, doc in enumerate(todo, 1):
        imgs, qs = work[doc]["imgs"], work[doc]["qs"]
        emb_img, keep = [], []
        n_failed_this = 0
        with torch.no_grad():
            for i in range(0, len(imgs), args.img_batch):
                cpath = _slice_path(doc, i)
                want = len(imgs[i:i + args.img_batch])
                if os.path.exists(cpath):
                    try:
                        blob = torch.load(cpath, weights_only=False)
                        got = len(blob["ids"])
                        if got != want:
                            raise ValueError(
                                f"slice holds {got} image(s), loop expects "
                                f"{want}")
                        emb_img.append(blob["emb"])
                        keep.extend(blob["ids"])
                        continue
                    except Exception as exc:
                        print(f"    checkpoint {os.path.basename(cpath)} "
                              f"rejected ({type(exc).__name__}: {exc}); "
                              f"re-encoding", flush=True)
                chunk = imgs[i:i + args.img_batch]
                pil, ids = [], []
                for eid, path in chunk:
                    full = os.path.join(args.img_root, path.replace("/", os.sep))
                    try:
                        pil.append(Image.open(full).convert("RGB"))
                        ids.append(eid)
                    except Exception as exc:
                        n_failed += 1
                        n_failed_this += 1
                        failed_fh.write(json.dumps(
                            {"doc_name": doc, "evidence_id": eid,
                             "img_path": path, "resolved_path": full,
                             "exists": os.path.exists(full),
                             "error_type": type(exc).__name__, "error": str(exc),
                             "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                  time.gmtime())},
                            ensure_ascii=False) + "\n")
                        failed_fh.flush()
                if not pil:
                    continue
                batch = proc.process_images(pil).to(model.device)
                e = model(**batch).to(torch.float32).cpu()
                tmp = cpath + ".tmp"
                torch.save({"emb": e, "ids": ids}, tmp)
                os.replace(tmp, cpath)   # a torn slice must not look complete
                emb_img.append(e)
                keep.extend(ids)
            emb_q = []
            for i in range(0, len(qs), args.q_batch):
                batch = proc.process_queries([q for _, q in qs[i:i + args.q_batch]])
                batch = batch.to(model.device)
                emb_q.append(model(**batch).to(torch.float32).cpu())

        if not emb_img or not emb_q:
            con.execute("INSERT OR REPLACE INTO done_docs VALUES (?)", (doc,))
            con.commit()
            continue

        # score_multi_vector handles the ragged padding across batches
        scores = proc.score_multi_vector(
            [e[i] for e in emb_q for i in range(e.shape[0])],
            [e[i] for e in emb_img for i in range(e.shape[0])])

        if len(keep) + n_failed_this < len(imgs):
            raise SystemExit(
                f"\n{doc}: assembled {len(keep)} image embeddings for "
                f"{len(imgs)} images ({n_failed_this} unreadable). Refusing to "
                f"mark the document done -- a short pool silently deflates every "
                f"recall computed from it. Delete "
                f"{os.path.basename(ckpt_root)}/ and re-run this document.")
        rows = []
        for qi, (quid, _) in enumerate(qs):
            s = scores[qi]
            order = torch.argsort(s, descending=True)
            for r, j in enumerate(order.tolist()):
                rows.append((quid, keep[j], r, float(s[j])))
        con.executemany("INSERT OR REPLACE INTO ranking VALUES (?,?,?,?)", rows)
        con.execute("INSERT OR REPLACE INTO done_docs VALUES (?)", (doc,))
        con.commit()
        for i in range(0, len(imgs), args.img_batch):
            try:
                os.remove(_slice_path(doc, i))
            except OSError:
                pass

        n_done += len(imgs)
        del emb_img, emb_q, scores
        torch.cuda.empty_cache()
        if di % 5 == 0 or di == len(todo):
            rate = (time.time() - started) / n_done if n_done else 0
            print(f"  {di}/{len(todo)} docs, {n_done} images, "
                  f"{rate:.2f}s/img, eta {rate*(n_img-n_done)/60:.0f} min, "
                  f"VRAM {torch.cuda.memory_allocated()/1e9:.2f} GB", flush=True)

    failed_fh.close()
    tot = con.execute("SELECT COUNT(DISTINCT question_uid) FROM ranking").fetchone()[0]
    print()
    print(f"done: rankings for {tot} questions -> {args.out}")
    if n_failed:
        print(f"[!] {n_failed} image(s) could not be read and are ABSENT "
              f"from the index. Every question in the affected documents "
              f"ranks a smaller pool than the evaluator assumes.")
        print(f"    details: {failed_path}")
        print("    run `python experiments.py verify E24` before "
              "reporting any number from this index.")
    else:
        print("all images read successfully; no entries in "
              + os.path.basename(failed_path))
    con.close()


if __name__ == "__main__":
    main()
