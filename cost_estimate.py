"""Estimate the API spend for the experiment plan.

Token volumes are not guessed. The generation side is measured directly from
the `in_tok` / `out_tok` fields the benchmark authors recorded in the shipped
response files, so it reflects what the providers actually billed for these
exact prompts. The judge side is derived from the real prompt and answer
lengths, converted with a chars-per-token ratio calibrated against those same
measured counts.

Prices are per million tokens, in USD, checked 2026-08-24. They move; re-check
before relying on a total. Run with --prices to see the table and its sources.

Usage:
    python cost_estimate.py                    # per-run costs + plan roll-up
    python cost_estimate.py --plan-only
    python cost_estimate.py --questions 200    # pilot-sized run
"""

import argparse
import collections
import json
import os
import re
import statistics
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
EVAL_SET_SIZE = 2000

# USD per 1M tokens, as (input, output). Checked 2026-08-24.
#   gpt-5-*            https://platform.openai.com/docs/pricing
#   gemini-*           https://ai.google.dev/gemini-api/docs/pricing
#   deepinfra-hosted   https://deepinfra.com/pricing
PRICES = {
    "gpt-5-nano":            (0.05, 0.40),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "qwen2.5-72b @deepinfra": (0.23, 0.23),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gpt-5-mini":            (0.25, 2.00),
    "deepseek-v3.2 @deepinfra": (0.26, 0.38),
}

# Only these carry vision; a pure-text model cannot run the multimodal arm.
VISION_CAPABLE = {"gpt-5-nano", "gpt-5-mini", "gemini-2.5-flash-lite",
                  "gemini-3.1-flash-lite"}

# How many full generation passes over the evaluation set each phase needs.
# Phase 1A and 1A.5 are absent on purpose: both score responses that already
# ship with the repo, so they cost nothing. Phase 1B is retrieval only -- its
# recall metrics are computed locally against the canonical layer.
DEFAULT_PLAN = [
    ("Phase 2  static baselines",      10, "mixed"),
    ("Phase 3  router end-to-end",      4, "mixed"),
    ("Phase 4  granularity",            8, "mixed"),
    ("Phase 5  dynamic top-k",          5, "pure-text"),
]


