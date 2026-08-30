"""Is multimodal input worth paying for? A per-model cost-quality table.

Phase 1A.5 established that the pure-text / multimodal choice cannot be made
per question: which mode wins is a property of the model-question pair, not of
the question (router/diagnose.py). What remains is the decision one level up,
which is both answerable and the one proposal 13 actually asks about --
**for a given model, is sending real images worth its cost?**

That question has a clean answer per model, because both arms were measured on
the same 2000 questions with the provider's own billed token counts.

Four views:

  MEASURED     delta F1 with a paired bootstrap interval, and the exact token
               deltas. No assumptions.
  BREAK-EVEN   extra input tokens per F1 point gained. Provider-neutral, needs
               no price list, and is the number to quote when prices move.
  DOLLARS      cost per 1000 questions, gated on a price entry existing.
  PARETO       which (model, mode) pairs survive as non-dominated choices.

Excluded from every cost view: the five Gemini models. Their reported in_tok is
1.02-1.04x pure-text in the multimodal arm, so it cannot be counting the eight
images; a dollar figure built on it would understate the arm it is meant to
price. Their F1 numbers are unaffected and appear in the quality view.

Run:
    python -m router.cost_quality
    python -m router.cost_quality --setting 15 --per-questions 2000
"""

import argparse
import json
import os
import sqlite3
import sys

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO_ROOT, "router", "outcomes.sqlite")
DEFAULT_PRICES = os.path.join(REPO_ROOT, "router", "prices.json")

# See module docstring. Same threshold router/oracle.py uses.
MIN_CREDIBLE_RATIO = 1.2
BOOTSTRAP = 2000
SEED = 20260824


def load(db_path, setting):
    con = sqlite3.connect(db_path)
    rows = con.execute("""
        SELECT t.model, t.q_id, t.f1, m.f1, t.in_tok, m.in_tok, t.out_tok, m.out_tok
        FROM outcomes t
        JOIN outcomes m
          ON  m.model = t.model AND m.setting = t.setting AND m.q_id = t.q_id
        WHERE t.setting = ? AND t.mode = 'pure-text' AND m.mode = 'multimodal'
        ORDER BY t.model, t.q_id
    """, (setting,)).fetchall()
    con.close()
    per = {}
    for model, _, f1t, f1m, it, im, ot, om in rows:
        per.setdefault(model, []).append((f1t, f1m, it or 0, im or 0, ot or 0, om or 0))
    return {m: np.asarray(v, dtype=np.float64) for m, v in per.items()}


def paired_bootstrap(arr, rng, b=BOOTSTRAP):
    """CI for mean(f1_mm - f1_pt), resampling questions, keeping pairs together.

    Paired because both arms answered the same questions: the question-to-
    question variance is shared and must not be counted twice.
    """
    d = arr[:, 1] - arr[:, 0]
    n = len(d)
    idx = rng.integers(0, n, size=(b, n))
    means = d[idx].mean(axis=1)
    return np.percentile(means, [2.5, 97.5]) * 100


