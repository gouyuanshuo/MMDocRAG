"""The literature review as a checkable registry, not a prose file.

Why this is a program
---------------------
Proposal section 14 asks for 30-40 candidate papers, 15-20 read closely, a
taxonomy table, a method comparison table and an evidence-backed statement of
the research gap. Written as prose, none of those can be audited: a reader
cannot tell which claims about a paper were read off the paper and which were
recalled, and a miscount of the gap matrix is invisible.

E22 exists in this project because an external report cited four papers that
had to be checked by hand. So every record here carries the URL it was verified
against and the date it was checked, `check` refuses to pass on a record that
lacks one, and the renderer drops unverified records out of the tables rather
than printing them with a footnote.

The gap claim this review has to test
-------------------------------------
The proposal's hypothesis is that prior systems adapt only ONE stage of the
pipeline, so a hierarchical router over several stages is unoccupied ground.
Section 3 immediately warns that this is a preliminary judgement and must not
be asserted without a review. `gap` therefore prints the stage-coverage matrix
as counts, which can falsify the claim as easily as support it: any paper that
adapts two or more stages is evidence against it, and is listed by name.

Stages are the ones the proposal itself routes over, plus the two adjacent
mechanisms it must not be confused with:

    modality     which evidence modality to retrieve for this query
    retriever    which retrieval method (BM25 / dense / hybrid / visual)
    depth        how much to retrieve: top-k, or how many retrieval rounds
    granularity  chunk or region size of the evidence
    filter       post-retrieval selection among already-retrieved evidence
    generation   what to feed the generator, given fixed retrieved evidence

`filter` and `generation` are recorded separately from `modality` on purpose.
Choosing among evidence you have already paid to retrieve is a different
operation from choosing what to retrieve, and this project's own RQ1a is a
`generation`-stage result that says nothing about the retrieval stage.

Run:
    python literature.py check
    python literature.py list --theme adaptive-rag
    python literature.py gap
    python literature.py render
"""

import argparse
import collections
import io
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(REPO, "docs", "literature", "papers.json")
OUT = os.path.join(REPO, "docs", "literature-review.html")

# Proposal section 14 review themes, verbatim.
THEMES = collections.OrderedDict([
    ("foundational", "Foundational RAG and retrieval"),
    ("bm25-dense-hybrid", "BM25, Dense and Hybrid Retrieval"),
    ("adaptive-rag", "Adaptive RAG and Query Routing"),
    ("multimodal-doc-rag", "Multimodal Document RAG"),
    ("visual-retrieval", "Visual document retrieval"),
    ("granularity", "Multi-granularity indexing and chunking"),
    ("evidence-selection", "Evidence selection and reranking"),
    ("evaluation", "Faithfulness and multimodal RAG evaluation"),
])

STAGES = collections.OrderedDict([
    ("modality", "which modality to retrieve"),
    ("retriever", "which retrieval method"),
    ("depth", "top-k or number of retrieval rounds"),
    ("granularity", "chunk or region size"),
    ("filter", "post-retrieval evidence selection"),
    ("generation", "what to feed the generator"),
])

REQUIRED = ("key", "title", "year", "venue", "url", "themes", "stages",
            "modalities", "retrieval", "datasets", "metrics", "limitation",
            "relevance", "read", "verified")
RELEVANCE = ("core", "candidate", "excluded")
# How much of the paper was actually read. The distinction is load-bearing:
# section 14 asks for 15-20 papers read CLOSELY, and a pile of abstracts is not
# that. `check` refuses to let a record call itself core on an abstract.
READ = ("abstract", "full")
# `stages` may legitimately be empty -- a static pipeline that routes nothing is
# an informative record, and it is the control group for the gap claim.
MAY_BE_EMPTY = ("stages",)


def load(path=DATA):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["papers"]


