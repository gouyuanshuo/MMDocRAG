"""How much is there to gain from routing the generation input modality?

Every paired model in the release answered the same 2000 questions twice: once
with images passed as images, once with images passed as their text
descriptions. Comparing the two per question gives, for free, the ceiling any
router could reach -- and, more usefully, shows that neither fixed choice is
right for a large minority of questions.

The oracle picks the better mode per question. Ties go to pure-text: it is the
cheaper mode, and a router that guesses on a tie should not be rewarded for it.

A cost-aware oracle takes multimodal only when it wins by more than some margin
`lambda`, which is the plan's a* = argmax [quality - lambda*cost] with cost
folded into a single threshold. Because quote-selection F1 over sets of ~5
items is heavily quantised, a small lambda changes almost nothing (for gpt-4o
only 23 of 1,486 non-tied questions have a gap under 2 F1 points). So rather
than pick one lambda, `--pareto` sweeps it and traces the frontier.

Run:
    python -m router.oracle --setting 20
    python -m router.oracle --setting 20 --pareto
"""

import argparse
import os
import sqlite3
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO_ROOT, "router", "outcomes.sqlite")

# Below this multimodal/pure-text input-token ratio, the provider's reported
# `in_tok` cannot be including the images: eight images cannot cost 4% more
# input than the text descriptions they replaced. Gemini reports 1.02-1.04x
# across all five of its models. Their F1 numbers are sound -- only their cost
# numbers are unusable, so they are dropped from cost analysis and kept
# everywhere else.
MIN_CREDIBLE_RATIO = 1.2


def paired_models(con, setting):
    rows = con.execute(
        "SELECT model FROM outcomes WHERE setting = ? "
        "GROUP BY model HAVING COUNT(DISTINCT mode) = 2 ORDER BY model",
        (setting,)).fetchall()
    return [r[0] for r in rows]


def load_pair(con, setting, model):
    """Per-question (f1, in_tok) for both modes, aligned on q_id."""
    return con.execute("""
        SELECT t.q_id, t.f1, m.f1, t.in_tok, m.in_tok
        FROM outcomes t
        JOIN outcomes m
          ON  m.model = t.model AND m.setting = t.setting AND m.q_id = t.q_id
        WHERE t.model = ? AND t.setting = ?
          AND t.mode = 'pure-text' AND m.mode = 'multimodal'
        ORDER BY t.q_id
    """, (model, setting)).fetchall()


def summarise(rows):
    n = len(rows)
    f1_pt = sum(r[1] for r in rows) / n
    f1_mm = sum(r[2] for r in rows) / n
    tok_pt = sum(r[3] or 0 for r in rows) / n
    tok_mm = sum(r[4] or 0 for r in rows) / n
    return {
        "n": n, "f1_pt": f1_pt, "f1_mm": f1_mm,
        "best_fixed": max(f1_pt, f1_mm),
        "oracle": sum(max(r[1], r[2]) for r in rows) / n,
        "t_wins": sum(1 for r in rows if r[1] > r[2]),
        "m_wins": sum(1 for r in rows if r[2] > r[1]),
        "tok_pt": tok_pt, "tok_mm": tok_mm,
        "ratio": tok_mm / tok_pt if tok_pt else 0.0,
    }


def pareto_point(rows, lam):
    """Mean F1 and mean input tokens when multimodal needs a `lam`-point win."""
    n = len(rows)
    margin = lam / 100.0
    take = [(r[2] - r[1]) > margin for r in rows]
    f1 = sum(r[2] if t else r[1] for r, t in zip(rows, take)) / n
    tok = sum((r[4] or 0) if t else (r[3] or 0) for r, t in zip(rows, take)) / n
    return f1, tok, sum(take) / n


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--setting", default="20", choices=["15", "20"])
    ap.add_argument("--pareto", action="store_true",
                    help="sweep lambda and print the quality/cost frontier")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    models = paired_models(con, args.setting)
    data = {m: load_pair(con, args.setting, m) for m in models}
    stats = {m: summarise(rows) for m, rows in data.items()}
    con.close()
    print(f"setting {args.setting}: {len(models)} models with both input modes\n")

    print("=" * 92)
    print("ORACLE HEADROOM  (quote-selection F1, x100)")
    print("=" * 92)
    print(f"{'model':<24}{'text':>7}{'multi':>7}{'best':>7}{'ORACLE':>8}"
          f"{'gain':>7}{'T win':>7}{'M win':>7}{'tie':>7}")
    print("-" * 92)
    for m in models:
        s = stats[m]
        tie = s["n"] - s["t_wins"] - s["m_wins"]
        print(f"{m:<24}{s['f1_pt']*100:>7.1f}{s['f1_mm']*100:>7.1f}"
              f"{s['best_fixed']*100:>7.1f}{s['oracle']*100:>8.1f}"
              f"{(s['oracle']-s['best_fixed'])*100:>+7.1f}"
              f"{s['t_wins']:>7}{s['m_wins']:>7}{tie:>7}")
    print("-" * 92)
    g = [(stats[m]["oracle"] - stats[m]["best_fixed"]) * 100 for m in models]
    print(f"mean gain {sum(g)/len(g):+.1f}   min {min(g):+.1f}   max {max(g):+.1f}"
          f"   positive for {sum(1 for x in g if x > 0)}/{len(g)} models")

    print()
    print("=" * 92)
    print("INPUT-TOKEN ACCOUNTING  (provider-reported, per question)")
    print("=" * 92)
    print(f"{'model':<24}{'pure-text':>11}{'multimodal':>12}{'ratio':>8}   note")
    print("-" * 92)
    usable = []
    for m in models:
        s = stats[m]
        bad = s["ratio"] < MIN_CREDIBLE_RATIO
        note = "images not counted -> excluded from cost" if bad else ""
        if not bad:
            usable.append(m)
        print(f"{m:<24}{s['tok_pt']:>11.0f}{s['tok_mm']:>12.0f}{s['ratio']:>8.2f}   {note}")
    print("-" * 92)
    print(f"{len(usable)}/{len(models)} models have credible multimodal token counts.")
    print("Reported counts are what the provider billed, so they are the ground "
          "truth where they are complete -- but they are not comparable across\n"
          "providers: the same 8 images cost 1.04x on Gemini and 4.75x on the "
          "DeepInfra-hosted InternVL3 models.")

    if not args.pareto:
        print("\n(pass --pareto for the quality/cost frontier)")
        return

    print()
    print("=" * 92)
    print("COST-AWARE ORACLE FRONTIER  (lambda = F1 points multimodal must win by)")
    print("=" * 92)
    lams = [0, 5, 10, 20, 30, 50, 100]
    print(f"{'model':<24}" + "".join(f"{'L=' + str(l):>9}" for l in lams))
    print("-" * 92)
    for m in usable:
        rows = data[m]
        cells = []
        for l in lams:
            f1, tok, share = pareto_point(rows, l)
            cells.append(f"{f1*100:>9.1f}")
        print(f"{m + ' F1':<24}" + "".join(cells))
        cells = []
        for l in lams:
            f1, tok, share = pareto_point(rows, l)
            saving = 1 - tok / stats[m]["tok_mm"]
            cells.append(f"{saving:>8.0%} ")
        print(f"{'  tokens vs always-mm':<24}" + "".join(cells))
    print("-" * 92)
    print("lambda=0 is the plain oracle; lambda=100 is always-pure-text. Each "
          "column is a router target: how much quality survives\nwhen multimodal "
          "is only paid for on questions where it clearly earns its cost.")


if __name__ == "__main__":
    main()
