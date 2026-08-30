from data_utils import load_jsonl
import os
import re
import nltk

# Resolve the NLTK corpora once instead of hitting the network on every run.
# Set MMDOCRAG_NLTK_DATA to point at a pre-populated directory for offline use.
_NLTK_DATA = os.environ.get("MMDOCRAG_NLTK_DATA")
if _NLTK_DATA:
    nltk.data.path.insert(0, _NLTK_DATA)
for _res in ('punkt', 'punkt_tab'):
    try:
        nltk.data.find(f'tokenizers/{_res}')
    except LookupError:
        nltk.download(_res, download_dir=_NLTK_DATA) if _NLTK_DATA else nltk.download(_res)
from nltk.translate.bleu_score import sentence_bleu
from nltk.tokenize import word_tokenize
from rouge_score import rouge_scorer
from tqdm import tqdm
import argparse
import os
import sys




model_dict = {
    "Qwen2.5-3B-Inst": "qwen2.5-3b",
    "Qwen2.5-3B-Inst-Fine-tuning": "qwen2.5-3b-ft",
    "Llama3.2-3B-Inst": "llama3.2-3b",
    "Qwen3-4B": "qwen3-4b",
    "Mistral-7B-Inst": "mistral-7b",
    "Qwen2.5-7B-Inst": "qwen2.5-7b",
    "Qwen2.5-7B-Inst-Fine-tuning": "qwen2.5-7b-ft",
    "Llama3.1-8B-Inst": "llama3.1-8b",
    "Qwen3-8B": "qwen3-8b",
    "Qwen2.5-14B-Inst": "qwen2.5-14b",
    "Qwen2.5-14B-Inst-Fine-tuning": "qwen2.5-14b-ft",
    "Qwen3-14B": "qwen3-14b",
    "Mistral-Small-24B-Inst": "mistral-small-24b",
    "Qwen3-30B-A3B": "qwen3-30b-a3b",
    "Qwen2.5-32B-Inst": "qwen2.5-32b",
    "Qwen2.5-32B-Inst-Fine-tuning": "qwen2.5-32b-ft",
    "Qwen3-32B": "qwen3-32b",
    "Mistral-8x7B-Inst": "mistral-8x7b",
    "Llama3.3-70B-Inst": "llama3.3-70b",
    "Qwen2.5-72B-Inst": "qwen2.5-72b",
    "Qwen2.5-72B-Inst-Fine-tuning": "qwen2.5-72b-ft",
    "Qwen3-235B-A22B": "qwen3-235b-a22b",
    "Deepseek-V3": "deepseek-v3",
    "Deepseek-R1": "deepseek-r1",
    "Deepseek-R1-Distill-Qwen-32B": "deepseek-r1-distill-qwen-32b",
    "Deepseek-R1-Distill-Llama-70B": "deepseek-r1-distill-llama-70b",
    "Qwen-Plus": "qwen-plus",
    "Qwen-Max": "qwen-max",
    "Gemini-1.5-Pro": "gemini-1.5-pro",
    "Gemini-2.0-Pro": "gemini-2.0-pro",
    "Gemini-2.0-Flash": "gemini-2.0-flash",
    "Gemini-2.0-Flash-Think": "gemini-2.0-flash-tk",
    "Gemini-2.5-Flash": "gemini-2.5-flash",
    "Gemini-2.5-Pro": "gemini-2.5-pro",
    # Not a model the paper evaluated. Added because the paper's own Gemini
    # models are no longer callable -- gemini-2.0-flash returns 404 and
    # gemini-2.5-flash is closed to new API keys -- so the end-to-end retrieval
    # comparison (E29) had to run on a current model. Its absolute scores are
    # therefore NOT comparable to any published row; only the paired
    # config-vs-config difference it produces is meaningful.
    "Gemini-3.6-Flash": "gemini-3.6-flash",
    "Claude-3.5-Sonnet": "claude-3.5-sonnet",
    "GPT-4-turbo": "gpt-4-turbo",
    "GPT-4o-mini": "gpt-4o-mini",
    "GPT-4o": "gpt-4o",
    "GPT-o3-mini": "gpt-o3-mini",
    "GPT-4.1-nano": "gpt-4.1-nano",
    "GPT-4.1-mini": "gpt-4.1-mini",
    "GPT-4.1": "gpt-4.1",
    "Janus-Pro-7B": "janus-pro-7b",
    "MiniCPM-o-2.6-8B": "minicpm-o-2.6-8b",
    "InternVL2.5-8B": "internvl2.5-8b",
    "InternVL3-8B": "internvl3-8b",
    "InternVL3-9B": "internvl3-9b",
    "InternVL3-14B": "internvl3-14b",
    "InternVL2.5-26B": "internvl2.5-26b",
    "InternVL2.5-38B": "internvl2.5-38b",
    "InternVL3-38B": "internvl3-38b",
    "InternVL2.5-78B": "internvl2.5-78b",
    "InternVL3-78B": "internvl3-78b",
    "Qwen2.5-VL-7B-Inst": "qwen2.5-vl-7b",
    "Qwen2.5-VL-32B-Inst": "qwen2.5-vl-32b",
    "Qwen2.5-VL-72B-Inst": "qwen2.5-vl-72b",
    "Qwen-VL-Plus": "qwen-vl-plus",
    "Qwen-VL-Max": "qwen-vl-max",
    "Qwen-QVQ-Max": "qwen-qvq-max",
    "Qwen-QwQ-Plus": "qwen-qwq-plus",
    "Llama4-Scout-17Bx16E": "llama4-scout-17b-16e",
    "Llama4-Mave-17Bx128E": "llama4-mave-17b-128e"
}