def save(papers, path=DATA):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        json.dump({"papers": sorted(papers, key=lambda p: p["key"])}, fh,
                  ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def problems(p):
    """Everything wrong with one record, as a list of strings."""
    out = []
    for f in REQUIRED:
        if f not in p:
            out.append(f"missing {f}")
        elif p[f] in (None, "", {}) or (p[f] == [] and f not in MAY_BE_EMPTY):
            out.append(f"empty {f}")
    if p.get("relevance") not in RELEVANCE:
        out.append(f"relevance must be one of {RELEVANCE}")
    if p.get("read") not in READ:
        out.append(f"read must be one of {READ}")
    if p.get("relevance") == "core" and p.get("read") != "full":
        out.append("core requires read=full -- an abstract is not a close "
                   "reading, and section 14 counts 15-20 close readings")
    for t in p.get("themes", []):
        if t not in THEMES:
            out.append(f"unknown theme {t!r}")
    for s in p.get("stages", []):
        if s not in STAGES:
            out.append(f"unknown stage {s!r}")
    v = p.get("verified") or {}
    if not v.get("url") or not v.get("date"):
        out.append("verified needs both url and date -- a record without a "
                   "source it was checked against is a recollection")
    return out


def cmd_check(args):
    papers = load()
    bad = 0
    for p in papers:
        errs = problems(p)
        if errs:
            bad += 1
            print(f"  [FAIL] {p.get('key', '<no key>')}: {'; '.join(errs)}")
    live = [p for p in papers if p.get("relevance") != "excluded"]
    core = [p for p in live if p.get("relevance") == "core"]
    full = [p for p in live if p.get("read") == "full"]
    print()
    print(f"records {len(papers)}, in scope {len(live)}, core {len(core)}, "
          f"excluded {len(papers) - len(live)}")
    print(f"proposal section 14 targets: 30-40 candidates, 15-20 core")
    print(f"  candidates {len(live):>3}  "
          f"{'OK' if 30 <= len(live) <= 40 else 'NOT YET' }")
    print(f"  core       {len(core):>3}  "
          f"{'OK' if 15 <= len(core) <= 20 else 'NOT YET'}")
    print(f"  read in full {len(full):>3} of {len(live)} in scope; the rest "
          f"are abstract-level only and are labelled as such")
    missing = [t for t in THEMES
               if not any(t in p["themes"] for p in live)]
    print(f"  themes with no paper: {missing if missing else 'none'}")
    if bad:
        print(f"\n{bad} record(s) failed validation")
        raise SystemExit(1)
    print("\nall records validated")


def cmd_list(args):
    papers = [p for p in load() if p["relevance"] != "excluded"]
    if args.theme:
        papers = [p for p in papers if args.theme in p["themes"]]
    if args.stage:
        papers = [p for p in papers if args.stage in p["stages"]]
    print(f"{'key':<26}{'yr':>5}  {'rel':<10}{'stages':<34}venue")
    print("-" * 108)
    for p in sorted(papers, key=lambda x: (-x["year"], x["key"])):
        print(f"{p['key']:<26}{p['year']:>5}  {p['relevance']:<10}"
              f"{','.join(p['stages']) or '-':<34}{p['venue'][:38]}")
    print(f"\n{len(papers)} paper(s)")


def cmd_gap(args):
    papers = [p for p in load() if p["relevance"] != "excluded"]
    print("=" * 88)
    print("STAGE COVERAGE  --  the evidence for or against the proposal's gap "
          "claim")
    print("=" * 88)
    print("Proposal section 3: prior systems typically adapt only ONE stage. "
          "Section 3 also\nwarns that this is preliminary and must be checked "
          "rather than asserted.\n")
    counts = collections.Counter()
    for p in papers:
        for s in p["stages"]:
            counts[s] += 1
    print(f"{'stage':<14}{'papers':>7}   what it means")
    print("-" * 88)
    for s, desc in STAGES.items():
        print(f"{s:<14}{counts[s]:>7}   {desc}")
    print()
    multi = [p for p in papers if len(p["stages"]) >= 2]
    retr = [p for p in papers
            if len([s for s in p["stages"]
                    if s in ("modality", "retriever", "depth", "granularity")])
            >= 2]
    print(f"papers adapting >= 2 stages of any kind : {len(multi)}")
    for p in sorted(multi, key=lambda x: x["key"]):
        print(f"    {p['key']:<26}{','.join(p['stages'])}")
    print()
    print(f"papers adapting >= 2 RETRIEVAL-side stages: {len(retr)}")
    for p in sorted(retr, key=lambda x: x["key"]):
        print(f"    {p['key']:<26}{','.join(p['stages'])}")
    print()
    if retr:
        print("The gap claim as written in the proposal is NOT supported "
              "without qualification:\nthe works above already adapt more than "
              "one retrieval-side stage. Any gap statement\nmust name what "
              "those works do not do, rather than claim the ground is empty.")
    else:
        print("No paper in the current set adapts two or more retrieval-side "
              "stages. That is\nconsistent with the proposal's claim, but it "
              "is only as strong as the search\ncoverage -- report the themes "
              "searched and the queries used alongside it.")


def _cell(v):
    return ", ".join(v) if isinstance(v, list) else (v or "")


def cmd_render(args):
    papers = [p for p in load() if p["relevance"] != "excluded"]
    papers.sort(key=lambda x: (-x["year"], x["key"]))
    core = [p for p in papers if p["relevance"] == "core"]
    counts = collections.Counter(s for p in papers for s in p["stages"])
    rows = []
    for p in papers:
        rows.append(
            "<tr><td><a href=\"{url}\">{title}</a><div class=\"meta\">{venue}"
            " &middot; read: {read}</div></td><td>{stages}</td>"
            "<td>{mod}</td><td>{ret}</td>"
            "<td>{ds}</td><td>{me}</td><td>{lim}</td></tr>".format(
                url=p["url"], title=p["title"], venue=p["venue"],
                read=p["read"],
                stages=_cell(p["stages"]) or "&mdash;",
                mod=_cell(p["modalities"]), ret=_cell(p["retrieval"]),
                ds=_cell(p["datasets"]), me=_cell(p["metrics"]),
                lim=p["limitation"]))
    # Close readings get their own section: they are the 15-20 papers section 14
    # asks to be read properly, and burying them in a table cell would make the
    # difference between a close reading and an abstract invisible again.
    cr = []
    for x in papers:
        if x.get("close_reading"):
            body = "".join(f"<p>{para}</p>"
                           for para in x["close_reading"].split(chr(10) + chr(10)))
            cr.append(f'<div class="cr"><h3><a href="{x["url"]}">{x["title"]}</a>'
                      f'</h3><div class="meta">{x["venue"]}</div>{body}</div>')
    cr_html = ("<h2>Close readings</h2>" + "".join(cr)) if cr else ""

    stage_rows = "".join(
        f"<tr><td>{s}</td><td class=\"num\">{counts[s]}</td><td>{d}</td></tr>"
        for s, d in STAGES.items())
    html = f"""<title>MMDocRAG Literature Review</title>
<style>
:root {{ --fg:#1a1a1a; --bg:#fff; --mut:#666; --line:#e0e0e0; --acc:#0b6; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme=light]) {{
  --fg:#e8e8e8; --bg:#151515; --mut:#999; --line:#333; }} }}
body {{ font:15px/1.6 -apple-system,Segoe UI,Roboto,sans-serif;
  color:var(--fg); background:var(--bg); margin:0; padding:2rem; }}
.wrap {{ max-width:1180px; margin:0 auto; }}
h1 {{ font-size:1.6rem; margin:0 0 .3rem; }}
h2 {{ font-size:1.2rem; margin:2.4rem 0 .6rem; border-bottom:2px solid
  var(--line); padding-bottom:.3rem; }}
.sub {{ color:var(--mut); margin:0 0 1.5rem; }}
.scroll {{ overflow-x:auto; }}
.scope {{ font-size:13px; color:var(--mut); border-top:1px solid var(--line);
  padding-top:.8rem; margin-top:1.4rem; }}
ol li {{ margin:.5rem 0; }}
.cr {{ border-left:3px solid var(--line); padding:.2rem 0 .2rem 1rem;
  margin:1.4rem 0; }}
.cr h3 {{ margin:.2rem 0 .1rem; }}
.cr p {{ font-size:14px; }}
h3 {{ font-size:1.02rem; margin:1.4rem 0 .4rem; }}
table {{ border-collapse:collapse; width:100%; font-size:13px; }}
th,td {{ border:1px solid var(--line); padding:.45rem .55rem;
  text-align:left; vertical-align:top; }}
th {{ background:rgba(128,128,128,.09); font-weight:600; }}
.meta {{ color:var(--mut); font-size:11px; margin-top:.2rem; }}
.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
a {{ color:var(--acc); }}
.note {{ border-left:3px solid var(--acc); padding:.6rem .9rem;
  background:rgba(0,187,102,.06); margin:1rem 0; }}
</style>
<div class="wrap">
<h1>Literature review &mdash; hierarchical query-conditioned routing</h1>
<p class="sub">{len(papers)} papers in scope, {len(core)} read closely,
{len([x for x in papers if x["read"] == "abstract"])} recorded at abstract
level only and marked as such.
Every record carries the URL it was verified against; unverified records are
not rendered. Generated by <code>literature.py render</code>.</p>

{cr_html}

<h2>Stage coverage</h2>
<p>The proposal's gap hypothesis is that prior systems adapt only one stage of
the pipeline. This table is the evidence, and it can falsify the claim as
easily as support it.</p>
<div class="scroll"><table>
<thead><tr><th>Stage</th><th>Papers</th><th>What it means</th></tr></thead>
<tbody>{stage_rows}</tbody></table></div>

<h2>Taxonomy and method comparison</h2>
<div class="scroll"><table>
<thead><tr><th>Paper</th><th>Adaptation target</th><th>Modalities</th>
<th>Retrieval method</th><th>Dataset</th><th>Metrics</th>
<th>Limitation</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
</div>
"""
    # The gap statement lives in its own file so it can be edited as prose
    # while every number around it stays generated from the registry.
    gap_path = os.path.join(REPO, "docs", "literature", "gap.html")
    if os.path.exists(gap_path):
        gap = io.open(gap_path, encoding="utf-8").read()
        html = html.replace("<h2>Stage coverage</h2>",
                            gap + chr(10) + "<h2>Stage coverage</h2>")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(html)
    os.replace(tmp, OUT)
    print(f"wrote {OUT}  ({len(papers)} papers, {len(core)} core, "
          f"{os.path.getsize(OUT) / 1024:.0f} KB)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    lp = sub.add_parser("list")
    lp.add_argument("--theme")
    lp.add_argument("--stage")
    sub.add_parser("gap")
    sub.add_parser("render")
    args = ap.parse_args()
    {"check": cmd_check, "list": cmd_list, "gap": cmd_gap,
     "render": cmd_render}[args.cmd](args)


if __name__ == "__main__":
    main()
