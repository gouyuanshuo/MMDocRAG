"""Aggregate a run into summary.{json,csv,md,html} and metrics.jsonl.

The hard rule here: **every number in a summary comes from this run's
metrics.json files.** The registry's prose supplies the framing -- what the
experiment asked, how it was done, what the metric means, what the limits are --
but never the figures. Copying the registry's historical numbers into a fresh
summary would produce a document that looks like a result and is actually a
memory, and it would keep looking correct after the code stopped reproducing it.

Experiments that ran but are not yet instrumented show up honestly as
`stdout-only`, with a pointer to their log, rather than borrowing numbers from
the registry to fill the gap.
"""

import csv
import html
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from expkit import paths                            # noqa: E402
from expkit.results import atomic_json, atomic_write  # noqa: E402

STATE_LABEL = {
    "ok": "已运行", "error": "失败", "skipped": "跳过", "manual": "人工核对",
    "blocked": "受阻", "dry-run": "仅打印", "stdout-only": "已运行（仅日志）",
}


def collect(run_id, registry_entries, artifact_root=None):
    """Walk a run directory and pull together status + metrics for each experiment."""
    rdir = paths.run_dir(run_id, artifact_root)
    exp_root = os.path.join(rdir, "experiments")
    out = []
    if not os.path.isdir(exp_root):
        return out
    for exp_id in sorted(os.listdir(exp_root),
                         key=lambda s: (len(s), s)):     # E2 before E10
        spath = os.path.join(exp_root, exp_id, "status.json")
        if not os.path.exists(spath):
            continue
        with open(spath, encoding="utf-8") as fh:
            status = json.load(fh)
        metrics = []
        for rel_p in status.get("metrics_files", []):
            full = os.path.join(paths.REPO_ROOT, rel_p)
            if os.path.exists(full):
                with open(full, encoding="utf-8") as fh:
                    metrics.append(json.load(fh))
        reg = registry_entries.get(exp_id, {})
        state = status.get("status", "unknown")
        if state == "ok" and not metrics:
            state = "stdout-only"
        out.append({
            "id": exp_id,
            "title": status.get("title") or reg.get("title", ""),
            "state": state,
            "reason": status.get("reason", ""),
            "elapsed_sec": status.get("elapsed_sec", 0.0),
            "n_commands": len(status.get("commands", [])),
            "logs": [c.get("stdout_log") for c in status.get("commands", [])
                     if c.get("stdout_log")],
            "metrics_files": status.get("metrics_files", []),
            "metrics": metrics,
            "asks": reg.get("asks", ""),
            "how": reg.get("how", ""),
            "metric_meaning": reg.get("metric_meaning", ""),
            "limits": reg.get("limits", ""),
            "primary_metric": reg.get("primary_metric", ""),
            "sample_unit": reg.get("sample_unit", ""),
            "lifecycle": reg.get("lifecycle", ""),
            "superseded": reg.get("superseded"),
        })
    return out


def flat_metrics(entries):
    rows = []
    for e in entries:
        for block in e["metrics"]:
            cfg = block.get("config", {})
            for m in block.get("metrics", []):
                row = {"experiment": e["id"], "title": e["title"]}
                row.update({k: v for k, v in cfg.items()})
                row.update(m)
                rows.append(row)
    return rows


def _fmt(v, digits=4):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:+.{digits}f}" if abs(v) < 1 else f"{v:.{digits}f}"
    return str(v)


def _ci(m):
    if m.get("ci_low") is None:
        return "—"
    star = " *" if m.get("significant") else ""
    return f"[{m['ci_low']:+.4f}, {m['ci_high']:+.4f}]{star}"


def write_all(run_id, entries, run_meta, artifact_root=None):
    rdir = paths.run_dir(run_id, artifact_root)
    os.makedirs(rdir, exist_ok=True)
    rows = flat_metrics(entries)

    counts = {}
    for e in entries:
        counts[e["state"]] = counts.get(e["state"], 0) + 1

    summary = {
        "run_id": run_id,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "suite": run_meta.get("suite"),
        "offline": run_meta.get("offline"),
        "counts": counts,
        "n_metrics": len(rows),
        "experiments": [{k: v for k, v in e.items() if k != "metrics"}
                        for e in entries],
    }
    atomic_json(os.path.join(rdir, "summary.json"), summary)

    # metrics.jsonl -- one metric per line, the machine-readable spine
    lines = "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n"
                    for r in rows)
    atomic_write(os.path.join(rdir, "metrics.jsonl"), lines)

    # summary.csv
    cols, seen = [], set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                cols.append(k)
    lead = [c for c in ("experiment", "name", "value", "ci_low", "ci_high",
                        "significant", "pool", "k") if c in seen]
    cols = lead + [c for c in cols if c not in lead]
    csv_path = os.path.join(rdir, "summary.csv")
    tmp = csv_path + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols or ["experiment"], extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, csv_path)

    atomic_write(os.path.join(rdir, "summary.md"),
                 render_md(run_id, entries, run_meta, counts))
    atomic_write(os.path.join(rdir, "summary.html"),
                 render_html(run_id, entries, run_meta, counts))
    return {
        "summary_json": paths.rel(os.path.join(rdir, "summary.json")),
        "summary_csv": paths.rel(csv_path),
        "summary_md": paths.rel(os.path.join(rdir, "summary.md")),
        "summary_html": paths.rel(os.path.join(rdir, "summary.html")),
        "metrics_jsonl": paths.rel(os.path.join(rdir, "metrics.jsonl")),
        "n_metrics": len(rows),
    }