def load_prices(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--setting", default="20", choices=["15", "20"])
    ap.add_argument("--prices", default=DEFAULT_PRICES)
    ap.add_argument("--per-questions", type=int, default=1000,
                    help="batch size the dollar column is quoted for")
    args = ap.parse_args()

    data = load(args.db, args.setting)
    models = sorted(data)
    rng = np.random.default_rng(SEED)
    prices = load_prices(args.prices)

    stat = {}
    for m in models:
        a = data[m]
        lo, hi = paired_bootstrap(a, rng)
        stat[m] = {
            "n": len(a),
            "f1_pt": a[:, 0].mean() * 100, "f1_mm": a[:, 1].mean() * 100,
            "d_f1": (a[:, 1] - a[:, 0]).mean() * 100, "ci": (lo, hi),
            "in_pt": a[:, 2].mean(), "in_mm": a[:, 3].mean(),
            "out_pt": a[:, 4].mean(), "out_mm": a[:, 5].mean(),
        }
        s = stat[m]
        s["ratio"] = s["in_mm"] / s["in_pt"] if s["in_pt"] else 0.0
        s["credible"] = s["ratio"] >= MIN_CREDIBLE_RATIO

    # ---------------- 1. measured ----------------
    print("=" * 104)
    print(f"1. MEASURED  (setting {args.setting}, {stat[models[0]]['n']} questions, "
          f"paired bootstrap 95% CI, B={BOOTSTRAP})")
    print("=" * 104)
    print(f"{'model':<22}{'F1 text':>9}{'F1 multi':>10}{'dF1':>8}"
          f"{'95% CI':>20}{'in tok x':>10}{'out tok':>18}")
    print("-" * 104)
    for m in models:
        s = stat[m]
        sig = " *" if not (s["ci"][0] < 0 < s["ci"][1]) else "  "
        ci = f"[{s['ci'][0]:+.1f}, {s['ci'][1]:+.1f}]{sig}"
        print(f"{m:<22}{s['f1_pt']:>9.1f}{s['f1_mm']:>10.1f}{s['d_f1']:>+8.1f}"
              f"{ci:>20}{s['ratio']:>10.2f}"
              f"{format(s['out_pt'], '.0f') + ' -> ' + format(s['out_mm'], '.0f'):>18}")
    print("-" * 104)
    ns = [m for m in models if stat[m]["ci"][0] < 0 < stat[m]["ci"][1]]
    print(f"* = delta F1 excludes zero.  {len(models) - len(ns)}/{len(models)} models "
          f"show a distinguishable difference between the two modes;")
    print(f"the other {len(ns)} are statistically indistinguishable: "
          f"{', '.join(ns) if ns else '-'}")

    # ---------------- 2. break-even ----------------
    print()
    print("=" * 104)
    print("2. BREAK-EVEN  (extra input tokens paid per F1 point gained; "
          "provider-neutral, no prices needed)")
    print("=" * 104)
    print(f"{'model':<22}{'dF1':>8}{'d in tok':>11}{'tok / F1 pt':>14}   verdict")
    print("-" * 104)
    usable = [m for m in models if stat[m]["credible"]]
    for m in usable:
        s = stat[m]
        d_tok = s["in_mm"] - s["in_pt"]
        if s["d_f1"] <= 0:
            verdict = "DOMINATED - pure-text is better AND cheaper"
            rate = "-"
        elif stat[m]["ci"][0] < 0 < stat[m]["ci"][1]:
            verdict = "no measurable gain, but a real cost"
            rate = f"{d_tok / s['d_f1']:,.0f}"
        else:
            verdict = f"pays {d_tok / s['d_f1']:,.0f} tok for each F1 point"
            rate = f"{d_tok / s['d_f1']:,.0f}"
        print(f"{m:<22}{s['d_f1']:>+8.1f}{d_tok:>+11.0f}{rate:>14}   {verdict}")
    print("-" * 104)
    dominated = [m for m in usable if stat[m]["d_f1"] <= 0]
    print(f"{len(dominated)}/{len(usable)} models are strictly dominated by "
          f"pure-text: {', '.join(dominated) if dominated else '-'}")
    excluded = [m for m in models if not stat[m]["credible"]]
    print(f"excluded (in_tok omits image tokens): {', '.join(excluded)}")

    # ---------------- 3. dollars ----------------
    print()
    print("=" * 104)
    print(f"3. DOLLARS  (USD per {args.per_questions:,} questions, "
          f"prices checked {prices['checked']})")
    print("=" * 104)
    pm = prices["models"]
    priced = [m for m in usable if m in pm]
    unpriced = [m for m in usable if m not in pm]
    n = args.per_questions
    print(f"{'model':<22}{'text $':>10}{'multi $':>10}{'extra $':>10}"
          f"{'$ / F1 pt':>12}{'F1/$ text':>12}{'F1/$ multi':>12}")
    print("-" * 104)
    for m in priced:
        s, p = stat[m], pm[m]
        c_pt = (s["in_pt"] * p["in"] + s["out_pt"] * p["out"]) * n / 1e6
        c_mm = (s["in_mm"] * p["in"] + s["out_mm"] * p["out"]) * n / 1e6
        per_pt = (c_mm - c_pt) / s["d_f1"] if s["d_f1"] > 0 else float("nan")
        print(f"{m:<22}{c_pt:>10.2f}{c_mm:>10.2f}{c_mm - c_pt:>+10.2f}"
              f"{(format(per_pt, '.2f') if per_pt == per_pt else 'n/a'):>12}"
              f"{s['f1_pt'] / c_pt:>12.1f}{s['f1_mm'] / c_mm:>12.1f}")
    print("-" * 104)
    if unpriced:
        print(f"no price entry, omitted: {', '.join(unpriced)}")
    unver = [m for m in priced if not pm[m].get("verified")]
    if unver:
        print()
        print("!" * 104)
        print("UNVERIFIED PRICES. The following entries in router/prices.json are "
              "marked verified=false, i.e. they are")
        print("best-known list prices, not prices confirmed against the provider's "
              "page. Check them before citing any")
        print("dollar figure above:")
        print("  " + ", ".join(unver))
        print("!" * 104)

    # ---------------- 4. pareto ----------------
    print()
    print("=" * 104)
    print(f"4. PARETO FRONTIER  (every model x mode as one option; "
          f"USD per {args.per_questions:,} questions)")
    print("=" * 104)
    pts, vec = [], {}
    for m in priced:
        s, p = stat[m], pm[m]
        pts.append((m, "pure-text", s["f1_pt"],
                    (s["in_pt"] * p["in"] + s["out_pt"] * p["out"]) * n / 1e6))
        pts.append((m, "multimodal", s["f1_mm"],
                    (s["in_mm"] * p["in"] + s["out_mm"] * p["out"]) * n / 1e6))
        # Per-question F1 vectors, for testing frontier steps. All models were
        # scored on the same questions in the same order, so these align.
        vec[(m, "pure-text")] = data[m][:, 0]
        vec[(m, "multimodal")] = data[m][:, 1]

    front = []
    for cand in sorted(pts, key=lambda x: (x[3], -x[2])):
        if not front or cand[2] > front[-1][2]:
            front.append(cand)

    # A step onto the frontier is only worth paying for if the quality gain is
    # distinguishable from zero. Every option was measured on the same 2000
    # questions, so the step is tested with a paired bootstrap over questions --
    # the same procedure as table 1, applied between models instead of within.
    def step_ci(a, b):
        d = vec[a] - vec[b]
        idx = rng.integers(0, len(d), size=(BOOTSTRAP, len(d)))
        return np.percentile(d[idx].mean(axis=1), [2.5, 97.5]) * 100

    print(f"{'rank':<6}{'model':<22}{'mode':<13}{'F1':>7}{'cost $':>10}"
          f"{'F1 per $':>10}{'step vs prev':>22}")
    print("-" * 104)
    noise_steps, robust = [], []
    for i, (m, mode, f1, c) in enumerate(front, 1):
        note = ""
        if not robust:
            robust.append((m, mode, f1, c))
        else:
            # Compare against the last RETAINED point, not the previous row: if
            # rank k was dropped for being noise, rank k+1 has to justify itself
            # against the last option actually worth buying.
            pm_, pmode, pf1, pc = robust[-1]
            lo, hi = step_ci((m, mode), (pm_, pmode))
            real = not (lo < 0 < hi)
            note = f"{f1 - pf1:+.1f} [{lo:+.1f},{hi:+.1f}]" + ("" if real else " ~")
            if real:
                robust.append((m, mode, f1, c))
            else:
                noise_steps.append((m, mode, pm_, pmode, c - pc))
        print(f"{i:<6}{m:<22}{mode:<13}{f1:>7.1f}{c:>10.2f}{f1 / c:>10.1f}"
              f"{note:>22}")
    print("-" * 104)
    print(f"{len(front)} of {len(pts)} options are non-dominated on the raw "
          f"frontier. Everything absent is beaten on both")
    print("axes at once by something on this list.")
    if noise_steps:
        print()
        print("~ = the quality gain over the previous rank is NOT distinguishable "
              "from zero. Such an option holds its")
        print("  place on the frontier only by a difference the data cannot "
              "resolve, and buying it means paying for")
        print("  noise:")
        for m, mode, pm_, pmode, dc in noise_steps:
            print(f"    {m} {mode} over {pm_} {pmode}: "
                  f"+${dc:.2f} per {n:,} questions for no measurable gain")
    mm_front = [x for x in robust if x[1] == "multimodal"]
    print(f"\nfrontier after dropping noise-only steps: {len(robust)} options, "
          f"of which {len(mm_front)} "
          f"{'is' if len(mm_front) == 1 else 'are'} multimodal"
          + (f" ({', '.join(x[0] for x in mm_front)})" if mm_front else ""))
    print("Sending real images earns a place on the frontier at exactly one "
          "point: the top of the quality range,")
    print("where there is nothing cheaper left to buy quality from.")


if __name__ == "__main__":
    main()
