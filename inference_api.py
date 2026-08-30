from data_utils import load_jsonl, save_jsonl
from tqdm import tqdm
import json
import os
import sys
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from expkit import apilog                                   # noqa: E402
from expkit.paths import rel                                # noqa: E402

# Every API call is logged to artifacts/api/<tag>/requests.jsonl before the
# response file is touched. That log -- not the response JSONL -- is the record
# of what was spent: it keeps failures, rate-limit details, token usage and
# latency, none of which survive into the response file. See expkit/apilog.py.
PROMPT_FOR_MODE = {"pure-text": "prompt_bank/pure_text_infer.txt",
                   "multimodal": "prompt_bank/multimodal_infer.txt"}


def provider_of(model_name):
    m = model_name.lower()
    for prefix, name in (("gemini", "gemini"), ("gpt", "openai"), ("o", "openai"),
                         ("grok", "grok"), ("claude", "anthropic"),
                         ("qwen", "qwen"), ("qvq", "qwen"), ("qwq", "qwen"),
                         ("llama-4", "qwen"), ("mock", "mock")):
        if m.startswith(prefix):
            return name
    return "deepinfra"

# API keys come from the environment so they never land in the repo. Set the
# variable for whichever provider you are calling, e.g.
#   PowerShell:  $env:OPENAI_API_KEY = "sk-..."
#   bash:        export OPENAI_API_KEY=sk-...
API_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
    "grok": "XAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "deepinfra": "DEEPINFRA_API_KEY",
}


def load_api_keys():
    return {provider: os.environ.get(env, "") for provider, env in API_KEY_ENV.items()}


def require_key(api_keys, provider):
    key = api_keys.get(provider) or ""
    if not key:
        raise SystemExit(
            f"missing API key for '{provider}': set the {API_KEY_ENV[provider]} "
            f"environment variable before running inference")
    return key


def initialize_infer(api_keys, model_name, mode, enable_thinking):
    # inference for Google Gemini models
    if model_name.startswith("gemini"):
        from inference_wrapper import Gemini_Inference
        api_key = require_key(api_keys, "gemini")
        return Gemini_Inference(api_key=api_key, model=model_name, mode=mode)

    # inference for OpenAI related models
    elif model_name.startswith("gpt") or model_name.startswith("o"):
        from inference_wrapper import OpenAI_Inference
        api_key = require_key(api_keys, "openai")
        base_url = "https://api.openai.com/v1"
        return OpenAI_Inference(api_key=api_key, base_url=base_url, model=model_name, mode=mode)

    # inference for Grok related models
    elif model_name.startswith("grok"):
        from inference_wrapper import OpenAI_Inference
        api_key = require_key(api_keys, "grok")
        base_url = "https://api.x.ai/v1"
        return OpenAI_Inference(api_key=api_key, base_url=base_url, model=model_name, mode=mode)

    # inference for Qwen related models
    elif model_name.startswith("qwen") or model_name.startswith("qvq") or model_name.startswith("qwq") or model_name.startswith("llama-4"):
        api_key = require_key(api_keys, "qwen")
        base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        if model_name.startswith("qwen3") or model_name.startswith("qvq") or model_name.startswith("qwq"): # specifically for Qwen 3 related models
            from inference_wrapper import Qwen3_inference
            return Qwen3_inference(api_key=api_key, base_url=base_url, model=model_name, mode=mode,
                                        enable_thinking=enable_thinking)
        else: # for Qwen 2.5 and other commercial related models
            from inference_wrapper import OpenAI_Inference
            return OpenAI_Inference(api_key=api_key, base_url=base_url, model=model_name, mode=mode)

    # inference for Anthropic related models
    elif model_name.startswith("claude"):
        from inference_wrapper import Anthropic_Inference
        api_key = require_key(api_keys, "anthropic")
        return Anthropic_Inference(api_key=api_key, model=model_name, mode=mode)

    # inference for open-sourced llama/mistral/deepseek models from deepinfra
    elif model_name.startswith("m") or model_name.startswith("d"):
        from inference_wrapper import OpenAI_Inference
        api_key = require_key(api_keys, "deepinfra")
        base_url = "https://api.deepinfra.com/v1/openai"
        return OpenAI_Inference(api_key=api_key, base_url=base_url, model=model_name, mode=mode)

    else:
        raise ValueError("cannot find a suitable api provider. please check your model name!")