model_type = {
    'pure-text': ['Qwen2.5-3B-Inst', 'Qwen2.5-3B-Inst-Fine-tuning', 'Llama3.2-3B-Inst', 'Qwen3-4B',
                  'Qwen2.5-7B-Inst', 'Qwen2.5-7B-Inst-Fine-tuning', 'Mistral-7B-Inst', 'Llama3.1-8B-Inst',
                  'Qwen3-8B', 'Qwen2.5-14B-Inst', 'Qwen2.5-14B-Inst-Fine-tuning', 'Qwen3-14B',
                  'Mistral-Small-24B-Inst', 'Qwen3-30B-A3B', 'Qwen2.5-32B-Inst', 'Qwen2.5-32B-Inst-Fine-tuning',
                  'Qwen3-32B', 'Mistral-8x7B-Inst', 'Llama3.3-70B-Inst', 'Qwen2.5-72B-Inst',
                  'Qwen2.5-72B-Inst-Fine-tuning', 'Qwen3-235B-A22B', 'Deepseek-V3', 'Deepseek-R1',
                  'Deepseek-R1-Distill-Qwen-32B', 'Deepseek-R1-Distill-Llama-70B', 'Qwen-Plus', 'Qwen-Max',
                  'Qwen-QwQ-Plus', 'Gemini-1.5-Pro', 'Gemini-2.0-Pro', 'Gemini-2.0-Flash', 'Gemini-2.5-Pro',
                  'Gemini-2.0-Flash-Think', 'Gemini-2.5-Flash', 'Claude-3.5-Sonnet',  'GPT-4-turbo',
                  'GPT-4o-mini', 'GPT-4o', 'GPT-o3-mini', 'GPT-4.1-nano', 'GPT-4.1-mini', 'GPT-4.1'],
    'multi_modal': ['Janus-Pro-7B -', 'MiniCPM-o-2.6-8B -', 'InternVL2.5-8B', 'InternVL3-8B', 'InternVL3-9B',
                    'InternVL3-14B', 'InternVL2.5-26B', 'InternVL2.5-38B', 'InternVL3-38B', 'InternVL2.5-78B',
                    'InternVL3-78B', 'Qwen2.5-VL-7B-Inst', 'Qwen2.5-VL-32B-Inst', 'Qwen2.5-VL-72B-Inst',
                    'Llama4-Scout-17Bx16E', 'Llama4-Mave-17Bx128E', 'Qwen-VL-Plus', 'Qwen-VL-Max',
                    'Qwen-QVQ-Max', 'Gemini-1.5-Pro', 'Gemini-2.0-Pro', 'Gemini-2.0-Flash',
                    'Gemini-2.0-Flash-Think', 'Gemini-2.5-Flash', 'Gemini-2.5-Pro', 'Claude-3.5-Sonnet',
                    'GPT-4o-mini', 'GPT-4o', 'GPT-4.1-nano', 'GPT-4.1-mini', 'GPT-4.1']
}