def render_md(run_id, entries, run_meta, counts):
    L = [f"# 运行报告 · {run_id}", ""]
    L.append(f"- 套件：`{run_meta.get('suite')}`　离线：{run_meta.get('offline')}"
             f"　允许 API：{run_meta.get('allow_api')}")
    L.append(f"- 生成时间（UTC）：{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}")
    L.append(f"- 代码 commit：`{run_meta.get('git', {}).get('commit')}`"
             f"　工作区脏：{run_meta.get('git', {}).get('dirty')}")
    fp = run_meta.get("source_fingerprint")
    if fp:
        L.append(f"- **source fingerprint：`{fp}`**"
                 f"（{run_meta.get('n_source_files')} 个源文件 + 注册表快照的哈希）"
                 f"　清单：`{run_meta.get('source_manifest')}`")
        if run_meta.get("source_bundle"):
            L.append(f"- **source bundle：`{run_meta['source_bundle']}`**"
                     f"（{run_meta.get('source_bundle_files')} 个文件，"
                     f"{run_meta.get('source_bundle_bytes')} 字节，"
                     f"sha256 `{run_meta.get('source_bundle_sha256')}`）"
                     f"——**这是本次源码的最终快照**")
        if run_meta.get("source_patch"):
            L.append(f"- 工作区补丁：`{run_meta['source_patch']}`"
                     f"（只含 **Git 已跟踪**文件的改动；本仓库多数源码未被跟踪，"
                     f"因此 patch 单独**不能**还原本次运行，须叠加 bundle）")
        rt = run_meta.get("reconstruction_test") or {}
        if rt:
            L.append(f"- 重建测试：**{rt.get('status')}** "
                     f"{rt.get('n_pass', 0)}/{rt.get('n_total', 0)} 个文件哈希逐字节命中"
                     + (f"（隔离目录 `{rt.get('tree')}`）" if rt.get("tree") else "")
                     + (f"　{rt.get('why')}" if rt.get("why") else ""))
        if run_meta.get("reconstruct_command"):
            L.append(f"- 复现源码：`{run_meta['reconstruct_command']}`"
                     f"（git archive → git apply → 解压 bundle → 重算全部哈希）")
    L.append("- 实验状态：" + "，".join(
        f"{STATE_LABEL.get(k, k)} {v}" for k, v in sorted(counts.items())))
    L.append("")
    L.append("> 本报告中的每个数字都取自本次运行落盘的 `metrics.json`，"
             "不复制 `experiments.py` 里的历史文字。"
             "标记为「已运行（仅日志）」的实验尚未接入结构化输出，"
             "其数字请看对应的 `stdout.log`，不要从这里引用。")
    L.append("")

    for e in entries:
        L.append(f"## {e['id']}　{e['title']}")
        L.append("")
        L.append(f"**状态**：{STATE_LABEL.get(e['state'], e['state'])}"
                 + (f"　（{e['reason']}）" if e.get("reason") else "")
                 + f"　耗时 {e['elapsed_sec']:.1f}s")
        if e.get("asks"):
            L.append(f"- **问什么**：{e['asks']}")
        if e.get("how"):
            L.append(f"- **怎么做**：{e['how']}")
        if e.get("metric_meaning"):
            L.append(f"- **指标含义**：{e['metric_meaning']}")
        if e.get("sample_unit"):
            L.append(f"- **统计单位**：{e['sample_unit']}"
                     f"（bootstrap 按此重采样）")
        if not e["metrics"]:
            if e["state"] == "stdout-only":
                L.append(f"- **数字**：本实验尚未接入 metrics.json，"
                         f"见日志 `{(e['logs'] or ['—'])[0]}`")
            L.append("")
            if e.get("limits"):
                L.append(f"- **限制**：{e['limits']}")
            L.append("")
            continue
        for block in e["metrics"]:
            cfg = block.get("config", {})
            tag = "　".join(f"{k}={v}" for k, v in cfg.items()
                            if k in ("pool", "k", "quota", "seed", "bootstrap"))
            L.append("")
            L.append(f"**配置**：{tag or '—'}")
            L.append("")
            L.append("| 指标 | 值 | 95% CI（文档聚类） | 说明 |")
            L.append("|---|---|---|---|")
            for m in block.get("metrics", []):
                note = m.get("comparison") or m.get("desc") or ""
                L.append(f"| {m['name']} | {_fmt(m.get('value'))} | {_ci(m)} | {note} |")
        L.append("")
        if e.get("limits"):
            L.append(f"**限制**：{e['limits']}")
        L.append("")
        L.append(f"<sub>逐题结果与 manifest：`{os.path.dirname(e['metrics_files'][0])}`</sub>"
                 if e["metrics_files"] else "")
        L.append("")
    L.append("---")
    L.append("`*` 表示 95% 置信区间不跨 0。区间下界贴近 0 时不要写「显著」。")
    return "\n".join(L) + "\n"


