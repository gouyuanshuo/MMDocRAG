from data_utils import load_jsonl, save_jsonl
import os
from tqdm import tqdm
import argparse
from inference_wrapper import OpenAI_LLM_Judge

JUDGE_KEY_ENV = "OPENAI_API_KEY"


def initialize_args():
    '''
    Example: eval_llm_judge.py response/qwen3-4b_pure-text_quotes20_response.jsonl --setting 20
    '''
    parser = argparse.ArgumentParser()
    parser.add_argument('path', type=str,
                        help='Inference response path, e.g. response/qwen3-4b_pure-text_quotes20_response.jsonl')
    parser.add_argument('--setting', choices=['20', '15'], default='20',
                        help='Number of quotes used for inference, 15 or 20')
    # Judging every answer is a paid GPT-4o call, so resume by default. The 62
    # incomplete llm-judge files shipped with the benchmark are what an
    # interrupted, non-resumable run leaves behind.
    parser.add_argument('--resume', dest='resume', action='store_true', default=True)
    parser.add_argument('--no-resume', dest='resume', action='store_false',
                        help='Ignore any existing judge file and re-judge every answer')
    return parser.parse_args()


if __name__ == '__main__':
    args = initialize_args()

    api_key = os.environ.get(JUDGE_KEY_ENV, "")
    if not api_key:
        raise SystemExit(
            f"missing OpenAI API key: set the {JUDGE_KEY_ENV} environment variable "
            f"before running the LLM judge")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    llm_judge = OpenAI_LLM_Judge(api_key=api_key, base_url=base_url, setting=args.setting)

    file_path = args.path
    file_name = os.path.basename(file_path)
    out_path = os.path.join("response", "evaluation",
                            file_name.replace("_response.jsonl", "_llm-judge.jsonl"))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    data_json = load_jsonl(file_path)

    out_jsonl, done = [], set()
    if args.resume and os.path.exists(out_path):
        out_jsonl = load_jsonl(out_path)
        done = {r["q_id"] for r in out_jsonl if r.get("response")}
        out_jsonl = [r for r in out_jsonl if r["q_id"] in done]
        print(f"[resume] {len(done)}/{len(data_json)} already judged in {out_path}; "
              f"judging the remaining {len(data_json) - len(done)}")

    for i, item in enumerate(tqdm(data_json)):
        q_id = item["q_id"]
        if q_id in done:
            continue
        pred_answer = item["response"] if item["response"] else " "
        result = llm_judge.get_api_response(q_id, pred_answer)
        out_jsonl.append(result)

        if len(out_jsonl) > 0:
            save_jsonl(out_jsonl, out_path)

    judged = sum(1 for r in out_jsonl if r.get("response"))
    print(f"[done] {judged}/{len(data_json)} answers judged -> {out_path}")
    if judged < len(data_json):
        print(f"[warn] {len(data_json) - judged} answer(s) still unjudged; "
              f"re-run the same command to resume")