def calculate_rouge(gold_str, predicted_str):
    scorer = rouge_scorer.RougeScorer(['rougeL'], use_stemmer=True)
    scores = scorer.score(gold_str, predicted_str)
    return scores

def calculate_bleu(reference, candidate):
    # Tokenizing the reference and candidate sentences
    reference_tokens = [word_tokenize(reference)]
    candidate_tokens = word_tokenize(candidate)
    # Calculating the BLEU score
    score = sentence_bleu(reference_tokens, candidate_tokens)
    return score

def strip_thinking(response):
    """Drop a reasoning model's chain-of-thought, keeping only the final answer.

    Extracted from calculate_all so anything scoring these same response files
    (the Phase 1A.5 router pipeline) preprocesses answers identically. Scoring a
    reasoning model's raw output would count citations that appear only in its
    scratchpad.
    """
    text = response if response else " "
    if "</think>\n\n" in text:
        return text.split("</think>\n\n")[1]
    if " seconds\n\n" in text:
        return text.split(" seconds\n\n")[1]
    return text


def extract_citations(text):
    citation_pattern = r'\[(\d+)\]'
    citations = re.findall(citation_pattern, text)

    image_pattern = r'\(image(\d+)\)'
    images = re.findall(image_pattern, text)

    txt_list = []
    for x in citations:
        txt_list.append("text" + x)
    txt_list = list(dict.fromkeys(txt_list))

    img_list = []
    for x in images:
        img_list.append("image" + x)
    img_list = list(dict.fromkeys(img_list))

    return txt_list, img_list, txt_list + img_list

def get_scores(gold_labels, predicted_labels):
    true_positives = set(gold_labels).intersection(predicted_labels)
    false_positives = set(predicted_labels).difference(gold_labels)
    false_negatives = set(gold_labels).difference(predicted_labels)
    tp = len(true_positives)
    fp = len(false_positives)
    fn = len(false_negatives)
    precision = tp / (tp + fp) if (tp + fp) != 0 else 0
    recall = tp / (tp + fn) if (tp + fn) != 0 else 0
    f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) != 0 else 0
    return precision, recall, f1_score

def index_by_qid(data, name):
    """Index a jsonl payload by q_id, keeping the first row per id (file order)."""
    idx = {}
    dupes = 0
    for item in data:
        qid = item["q_id"]
        if qid in idx:
            dupes += 1
            continue
        idx[qid] = item
    if dupes:
        print(f"[warn] {name}: ignored {dupes} duplicate q_id row(s), kept first occurrence")
    return idx