def initialize_args():
    '''
    Example: inference_api.py qwen3-32b --setting 20 --mode pure-text --no-enable-thinking
    --setting parameter is to pass either 15 or 20 quotes for evaluation.
    --mode parameter is to control passing quotes as either pure-text or multimodal inputs.
    --no-enable-thinking parameter is to disable thinking process for Qwen3 model, which
    does not applicable to non-Qwen3 models.
    '''
    parser = argparse.ArgumentParser()
    parser.add_argument('model_name', type=str, help='Model name, e.g. qwen3-32b')
    # --setting names both the input file (dataset/evaluation_<setting>.jsonl)
    # and the output file, so it doubles as a run tag. The official values are
    # '20' and '15'; the choices list is not enforced because retrieval
    # experiments feed in their own candidate sets under their own tag (e.g.
    # 'oursk10') and must not overwrite each other's responses. Behaviour for
    # '20' and '15' is unchanged.
    parser.add_argument('--setting', default='20',
                        help="20 | 15 | a custom tag naming "
                             "dataset/evaluation_<tag>.jsonl")
    parser.add_argument('--mode', choices=['pure-text', 'multimodal'], default='pure-text')
    # Boolean flag: True by default, set to False with --no-enable-thinking
    parser.add_argument('--enable-thinking', dest='enable_thinking', action='store_true', default=True)
    parser.add_argument('--no-enable-thinking', dest='enable_thinking', action='store_false')
    # Resume is on by default: API calls cost money, so re-running should pick
    # up where the last run stopped unless a fresh run is asked for explicitly.
    parser.add_argument('--resume', dest='resume', action='store_true', default=True)
    parser.add_argument('--no-resume', dest='resume', action='store_false',
                        help='Ignore any existing response file and re-run every question')
    # Free API tiers are rate limited per minute, and the wrapper only backs off
    # AFTER a request fails. Firing at full speed there means most requests 429,
    # each burning a retry, so pacing proactively is both faster overall and
    # cheaper in quota. 0 disables pacing (the previous behaviour).
    # A free-tier daily cap does not raise a distinct error the loop can see --
    # every remaining question just fails. Without this the run would keep pacing
    # through hundreds of doomed requests for hours. Stopping lets --resume pick
    # up cleanly the next day.
    # A 1,200-call job runs for hours, and anything that supervises it -- a CI
    # step, a background task slot, a laptop lid -- can end it mid-request. That
    # loses the in-flight call's spend without recording it, and can leave a torn
    # final line in the log. Bounding the run by request count instead lets each
    # segment finish a call, flush, and exit 0, with --resume carrying the rest.
    parser.add_argument('--max-requests', type=int, default=0,
                        help='stop cleanly after issuing this many requests '
                             '(0 = no bound). Use it to fit a long job inside a '
                             'supervisor timeout: --resume continues where the '
                             'previous segment stopped, and nothing is re-paid.')
    parser.add_argument('--stop-after-failures', type=int, default=10,
                        help='Abort after this many CONSECUTIVE failures '
                             '(typically the daily quota running out). 0 = never.')
    # A mock provider exists so the persistence, resume and error paths can be
    # exercised without spending quota. Testing a payment path against the real
    # endpoint means paying to discover that the logging works.
    parser.add_argument('--mock', action='store_true',
                        help='use a deterministic offline fake provider; no '
                             'network, no spend. For testing persistence/resume.')
    parser.add_argument('--mock-fail', default='',
                        help='comma-separated q_ids the mock provider should fail')
    parser.add_argument('--mock-rate-limit', default='',
                        help='comma-separated q_ids the mock provider should 429')
    parser.add_argument('--force', action='store_true',
                        help='re-issue requests that already succeeded (costs money)')
    parser.add_argument('--api-log-tag', default='',
                        help='name under artifacts/api/ (default: model_mode_setting)')
    parser.add_argument('--experiment-id', default='',
                        help='experiment id to stamp into every request record')
    parser.add_argument('--plan-only', action='store_true',
                        help='write the call plan and exit without calling anything')
    # Test isolation. A mock provider must not deposit fake responses beside
    # real ones: `response/` is the record of what was actually paid for.
    parser.add_argument('--dataset-dir', default='dataset',
                        help='directory holding evaluation_<setting>.jsonl')
    parser.add_argument('--response-dir', default='response',
                        help='where to write the response JSONL. Point this at '
                             'artifacts/test-runs/<id>/ for mock runs.')
    parser.add_argument('--rpm', type=float, default=0,
                        help='Throttle to at most this many requests per minute. '
                             'Gemini free tier: 10 for gemini-2.0-flash, '
                             '15 for flash-lite. 0 = no pacing.')
    return parser.parse_args()