def measure_generation(response_dir):
    """Mean input/output tokens per question, from the shipped response files."""
    agg = collections.defaultdict(lambda: {"in": [], "out": []})
    pattern = re.compile(
        r"(.+)_(pure-text|pure-text_ocr|multimodal)_quotes(15|20)_response\.jsonl$")
    for name in sorted(os.listdir(response_dir)):
        m = pattern.match(name)
        if not m or m.group(2) == "pure-text_ocr":
            continue
        mode, setting = m.group(2), m.group(3)
        with open(os.path.join(response_dir, name), encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("in_tok"):
                    agg[(mode, setting)]["in"].append(rec["in_tok"])
                if rec.get("out_tok"):
                    agg[(mode, setting)]["out"].append(rec["out_tok"])
    return {k: (statistics.mean(v["in"]), statistics.mean(v["out"]), len(v["in"]))
            for k, v in agg.items()}


def calibrate_chars_per_token(dataset_dir, response_dir, sample=400):
    """chars/token, from a reconstructed prompt vs the provider's own count."""
    gold_path = os.path.join(dataset_dir, "evaluation_20.jsonl")
    resp_path = os.path.join(response_dir, "gpt-4o_pure-text_quotes20_response.jsonl")
    if not (os.path.exists(gold_path) and os.path.exists(resp_path)):
        return 3.9  # fallback: typical English ratio
    sys_msg = open(os.path.join(REPO_ROOT, "prompt_bank", "pure_text_infer.txt"),
                   encoding="utf-8").read()
    resp = {}
    with open(resp_path, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            resp[r["q_id"]] = r
    ratios = []
    with open(gold_path, encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if i >= sample:
                break
            g = json.loads(line)
            body = sys_msg + g["question"]
            body += "".join(t["text"] for t in g["text_quotes"])
            body += "".join(im.get("img_description") or "" for im in g["img_quotes"])
            tok = resp.get(g["q_id"], {}).get("in_tok")
            if tok:
                ratios.append(len(body) / tok)
    return statistics.median(ratios) if ratios else 3.9


def measure_judge(dataset_dir, chars_per_token, setting="20"):
    """Judge input/output tokens per question."""
    sys_msg = open(os.path.join(REPO_ROOT, "prompt_bank", "evaluation_answer.txt"),
                   encoding="utf-8").read()
    chars = []
    with open(os.path.join(dataset_dir, f"evaluation_{setting}.jsonl"),
              encoding="utf-8") as fh:
        for line in fh:
            g = json.loads(line)
            chars.append(len(sys_msg) + len(g["question"])
                         + len(str(g.get("answer_short", "")))
                         + len(g.get("answer_interleaved", "")))
    # plus the answer being judged, which is the generator's output
    return statistics.median(chars) / chars_per_token, 60.0


def cost(in_tok, out_tok, n, price):
    pin, pout = price
    return (in_tok * n / 1e6) * pin + (out_tok * n / 1e6) * pout


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dataset-dir", default=os.path.join(REPO_ROOT, "dataset"))
    ap.add_argument("--response-dir", default=os.path.join(REPO_ROOT, "response"))
    ap.add_argument("--questions", type=int, default=EVAL_SET_SIZE,
                    help="questions per run (2000 = full evaluation set)")
    ap.add_argument("--setting", choices=["15", "20"], default="20")
    ap.add_argument("--judge-model", default="gpt-5-nano",
                    help="model used for LLM-as-judge")
    ap.add_argument("--plan-only", action="store_true")
    ap.add_argument("--prices", action="store_true", help="print the price table and exit")
    args = ap.parse_args()

    if args.prices:
        print(f"{'model':<26}{'$/1M in':>10}{'$/1M out':>10}{'vision':>9}")
        for name, (pin, pout) in sorted(PRICES.items(), key=lambda kv: kv[1][0]):
            print(f"{name:<26}{pin:>10.2f}{pout:>10.2f}"
                  f"{'yes' if name in VISION_CAPABLE else 'no':>9}")
        print("\nChecked 2026-08-24; see module docstring for sources.")
        return

    gen = measure_generation(args.response_dir)
    cpt = calibrate_chars_per_token(args.dataset_dir, args.response_dir)
    j_in_base, j_out = measure_judge(args.dataset_dir, cpt)
    n = args.questions

    print("=" * 78)
    print("MEASURED TOKEN VOLUMES  (from the shipped response files)")
    print("=" * 78)
    print(f"{'mode':<12}{'quotes':>7}{'samples':>9}{'in/question':>13}{'out/question':>14}")
    for (mode, setting), (i, o, cnt) in sorted(gen.items()):
        print(f"{mode:<12}{setting:>7}{cnt:>9}{i:>13.0f}{o:>14.0f}")
    print(f"\ncalibrated chars/token = {cpt:.2f}")
    print(f"judge input/question   = {j_in_base:.0f} + the answer being judged")

    if not args.plan_only:
        print()
        print("=" * 78)
        print(f"COST OF ONE RUN  ({n} questions, {args.setting} quotes, generation + judge)")
        print("=" * 78)
        print(f"{'model':<26}{'pure-text':>14}{'multimodal':>14}{'judge':>12}")
        for name, price in sorted(PRICES.items(), key=lambda kv: kv[1][0]):
            row = f"{name:<26}"
            for mode in ("pure-text", "multimodal"):
                key = (mode, args.setting)
                if key not in gen:
                    row += f"{'n/a':>14}"
                elif mode == "multimodal" and name not in VISION_CAPABLE:
                    row += f"{'no vision':>14}"
                else:
                    i, o, _ = gen[key]
                    row += f"{'$' + format(cost(i, o, n, price), '.2f'):>14}"
            # judging one run's answers
            _, gout, _ = gen[("pure-text", args.setting)]
            jc = cost(j_in_base + gout, j_out, n, PRICES[args.judge_model])
            row += f"{'$' + format(jc, '.2f'):>12}"
            print(row)
        print(f"\njudge column uses {args.judge_model}; it is the same cost whichever "
              f"model produced the answers.")

    # ---- plan roll-up ----
    print()
    print("=" * 78)
    print(f"PLAN ROLL-UP  (cheapest viable: gpt-5-nano generation + gpt-5-nano judge)")
    print("=" * 78)
    gen_price = PRICES["gpt-5-nano"]
    judge_price = PRICES[args.judge_model]
    _, gout, _ = gen[("pure-text", args.setting)]

    def run_cost(mode):
        i, o, _ = gen[(mode, args.setting)]
        g = cost(i, o, n, gen_price)
        j = cost(j_in_base + gout, j_out, n, judge_price)
        return g + j

    pt, mm = run_cost("pure-text"), run_cost("multimodal")
    mixed = (pt + mm) / 2
    total = 0.0
    print(f"{'phase':<32}{'runs':>6}{'mode':>12}{'$/run':>10}{'subtotal':>12}")
    for label, runs, mode in DEFAULT_PLAN:
        per = {"pure-text": pt, "multimodal": mm, "mixed": mixed}[mode]
        sub = per * runs
        total += sub
        print(f"{label:<32}{runs:>6}{mode:>12}"
              f"{'$' + format(per, '.2f'):>10}{'$' + format(sub, '.2f'):>12}")
    print("-" * 78)
    print(f"{'TOTAL':<32}{'':>6}{'':>12}{'':>10}{'$' + format(total, '.2f'):>12}")
    print()
    print(f"Phase 1A and 1A.5 cost $0: both score the {len(os.listdir(args.response_dir)) - 1} "
          f"response files that ship with the repo.")
    print("Phase 1B costs $0 in API terms: retrieval recall is computed locally.")
    print()
    print("Add ~20-30% headroom for pilot runs, retries and failed calls. Prompt "
          "caching does not help here: each question carries its own 3.5k-token "
          "quote block, so there is no shared prefix to cache.")


if __name__ == "__main__":
    main()