def align_by_qid(gold_data, eval_data, llm_data, require_full=False):
    """Join gold / response / judge on q_id and report coverage.

    The previous implementation zipped the three payloads positionally. zip()
    stops at the shortest input, so a partially written response file (e.g. an
    interrupted inference run) was silently averaged over fewer questions and
    still reported a headline score. Joining on q_id makes any shortfall
    explicit instead.
    """
    gold_idx = index_by_qid(gold_data, "gold")
    eval_idx = index_by_qid(eval_data, "response")
    llm_idx = index_by_qid(llm_data, "llm-judge")

    gold_order = list(gold_idx)  # dict preserves gold file order
    metric_qids = [q for q in gold_order if q in eval_idx]
    judge_qids = [q for q in metric_qids if q in llm_idx]

    n_gold = len(gold_idx)
    print('-------------------------------')
    print('-----------COVERAGE------------')
    print('-------------------------------')
    print(f"gold questions      : {n_gold}")
    print(f"scored (response)   : {len(metric_qids)}/{n_gold} ({len(metric_qids) / n_gold * 100:.2f}%)")
    print(f"scored (llm-judge)  : {len(judge_qids)}/{n_gold} ({len(judge_qids) / n_gold * 100:.2f}%)")

    for label, extra in (("response", set(eval_idx) - set(gold_idx)),
                         ("llm-judge", set(llm_idx) - set(gold_idx))):
        if extra:
            print(f"[warn] {label}: {len(extra)} q_id(s) absent from gold, ignored "
                  f"(e.g. {sorted(extra)[:5]})")
    if len(judge_qids) < len(metric_qids):
        print(f"[warn] llm-judge covers only {len(judge_qids)} of the {len(metric_qids)} "
              f"scored questions; judge averages use that subset")

    if not metric_qids:
        raise ValueError("no overlapping q_id between gold and response files")
    if require_full and (len(metric_qids) < n_gold or len(judge_qids) < n_gold):
        raise ValueError(
            f"--require-full: incomplete coverage "
            f"(response {len(metric_qids)}/{n_gold}, judge {len(judge_qids)}/{n_gold})")

    return gold_idx, eval_idx, llm_idx, metric_qids, judge_qids