if __name__ == '__main__':
    '''   
    All you need to do is to get a api key from the corresponding websites.
    1. For Google Gemini key, please visit https://ai.google.dev/gemini-api/docs/api-key
    2. For Anthropic key, please visit https://console.anthropic.com/settings/keys
    3. For OpenAI key, please visit https://platform.openai.com/api-keys
    4. For Alibaba Cloud Qwen key, please visit https://bailian.console.aliyun.com/?tab=api#/api
    5. For Deepinfra key, please visit https://deepinfra.com/dash/api_keys
    '''
    api_keys = load_api_keys()

    '''
    This is the models used in our experiment, which can be inferred using API function calls.
    No pre-trained checkpoint is need.
    "multimodal" refers that the large model can process interleaved text-image inputs.
    "pure-text" refers that only text inputs can be processed.
    '''
    available_models = {
        "Google Gemini": {
            "gemini-1.5-pro": "multimodal",
            "gemini-2.0-flash-exp": "multimodal",
            "gemini-2.0-flash-thinking-exp": "multimodal",
            "gemini-2.0-pro-exp-02-05": "multimodal",
            "gemini-2.5-pro-exp-03-25": "multimodal",
            "gemini-2.5-pro-preview-03-25": "multimodal",
            "gemini-2.5-flash-preview-04-17": "multimodal",
        },
        "Anthropic": {
            "claude-3-5-sonnet-20241022": "multimodal",
            "claude-3-7-sonnet-20250219": "multimodal",
        },
        "OpenAI": {
            "gpt-4o": "multimodal",
            "gpt-4o-mini": "multimodal",
            "gpt-4-turbo": "multimodal",
            "o3-mini": "pure-text",
            "gpt-4.1": "multimodal",
            "gpt-4.1-nano": "multimodal",
            "gpt-4.1-mini": "multimodal",
        },
        "Alibaba Cloud": {
            "qwen-plus": "pure-text",
            "qwen-max": "pure-text",
            "qwen-vl-plus": "multimodal",
            "qwen-vl-max": "multimodal",
            "qwen2.5-3b-instruct": "pure-text",
            "qwen2.5-7b-instruct": "pure-text",
            "qwen2.5-14b-instruct": "pure-text",
            "qwen2.5-32b-instruct": "pure-text",
            "qwen2.5-72b-instruct": "pure-text",
            "qwen2.5-vl-3b-instruct": "multimodal",
            "qwen2.5-vl-7b-instruct": "multimodal",
            "qwen2.5-vl-32b-instruct": "multimodal",
            "qwen2.5-vl-72b-instruct": "multimodal",
            "qwen3-235b-a22b": "pure-text",
            "qwen3-30b-a3b": "pure-text",
            "qwen3-32b": "pure-text",
            "qwen3-14b": "pure-text",
            "qwen3-8b": "pure-text",
            "qwen3-4b": "pure-text",
            "qwq-plus": "pure-text",
            "qvq-max": "multimodal",
            "llama-4-scout-17b-16e-instruct": "multimodal",
            "llama-4-maverick-17b-128e-instruct": "multimodal",
        },
        "Deepinfra": {
            "meta-llama/Llama-3.2-3B-Instruct": "pure-text",
            "meta-llama/Meta-Llama-3.1-8B-Instruct": "pure-text",
            "meta-llama/Llama-3.3-70B-Instruct": "pure-text",
            "mistralai/Mistral-7B-Instruct-v0.3": "pure-text",
            "mistralai/Mixtral-8x7B-Instruct-v0.1": "pure-text",
            "mistralai/Mistral-Small-24B-Instruct-2501": "pure-text",
            "deepseek-ai/DeepSeek-V3": "pure-text",
            "deepseek-ai/DeepSeek-R1": "pure-text",
            "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B": "pure-text",
            "deepseek-ai/DeepSeek-R1-Distill-Llama-70B": "pure-text",
        }
    }

    # initialize arguments
    args = initialize_args()
    model_name, setting, mode = args.model_name, args.setting, args.mode

    # select a correct inference model based on input args
    if args.mock:
        mock = apilog.MockProvider(
            model=model_name,
            fail_on=[x for x in args.mock_fail.split(',') if x],
            rate_limit_on=[x for x in args.mock_rate_limit.split(',') if x])

        class _MockInference:
            mode = args.mode

            def get_api_response(self, q_id, question, texts, images):
                r = mock.generate(q_id, question, texts, images)
                if r["ok"]:
                    return {"q_id": q_id, "model": model_name,
                            "in_tok": r["usage"]["input_tokens"],
                            "out_tok": r["usage"]["output_tokens"],
                            "total_tok": (r["usage"]["input_tokens"]
                                          + r["usage"]["output_tokens"]),
                            "response": r["parsed"], "_raw": r}
                return {"q_id": q_id, "model": model_name, "in_tok": 0,
                        "out_tok": 0, "total_tok": 0, "response": "",
                        "error": r["error"], "_raw": r}

        inference = _MockInference()
        print("[mock] offline fake provider -- no network, no spend")
    else:
        inference = initialize_infer(api_keys, model_name, mode, args.enable_thinking)

    # record model name and inference mode for output file creation.
    if "/" in model_name:
        model_name = model_name.split("/")[1].replace("Meta-", "")
    infer_mode = inference.mode

    os.makedirs(args.response_dir, exist_ok=True)
    out_path = os.path.join(
        args.response_dir,
        f"{model_name}_{infer_mode}_quotes{setting}_response.jsonl")
    fail_path = os.path.join(
        args.response_dir, f"{model_name}_{infer_mode}_fail_quotes{setting}.txt")
    if args.mock and os.path.abspath(args.response_dir) == os.path.abspath("response"):
        print("[warn] a MOCK run is writing into the real response/ directory. "
              "Pass --response-dir artifacts/test-runs/<id> to keep fake "
              "responses out of the record.")

    out_jsonl, fail_list = [], []
    consecutive_failures = 0
    dataset_path = os.path.join(args.dataset_dir, f"evaluation_{setting}.jsonl")
    data_json = load_jsonl(dataset_path)

    # ---- structured API log ------------------------------------------------
    provider = "mock" if args.mock else provider_of(model_name)
    prompt_path = PROMPT_FOR_MODE.get(infer_mode, PROMPT_FOR_MODE["pure-text"])
    prompt_hash = apilog.file_hash(prompt_path)
    log_tag = args.api_log_tag or f"{model_name}_{infer_mode}_{setting}"
    log = apilog.APILog(log_tag, experiment_id=args.experiment_id)

    # request_hash keys on the quotes actually shown, not just the q_id: the
    # same question under a different retrieval configuration is a DIFFERENT
    # request, and resuming across configurations would silently reuse an
    # answer produced from other evidence.
    hashes, payloads = {}, {}
    for item in data_json:
        payload = {"question": item.get("question"),
                   "text_quotes": item.get("text_quotes"),
                   "img_quotes": [{k: v for k, v in q.items() if k != "img_path"}
                                  for q in item.get("img_quotes", [])]}
        h = apilog.request_hash(provider=provider, model=model_name,
                                mode=infer_mode, prompt_hash=prompt_hash,
                                question_uid=item["q_id"], payload=payload)
        hashes[item["q_id"]] = h
        payloads[item["q_id"]] = payload

    # The plan is the document a person reads before authorising spend, so it
    # has to predict what the run will actually do. Two independent records can
    # make a request unnecessary, and they do not overlap: the API log (written
    # only since the logging layer landed) and the response file (the sole
    # record of anything run before that). Counting the log alone reported
    # "600 requests to issue" for a setting that already had 30 responses on
    # disk and would have skipped them. Over-stating spend is the safer
    # direction to be wrong in, but a plan that does not match the run cannot
    # authorise it in either direction.
    done_from_log = {q for q, h in hashes.items() if log.done(h)}
    done_from_file = set()
    if args.resume and os.path.exists(out_path):
        done_from_file = {r["q_id"] for r in load_jsonl(out_path)
                          if r.get("response")}
    already_set = (done_from_log | done_from_file) if args.resume else set()
    already = len(already_set)
    todo_n = len(data_json) - (0 if args.force else already)
    plan = {
        "experiment_id": args.experiment_id, "provider": provider,
        "model": model_name, "mode": infer_mode, "setting": setting,
        "dataset": dataset_path.replace("\\", "/"),
        "response_dir": args.response_dir.replace("\\", "/"),
        "prompt_template": prompt_path, "prompt_hash": prompt_hash,
        "questions_total": len(data_json),
        "already_succeeded": already,
        "already_in_api_log": len(done_from_log),
        "already_in_response_file": len(done_from_file),
        "requests_to_issue": min(todo_n, args.max_requests) if args.max_requests
                             else todo_n,
        "requests_remaining_after_this_segment": max(
            0, todo_n - args.max_requests) if args.max_requests else 0,
        "max_requests": args.max_requests or None,
        "force_rerun": bool(args.force), "mock": bool(args.mock),
        "rpm_throttle": args.rpm,
        "estimated_minutes_at_rpm": (
            round(min(todo_n, args.max_requests or todo_n) / args.rpm, 1)
            if args.rpm else None),
        "stop_after_consecutive_failures": args.stop_after_failures,
        "log": rel(log.path),
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    plan_path = log.write_plan(plan)
    print("=" * 78)
    print("API CALL PLAN (written before any request is issued)")
    print("=" * 78)
    for key in ("provider", "model", "mode", "setting", "questions_total",
                "already_succeeded", "already_in_api_log",
                "already_in_response_file", "requests_to_issue",
                "requests_remaining_after_this_segment", "force_rerun",
                "mock", "estimated_minutes_at_rpm"):
        print(f"  {key:<40}{plan[key]}")
    print(f"  {'plan file':<40}{rel(plan_path)}")
    print(f"  {'request log':<40}{rel(log.path)}")
    print("=" * 78)
    if args.plan_only:
        print("--plan-only: nothing was called.")
        raise SystemExit(0)

    # Resume: keep questions that already produced a non-empty response so an
    # interrupted run (or a rate-limit failure) does not re-pay for them.
    done = set()
    if args.resume and os.path.exists(out_path):
        out_jsonl = load_jsonl(out_path)
        done = {r["q_id"] for r in out_jsonl if r.get("response")}
        out_jsonl = [r for r in out_jsonl if r["q_id"] in done]
        print(f"[resume] {len(done)}/{len(data_json)} already complete in {out_path}; "
              f"re-running the remaining {len(data_json) - len(done)}")
    if args.resume and not args.force:
        # the API log is authoritative: it survives a deleted response file
        if done_from_log - done:
            print(f"[resume] API log has {len(done_from_log - done)} additional "
                  f"completed request(s) not in the response file")
        done |= done_from_log
    # The plan promised a number; the run must honour it or say why not.
    if args.resume and not args.force and len(done) != already:
        print(f"[resume] WARNING: plan said {already} already done, resume found "
              f"{len(done)}. The plan and the run disagree -- investigate before "
              f"trusting either.")

    # start to run inference
    issued = 0
    hit_bound = False
    for i, item in enumerate(tqdm(data_json)):
        q_id = item["q_id"]
        if q_id in done and not args.force:
            continue
        if args.max_requests and issued >= args.max_requests:
            hit_bound = True
            break
        issued += 1
        question = item["question"]
        call_started = time.time()
        text_quotes, image_quotes = item["text_quotes"], item["img_quotes"]
        rec = apilog.make_record(
            request_hash_=hashes[q_id], provider=provider, model=model_name,
            mode=infer_mode, question_uid=q_id, doc_name=item.get("doc_name"),
            experiment_id=args.experiment_id, run_id=os.environ.get("MMDOCRAG_RUN_ID", ""),
            prompt_path=prompt_path, prompt_hash=prompt_hash,
            params={"setting": setting, "mode": infer_mode,
                    "enable_thinking": args.enable_thinking,
                    "n_text_quotes": len(text_quotes or []),
                    "n_img_quotes": len(image_quotes or []),
                    "payload_hash": apilog.sha(json.dumps(
                        payloads[q_id], sort_keys=True, ensure_ascii=False), 24)})
        # input question, text and image quotes for multimodal generation
        result = inference.get_api_response(q_id, question, text_quotes, image_quotes)
        raw = result.pop("_raw", None)
        ok = bool(result.get("response"))
        log.append(apilog.finish_record(
            rec, status="success" if ok else "error",
            latency_sec=time.time() - call_started,
            raw_response=(raw or {}).get("raw") if raw else None,
            parsed_response=result.get("response") or None,
            usage={"input_tokens": result.get("in_tok"),
                   "output_tokens": result.get("out_tok"),
                   "total_tokens": result.get("total_tok")} if ok else None,
            provider_request_id=(raw or {}).get("provider_request_id") if raw else None,
            error=result.get("error"),
            http_status=(raw or {}).get("http_status") if raw else None,
            rate_limit=(raw or {}).get("rate_limit") if raw else None))
        log.save_index()
        out_jsonl.append(result)
        if result["response"] == "":
            print(f"@@@@@@ qid: {q_id} processed failed! @@@@@")
            if "error" in result:
                err_msg = result["error"]
                print(f"@@@@ the error message is: {err_msg} @@@@@@")
            fail_list.append(str(q_id))
            consecutive_failures += 1
            if (args.stop_after_failures
                    and consecutive_failures >= args.stop_after_failures):
                print(f"[stop] {consecutive_failures} consecutive failures - "
                      f"most likely the daily quota. {len(out_jsonl)} of "
                      f"{len(data_json)} done; re-run the same command to resume.")
                break
        else:
            consecutive_failures = 0

        if len(out_jsonl) > 0:
            save_jsonl(out_jsonl, out_path)

        if len(fail_list) > 0:
            with open(fail_path, "w", encoding="utf-8") as fail_out:
                fail_out.write("\n".join(fail_list))

        if args.rpm and args.rpm > 0:
            # measured from the START of the previous call, so slow responses
            # already count toward the interval instead of adding to it
            wait = (60.0 / args.rpm) - (time.time() - call_started)
            if wait > 0:
                time.sleep(wait)

    new_count = len(out_jsonl) - len(done)
    if hit_bound:
        remaining = len(data_json) - len(done) - issued
        print(f"[bound] --max-requests {args.max_requests} reached; stopped "
              f"cleanly after {issued} request(s). {remaining} still to do -- "
              f"re-run the same command to continue (nothing is re-paid).")
    print(f"[done] {len(out_jsonl)}/{len(data_json)} response(s) in {out_path} "
          f"({new_count} added this run)"
          + (f"; {len(fail_list)} failed this run" if fail_list else ""))
    log.save_index()
    st = log.stats()
    print(f"[api-log] {st['records']} request(s) recorded "
          f"({st['success']} success, {st['error']} error); "
          f"tokens in {st['input_tokens']}, out {st['output_tokens']}")
    print(f"[api-log] {rel(log.path)}")
    print("[api-log] token counts are measured; any USD figure derived from them "
          "is an UNVERIFIED estimate.")