def render_html(run_id, entries, run_meta, counts):
    esc = html.escape
    parts = ["""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>运行报告 """ + esc(run_id) + """</title><style>
:root{--bg:#fbfaf8;--ink:#1c1b19;--ink2:#5d5a54;--rule:#dcd8d0;--card:#fff;
--ok:#2f6f4e;--err:#a33a2c;--warn:#8a6d1f;--accent:#3b5a7a;}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#161513;
--ink:#eceae6;--ink2:#a5a099;--rule:#33302c;--card:#1e1d1a;--ok:#7fc39b;
--err:#e08b7c;--warn:#d4b45e;--accent:#8fb4d9;}}
:root[data-theme=dark]{--bg:#161513;--ink:#eceae6;--ink2:#a5a099;--rule:#33302c;
--card:#1e1d1a;--ok:#7fc39b;--err:#e08b7c;--warn:#d4b45e;--accent:#8fb4d9;}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.65 -apple-system,"Segoe UI","Noto Sans SC",sans-serif;padding:2rem 1rem}
.wrap{max-width:64rem;margin:0 auto}h1{font-size:1.5rem;margin:0 0 .3rem}
h2{font-size:1.05rem;margin:2rem 0 .5rem;padding-top:1rem;border-top:1px solid var(--rule)}
.meta{color:var(--ink2);font-size:13px;margin-bottom:1rem}
.note{background:var(--card);border:1px solid var(--rule);border-left:3px solid var(--accent);
padding:.7rem .9rem;border-radius:4px;font-size:13.5px;color:var(--ink2);margin:1rem 0}
.pill{display:inline-block;font-size:11px;padding:2px 8px;border-radius:99px;
border:1px solid var(--rule);margin-right:.4rem}
.ok{color:var(--ok)}.err{color:var(--err)}.warn{color:var(--warn)}
dl{display:grid;grid-template-columns:max-content 1fr;gap:.2rem .8rem;margin:.6rem 0;font-size:14px}
dt{color:var(--ink2)}dd{margin:0}
.scroll{overflow-x:auto;margin:.8rem 0}
table{border-collapse:collapse;width:100%;font-size:13.5px;min-width:34rem}
th,td{text-align:left;padding:.4rem .6rem;border-bottom:1px solid var(--rule)}
th{color:var(--ink2);font-weight:600;font-size:12px;letter-spacing:.03em}
td.num{font-variant-numeric:tabular-nums;text-align:right}
code{font-family:ui-monospace,Consolas,monospace;font-size:12.5px;
background:var(--card);border:1px solid var(--rule);border-radius:3px;padding:1px 5px}
.limits{font-size:13px;color:var(--ink2);border-left:2px solid var(--rule);
padding-left:.8rem;margin:.8rem 0}
footer{margin-top:2.5rem;padding-top:1rem;border-top:1px solid var(--rule);
color:var(--ink2);font-size:12.5px}
</style></head><body><div class="wrap">"""]
    g = run_meta.get("git", {})
    parts.append(f"<h1>运行报告 · {esc(run_id)}</h1>")
    parts.append(f'<p class="meta">套件 <code>{esc(str(run_meta.get("suite")))}</code>'
                 f'　离线 {run_meta.get("offline")}　允许 API {run_meta.get("allow_api")}'
                 f'　commit <code>{esc(str(g.get("commit"))[:12])}</code>'
                 f'　工作区脏 {g.get("dirty")}</p>')
    fp = run_meta.get("source_fingerprint")
    if fp:
        parts.append(
            f'<p class="meta">source fingerprint <code>{esc(fp)}</code>　'
            f'{run_meta.get("n_source_files")} 个源文件 + 注册表快照　'
            f'清单 <code>{esc(str(run_meta.get("source_manifest")))}</code>'
            + (f'　补丁 <code>{esc(str(run_meta.get("source_patch")))}</code>'
               if run_meta.get("source_patch") else "") + '</p>')
    if run_meta.get("source_bundle"):
        rt = run_meta.get("reconstruction_test") or {}
        ok = rt.get("status") == "pass"
        parts.append(
            f'<p class="meta">source bundle '
            f'<code>{esc(str(run_meta.get("source_bundle")))}</code>　'
            f'{run_meta.get("source_bundle_files")} 个文件 / '
            f'{run_meta.get("source_bundle_bytes")} B　'
            f'sha256 <code>{esc(str(run_meta.get("source_bundle_sha256")))}</code></p>')
        parts.append(
            f'<div class="note">重建测试 <b>{esc(str(rt.get("status")))}</b>：'
            f'{rt.get("n_pass", 0)}/{rt.get("n_total", 0)} 个源文件在隔离目录 '
            f'<code>{esc(str(rt.get("tree")))}</code> 中逐字节还原'
            f'{"" if ok else "——<b>未通过</b>"}。协议是 '
            f'<code>git archive &lt;commit&gt;</code> → '
            f'<code>git apply source.patch</code> → 解压 '
            f'<code>source_bundle.zip</code> → 重算 SHA-256。'
            f'source.patch 只覆盖 Git 已跟踪的文件，'
            f'<b>单独不足以还原本次运行</b>；bundle 才是最终源码快照。'
            f'一条命令：<code>'
            f'{esc(str(run_meta.get("reconstruct_command")))}</code></div>')
    parts.append('<p>' + "".join(
        f'<span class="pill">{esc(STATE_LABEL.get(k, k))} {v}</span>'
        for k, v in sorted(counts.items())) + '</p>')
    parts.append('<div class="note">本报告中的每个数字都取自本次运行落盘的 '
                 '<code>metrics.json</code>，不复制 <code>experiments.py</code> '
                 '里的历史文字。标记为「已运行（仅日志）」的实验尚未接入结构化输出，'
                 '其数字请看对应的 <code>stdout.log</code>，不要从这里引用。</div>')

    for e in entries:
        cls = {"ok": "ok", "error": "err"}.get(e["state"], "warn")
        parts.append(f'<h2>{esc(e["id"])}　{esc(e["title"])}</h2>')
        parts.append(f'<p class="meta"><span class="{cls}">'
                     f'{esc(STATE_LABEL.get(e["state"], e["state"]))}</span>'
                     + (f'　{esc(e["reason"])}' if e.get("reason") else "")
                     + f'　耗时 {e["elapsed_sec"]:.1f}s</p>')
        dl = []
        for label, key in (("问什么", "asks"), ("怎么做", "how"),
                           ("指标含义", "metric_meaning"), ("统计单位", "sample_unit")):
            if e.get(key):
                dl.append(f"<dt>{label}</dt><dd>{esc(str(e[key]))}</dd>")
        if dl:
            parts.append("<dl>" + "".join(dl) + "</dl>")

        if not e["metrics"]:
            if e["state"] == "stdout-only" and e["logs"]:
                parts.append(f'<p class="meta">尚未接入 metrics.json，'
                             f'见日志 <code>{esc(e["logs"][0])}</code></p>')
        for block in e["metrics"]:
            cfg = block.get("config", {})
            tag = "　".join(f"{k}={v}" for k, v in cfg.items()
                            if k in ("pool", "k", "quota", "seed", "bootstrap"))
            parts.append(f'<p class="meta">配置：{esc(tag) or "—"}</p>')
            parts.append('<div class="scroll"><table><thead><tr>'
                         '<th>指标</th><th>值</th><th>95% CI（文档聚类）</th>'
                         '<th>说明</th></tr></thead><tbody>')
            for m in block.get("metrics", []):
                note = m.get("comparison") or m.get("desc") or ""
                parts.append(f'<tr><td>{esc(m["name"])}</td>'
                             f'<td class="num">{esc(_fmt(m.get("value")))}</td>'
                             f'<td class="num">{esc(_ci(m))}</td>'
                             f'<td>{esc(str(note))}</td></tr>')
            parts.append("</tbody></table></div>")
        if e.get("limits"):
            parts.append(f'<p class="limits"><b>限制</b>：{esc(e["limits"])}</p>')
        if e["metrics_files"]:
            parts.append(f'<p class="meta">逐题结果与 manifest：'
                         f'<code>{esc(os.path.dirname(e["metrics_files"][0]))}</code></p>')
    parts.append('<footer><code>*</code> 表示 95% 置信区间不跨 0。'
                 '区间下界贴近 0 时不要写「显著」。多重比较未作校正时应一并说明。'
                 '</footer></div></body></html>')
    return "".join(parts)