def calculate_all(gold_data, eval_data, llm_data, require_full=False):
    prec_list, recall_list, f1_list = [], [], []
    gold_txt_list, gold_img_list = [], []
    pred_txt_list, pred_img_list = [], []
    in_tok_list, out_tok_list = [], []
    bleu_score_list, rougel_list = [], []

    gold_idx, eval_idx, llm_idx, metric_qids, judge_qids = align_by_qid(
        gold_data, eval_data, llm_data, require_full=require_full)

    for qid in tqdm(metric_qids):
        gold_item, eval_item = gold_idx[qid], eval_idx[qid]

        gold_quotes = gold_item["gold_quotes"]
        predicted_str = strip_thinking(eval_item["response"])

        txt_quotes, img_quotes, eval_quotes = extract_citations(predicted_str)
        precision, recall, f1_score = get_scores(gold_quotes, eval_quotes)

        for x in gold_quotes:
            if x.startswith("text"):
                gold_txt_list.append(str(qid) + x)
            else:
                gold_img_list.append(str(qid) + x)

        if len(img_quotes) > 0:
            img_quotes = [str(qid) + x for x in img_quotes]
            pred_img_list.extend(img_quotes)
        if len(txt_quotes) > 0:
            txt_quotes = [str(qid) + x for x in txt_quotes]
            pred_txt_list.extend(txt_quotes)

        prec_list.append(precision)
        recall_list.append(recall)
        f1_list.append(f1_score)
        if "in_tok" in eval_item and "out_tok" in eval_item:
            in_tok_list.append(eval_item["in_tok"])
            out_tok_list.append(eval_item["out_tok"])

        gold_str = gold_item["answer_interleaved"]

        bleu_score = calculate_bleu(gold_str, predicted_str)
        bleu_score_list.append(bleu_score)
        rouge = calculate_rouge(gold_str, predicted_str)
        rl_prec, rl_rec, rl_f1 = rouge["rougeL"].precision, rouge["rougeL"].recall, rouge["rougeL"].fmeasure

        rougel_list.append(rl_f1)

    final_f1 = sum(f1_list) / len(f1_list)

    final_bleu = sum(bleu_score_list) / len(bleu_score_list)
    final_rougel = sum(rougel_list) / len(rougel_list)


    img_precison, img_recall, img_f1 = get_scores(gold_img_list, pred_img_list)
    txt_precison, txt_recall, txt_f1 = get_scores(gold_txt_list, pred_txt_list)


    in_tok_len = sum(in_tok_list) / len(in_tok_list) if in_tok_list else 0
    out_tok_len = sum(out_tok_list) / len(out_tok_list) if out_tok_list else 0

    # Judge scores are averaged over the same q_id set the automatic metrics
    # used, so both halves of the table describe the same questions.
    count = len(judge_qids)
    average = 0  # for average score calculation
    fluency, citation, coherence, logic, factuality = 0, 0, 0, 0, 0

    for qid in judge_qids:
        item = llm_idx[qid]
        fluency += item['response'].get("Fluency", 0)
        citation += item['response'].get("Citation Quality", 0)
        coherence += item['response'].get('Text-Image Coherence', 0)
        logic += item['response'].get('Reasoning Logic', 0)
        factuality += item['response'].get('Factuality', 0)
        average += (item['response'].get('Fluency', 0) +
                    item['response'].get("Citation Quality", 0) +
                    item['response'].get('Text-Image Coherence', 0) +
                    item['response'].get('Reasoning Logic', 0) +
                    item['response'].get('Factuality', 0)) / 5
    count = count or 1  # keep the print block safe when no judge file matched


    print('-------------------------------')
    print('------------RESULT-------------')
    print('-------------------------------')
    print(f"in_tok_len:{in_tok_len:.1f}  out_tok_len: {out_tok_len:.1f}  img_precison:{img_precison * 100:.1f}  img_recall: {img_recall * 100:.1f}  ")
    print(f"img_f1:{img_f1 * 100:.1f}  txt_precison：{txt_precison * 100:.1f} txt_recall：{txt_recall * 100:.1f}   txt_f1：{txt_f1 * 100:.1f} ")
    print(f"final_f1：{final_f1 * 100:.1f} ")
    print(f"bleu: {final_bleu:.3f}  rougel: {final_rougel:.3f}")
    print(f'Fluency average：{fluency / count:.2f}    Citation Quality ：{citation / count:.2f}   Text-Image Coherence ：{coherence / count:.2f}')
    print(f'Reasoning Logic：{logic / count:.2f}    Factuality ：{factuality / count:.2f}    total ：{average / count:.2f}')

    print(
        f"{in_tok_len:.1f} & {out_tok_len:.1f} & {img_precison * 100:.1f} & {img_recall * 100:.1f} & {img_f1 * 100:.1f} & {txt_precison * 100:.1f} & "
        f"{txt_recall * 100:.1f} & {txt_f1 * 100:.1f} &\\cellcolor{{lightgreen}}{final_f1 * 100:.1f} & {final_bleu:.3f} & {final_rougel:.3f}")

    return {
        "n_gold": len(gold_idx),
        "n_scored": len(metric_qids),
        "n_judged": len(judge_qids),
        "in_tok_len": in_tok_len, "out_tok_len": out_tok_len,
        "img_precision": img_precison * 100, "img_recall": img_recall * 100,
        "img_f1": img_f1 * 100,
        "txt_precision": txt_precison * 100, "txt_recall": txt_recall * 100,
        "txt_f1": txt_f1 * 100,
        "final_f1": final_f1 * 100,
        "bleu": final_bleu, "rougel": final_rougel,
        "judge_fluency": fluency / count, "judge_citation": citation / count,
        "judge_coherence": coherence / count, "judge_logic": logic / count,
        "judge_factuality": factuality / count, "judge_total": average / count,
    }


def initialize_args():
    parser = argparse.ArgumentParser(description="Evaluation Script for LLMs")
    # '15' and '20' are the official settings. The choices list is not enforced
    # because retrieval experiments score their own candidate sets under their
    # own tag (dataset/evaluation_<tag>.jsonl); behaviour for '15' and '20' is
    # unchanged.
    parser.add_argument('--setting', default='20',
                        help='15 | 20 | a custom tag naming dataset/evaluation_<tag>.jsonl')
    # Task 1: reproduce from the response and llm-judge files
    parser.add_argument('--model', type=str, help='Model name, e.g. qwen3-4b')
    parser.add_argument('--mode', choices=['pure-text', 'multimodal'], default='pure-text')
    # Task 1: pass in your own response and llm-judge files
    parser.add_argument('--path', type=str, help='Path to response JSONL file')
    parser.add_argument('--path_judge', type=str, help='Path to response evaluation JSONL file')
    # The LLM judge is a secondary metric. Quote-selection P/R/F1 is computed
    # locally from the citations, so a run that never paid for a judge pass is
    # still fully scorable on the primary metric -- but only if asked for
    # explicitly, so a missing judge file is never silently ignored.
    parser.add_argument('--no-judge', dest='no_judge', action='store_true',
                        help='Score without an LLM-judge file. Judge columns are '
                             'reported as unavailable rather than omitted silently.')
    parser.add_argument('--require-full', dest='require_full', action='store_true',
                        help='Fail instead of scoring when response/judge coverage is below 100%%')
    parser.add_argument('--no-manifest', dest='no_manifest', action='store_true',
                        help='Skip writing a run manifest under manifests/')
    return parser.parse_args()


def get_jsonl_path(args):
    setting = args.setting
    gold_path = f'dataset/evaluation_{setting}.jsonl'

    # Task 1: reproduce from the response and llm-judge files
    if args.model:
        model = args.model
        mode = args.mode
        eval_path = f'response/{model}_{mode}_quotes{setting}_response.jsonl'

        if model not in model_dict.values():
            raise ValueError('error, not support that model')
        elif (not os.path.exists(eval_path)):
            raise ValueError(f"path: {eval_path} does not exist.")
            # elif (not os.path.exists(eval_path)) or (model not in model_type[mode]):
            # raise ValueError(f" Error: model exists but does not support `{mode}` mode. ")

        llm_judge_path = f'response/evaluation/{model}_{mode}_quotes{setting}_llm-judge.jsonl'
        if not os.path.exists(llm_judge_path):
            if getattr(args, 'no_judge', False):
                print(f"[no-judge] {llm_judge_path} absent; judge metrics unavailable")
                return eval_path, None, gold_path
            raise ValueError(f" Error: Judge file not found: {llm_judge_path}")
        return eval_path, llm_judge_path, gold_path

    # Task 1: pass in your own response and llm-judge files
    elif args.path and args.path_judge:
        eval_path = args.path
        llm_judge_path = args.path_judge
        if not os.path.exists(eval_path):
            raise ValueError(f" Error: Eval path does not exist: {eval_path}")
        if not os.path.exists(llm_judge_path):
            raise ValueError(f" Error: Judge path does not exist: {llm_judge_path}")
        return eval_path, llm_judge_path, gold_path

    else:
        raise ValueError(" Error: Must provide either --model or both --path and --path_judge")



if __name__ == '__main__':
    # get the jsonl path of gold, inference-response, and llm-judge.
    args = initialize_args()
    eval_path, llm_judge_path, gold_path = get_jsonl_path(args)
    print("Eval path:", eval_path)
    print("Judge path:", llm_judge_path)
    print("Gold path:", gold_path)

    gold_data, eval_data = load_jsonl(gold_path), load_jsonl(eval_path)
    # An absent judge file yields an empty list, not a crash: align_by_qid then
    # reports 0% judge coverage explicitly, which is the honest rendering.
    llm_data = load_jsonl(llm_judge_path) if llm_judge_path else []
    results = calculate_all(gold_data, eval_data, llm_data, require_full=args.require_full)

    if not args.no_manifest:
        import manifest
        tag = args.model or os.path.splitext(os.path.basename(eval_path))[0]
        out = manifest.write(
            f"eval_all/{tag}_{args.mode}_{args.setting}",
            data_files=[p for p in (gold_path, eval_path, llm_judge_path) if p],
            extra={"model": args.model, "mode": args.mode, "setting": args.setting,
                   "eval_path": eval_path, "judge_path": llm_judge_path,
                   "gold_path": gold_path, "require_full": args.require_full},
            results=results,
        )
        print("manifest:", os.path.relpath(out, os.path.dirname(os.path.abspath(__file__))))











