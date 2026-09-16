"""Build the Chinese project guide from Markdown and the identified saved run.

This is a document build, not an experiment run. No API calls or model loading.
Usage: python -X utf8 docs/build_project_guide.py
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import markdown
from bs4 import BeautifulSoup

DOCS = Path(__file__).resolve().parent
ROOT = DOCS.parent
RUN = ROOT / "artifacts/runs/20260905T073315Z_cached"
ASSETS = DOCS / "project-guide-assets"


def svg_start(width: int, height: int, title: str, desc: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">{html.escape(title)}</title><desc id="desc">{html.escape(desc)}</desc>
<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#47677a"/></marker></defs>
<style>text{{font-family:'Microsoft YaHei','PingFang SC',sans-serif;fill:#183444}} .label{{font-size:21px;font-weight:700}} .body{{font-size:17px}} .small{{font-size:16px;fill:#4a626d}} .edge{{fill:none;stroke:#47677a;stroke-width:2;marker-end:url(#arrow)}}</style>
<rect width="{width}" height="{height}" fill="#ffffff"/>
'''


def text(x, y, value, cls="body", anchor="middle"):
    return f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}">{html.escape(value)}</text>'


def node(x, y, w, title, lines, h=116, fill="#eef5f7"):
    out = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{fill}" stroke="#b9cdd5"/>'
    out += text(x+w/2, y+31, title, "label")
    for i, line in enumerate(lines):
        out += text(x+w/2, y+59+i*25, line)
    return out


def edge(d):
    return f'<path d="{d}" class="edge"/>'


def diagrams():
    ASSETS.mkdir(exist_ok=True)
    out = {}
    s = svg_start(960, 400, "从文档到评价", "离线解析和表示建立证据池。在线根据问题检索、选候选、生成答案，再分别评价检索、引用、正确性、忠实度和成本。")
    s += text(25, 30, "离线准备", "label", "start")
    s += node(25, 50, 230, "PDF 与官方材料", ["文字层与 OCR", "图片与已有描述"])
    s += node(330, 50, 255, "统一证据身份", ["文档 / 页面 / layout", "gold 映射与覆盖检查"])
    s += node(660, 50, 275, "索引与候选池", ["文字向量与词频", "图片描述 / 图片像素"])
    s += edge("M255 108 H320") + edge("M585 108 H650")
    s += text(25, 210, "在线查询及独立终点", "label", "start")
    for x, title, lines in [(25,"问题",["已知目标文档", "当前实验范围"]), (267,"检索和路由",["选择动作与配额", "返回 top-k 候选"]), (509,"生成与引用",["读候选并作答", "输出引用编号"]), (751,"分层评价",["召回 / 引用 / 事实", "忠实度 / 时间 / 用量"])]:
        s += node(x, 232, 184, title, lines, fill="#f6f8fa")
    s += edge("M209 290 H257") + edge("M451 290 H499") + edge("M693 290 H741")
    s += text(480, 383, "找回证据、引用正确、事实正确与运行更快，需要分别提供证据。", "small")
    out["pipeline"] = s + "</svg>"

    s = svg_start(960, 330, "三个候选池的范围", "canonical 和 selfbuilt 共享问题、文档与图片侧。full image pool 补齐像素候选，但未补齐图片描述，因此不能不对称地比较方法。")
    s += node(20, 25, 290, "canonical", ["官方候选并集", "证据身份与描述较完整", "池受到问题集合筛选", "适合固定池方法比较"], h=185)
    s += node(335, 25, 290, "selfbuilt", ["重新构造文字 chunk", "92,752 块 / 220 篇文档", "图片侧沿用已有材料", "检查文字池敏感性"], h=185)
    s += node(650, 25, 290, "full image pool", ["磁盘全图片供 ColQwen", "220 / 220 文档已索引", "额外图片描述尚不完整", "检查像素检索池效应"], h=185)
    s += text(320, 254, "前两池共享样本，不是独立复制", "label")
    s += text(480, 295, "跨方法比较要控制同一个池；扩池造成的变化需要同题配对测量。", "small")
    out["pools"] = s + "</svg>"

    s = svg_start(960, 510, "E39 所准备的 GPU 级联", "先运行 dense 文字和 BM25 图片描述。router 根据实际首轮信号决定保留或升级为 RRF 文字和 ColQwen。600题中118题升级。尚未生成答案。")
    s += node(255, 20, 450, "所有题先执行 cheap", ["dense 文字 + BM25 图片描述", "2 CPU pass / 0 GPU pass"], h=104)
    s += edge("M480 124 V156")
    s += node(255, 164, 450, "router 预测升级收益", ["只看当时可用的特征与实际首轮结果"], h=86)
    s += edge("M380 250 V277 H237 V300") + edge("M580 250 V277 H723 V300")
    s += node(35, 310, 404, "保留 cheap", ["482 / 600 题", "总计 2 CPU / 0 GPU pass"], fill="#eef7f2")
    s += node(521, 310, 404, "升级 expensive", ["118 / 600 题", "总计 3 CPU / 1 GPU pass"], fill="#fff5e5")
    s += text(480, 463, "升级结果：RRF 文字 + ColQwen 像素检索；候选配额均为 5 / 5。", "small")
    s += text(480, 493, "这些是保存决策与成本计数。E39 生成质量和实际端到端时间尚未测量。", "small")
    out["cascade"] = s + "</svg>"

    s = svg_start(960, 570, "研究路线图", "测量基础、静态配置、预算路由已有研究结果；下一步先补已有回答盲评，再冻结E39生成及在线效率，最后做新文档确认。")
    entries = [
        ("01 测量基础", ["E1–E7 与 E28、E31–E33", "身份、分母、可复算"], "#eef7f2"),
        ("02 静态配置", ["E27、E29、E30、E40、E41", "召回与引用 F1 的证据"], "#eef7f2"),
        ("03 预算路由", ["E35–E38", "GPU 部分信号，仍属探索"], "#eef5f7"),
        ("04 补答案盲评", ["优先复用 E29 保存回答", "正确性与忠实度"], "#fff5e5"),
        ("05 冻结并执行 E39", ["生成引用非劣与在线计时", "模型、边界、预算先明确"], "#fff5e5"),
        ("06 新文档确认", ["冻结完整方法与评价规则", "检验外部泛化"], "#f1f0f8"),
    ]
    for i, (title, lines, fill) in enumerate(entries):
        row, col = divmod(i, 3)
        s += node(20+col*320, 55+row*275, 280, title, lines, h=130, fill=fill)
    s += text(20, 30, "已完成或已有部分结果", "label", "start")
    s += text(20, 305, "建议下一步顺序", "label", "start")
    s += edge("M300 120 H332") + edge("M620 120 H652")
    s += edge("M800 185 V238 H160 V315")
    s += edge("M300 395 H332") + edge("M620 395 H652")
    s += text(480, 520, "扩展复杂方法之前，先补上研究主张缺少的终点与效率测量。", "small")
    s += text(480, 550, "未支持原假设的实验仍是研究结果；未来工作没有被提前记为完成。", "small")
    out["roadmap"] = s + "</svg>"
    for key, value in out.items():
        (ASSETS / f"{key}.svg").write_text(value, encoding="utf-8")
    return out


def e40_table():
    lines = ["| 池 | k | 基线 Recall | OOF Recall | 绝对差百分点 | 95% CI 百分点 |",
             "|---|---|---|---|---|---|"]
    for p in sorted((RUN / "experiments/E40").glob("cmd*/metrics.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        c = d["config"]
        m = {x["name"]: x for x in d["metrics"]}
        delta = m["delta: nested-CV - paper-style (E)"]
        assert c["n_questions"] == 2000 and c["n_documents"] == 220
        lines.append(f"| {c['pool']} | {c['k']} | {m['recall_paper_style_E']['value']:.4f} | {m['recall_nested_cv_oof']['value']:.4f} | +{delta['value']*100:.2f} | [{delta['ci_low']*100:.2f}, {delta['ci_high']*100:.2f}] |")
    assert len(lines) == 6
    return "\n".join(lines)


CSS = '''
:root{--ink:#182f3c;--muted:#536873;--line:#d7e1e5;--accent:#136c77;--paper:#fff;--bg:#f4f7f9}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:24px}
body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.95 'Microsoft YaHei','PingFang SC',sans-serif}
a{color:#126a80;text-underline-offset:3px;overflow-wrap:anywhere}a:hover{color:#004557}a:focus-visible,button:focus-visible,input:focus-visible{outline:3px solid #d98620;outline-offset:4px}
.sidebar{position:fixed;inset:0 auto 0 0;width:270px;overflow:auto;padding:28px 22px;background:#edf3f6;border-right:1px solid var(--line);font-size:13px;line-height:1.75}
.brand{font-weight:750;font-size:21px;color:#183444;margin-bottom:6px}.sidebar .meta{color:var(--muted);font-size:12px;margin-bottom:24px}.toc a{display:block;padding:7px 0;color:#345564;text-decoration:none}.toc a.active{font-weight:700;color:#075d6b}.sidebar hr{border:0;border-top:1px solid var(--line);margin:20px 0}
.layout{margin-left:270px;padding:44px 5vw 80px}.document{max-width:1040px;margin:auto;background:white;padding:55px 65px;box-shadow:0 3px 22px #14374c08}
h1,h2,h3{color:#112e3b;line-height:1.5;letter-spacing:.01em}h1{font-size:35px;margin:0 0 18px}h2{font-size:27px;margin:64px 0 22px;padding-top:10px}h3{font-size:21px;margin:35px 0 15px}p{margin:16px 0}strong{font-weight:700;color:#173b4b}ul,ol{padding-left:1.65em}li{padding:4px 0}code{font:0.89em/1.7 Consolas,monospace;background:#f0f4f6;border-radius:3px;padding:2px 5px;overflow-wrap:anywhere}pre{background:#edf3f6;padding:20px;overflow:auto;border:1px solid var(--line);border-radius:6px}pre code{padding:0;background:none}
.table-scroll{overflow-x:auto;margin:26px 0}table{width:100%;border-collapse:collapse;font-size:14px;line-height:1.8}th,td{border:1px solid #cddae1;padding:11px 13px;vertical-align:middle;text-align:left;min-width:75px}th{background:#e6f0f4;color:#193b4d;font-weight:700}tr:nth-child(even) td{background:#f9fbfc}th:first-child,td:first-child{font-weight:600}figure{margin:28px 0}figure svg{display:block;width:100%;height:auto;border:1px solid #d7e2e6;border-radius:6px}figcaption{font-size:13px;color:var(--muted);margin-top:9px}
.chapter-links{font-size:13px;margin:8px 0 18px;color:var(--muted)}.exp-record{padding:1px 0 22px;border-bottom:1px solid var(--line)}.exp-record h3{margin-top:30px}.status{font-size:12px;font-weight:500;color:#51666f;margin-left:12px}.exp-controls{margin:26px 0}.exp-controls label{display:block;font-weight:600;font-size:15px}.exp-controls input{width:100%;padding:13px 15px;border:1px solid #b4c8d1;border-radius:5px;font:inherit;background:#fbfdfe}.exp-count{font-size:13px;color:var(--muted)}.jump-grid{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0}.jump-grid a{font-size:13px;min-width:44px;padding:3px 8px;text-align:center;background:#edf4f6;text-decoration:none;border-radius:3px}.footer{margin-top:55px;padding-top:18px;border-top:1px solid var(--line);font-size:13px;color:var(--muted)}button{font:inherit;font-size:13px;border:1px solid #b6cbd4;background:white;padding:5px 12px;border-radius:4px;color:#204557;cursor:pointer}.skip{position:absolute;left:-9999px}.skip:focus{left:20px;top:10px;background:white;padding:10px;z-index:10}[hidden]{display:none!important}
@media(max-width:1100px){.sidebar{width:220px;padding:22px 17px}.layout{margin-left:220px;padding:25px}.document{padding:36px}}
@media(max-width:780px){.sidebar{position:relative;width:100%;max-height:340px}.sidebar .toc{columns:2;column-gap:24px}.layout{margin:0;padding:12px}.document{padding:24px 19px}h1{font-size:28px}h2{font-size:24px}body{font-size:16px}.table-scroll{margin-left:-4px;margin-right:-4px}th,td{min-width:100px}.sidebar hr{margin:8px 0}}
@media print{body{background:white;font-size:10.5pt;line-height:1.7}.sidebar,.exp-controls,.jump-grid,.chapter-links,.skip{display:none}.layout{margin:0;padding:0}.document{max-width:none;padding:0;box-shadow:none}h1{font-size:24pt}h2{font-size:17pt;margin:28px 0 15px;break-after:avoid}h3{font-size:13pt;break-after:avoid}table{font-size:9pt}.table-scroll{overflow:visible}thead{display:table-header-group}tr,figure{break-inside:avoid}a{color:inherit;text-decoration:none}.exp-record[hidden]{display:block!important}svg{max-height:19cm}pre{white-space:pre-wrap}@page{size:A4;margin:18mm}}
'''


def main():
    figures = diagrams()
    source = DOCS / "PROJECT_GUIDE.md"
    md = source.read_text(encoding="utf-8")
    table = e40_table()
    if "<!-- table:e40 -->" in md:
        md = md.replace("<!-- table:e40 -->", "<!-- e40:start -->\n"+table+"\n<!-- e40:end -->")
    else:
        md = re.sub(r"<!-- e40:start -->.*?<!-- e40:end -->", "<!-- e40:start -->\n"+table+"\n<!-- e40:end -->", md, flags=re.S)
    for key in figures:
        desc = {"pipeline":"图 1 文档处理与评价链", "pools":"图 2 三种候选池的范围", "cascade":"图 3 E39 已准备的 GPU 级联", "roadmap":"图 4 研究进展与下一步路线"}[key]
        md = md.replace(f"<!-- diagram:{key} -->", f"![{desc}](project-guide-assets/{key}.svg)")
    source.write_text(md, encoding="utf-8")
    soup = BeautifulSoup(markdown.markdown(md, extensions=["tables", "fenced_code", "sane_lists"]), "html.parser")
    for img in list(soup.select("img")):
        key = Path(img["src"]).stem
        if key in figures:
            fig = soup.new_tag("figure")
            graphic = BeautifulSoup(figures[key], "html.parser").find("svg")
            # SVG IDs share one HTML document. Give each diagram unique labels and marker.
            for el in graphic.select("[id]"):
                el["id"] = key+"-"+el["id"]
            graphic["aria-labelledby"] = f"{key}-title {key}-desc"
            graphic.find("style").string = graphic.find("style").string.replace("url(#arrow)", f"url(#{key}-arrow)")
            fig.append(graphic)
            cap = soup.new_tag("figcaption")
            cap.string = img["alt"]
            fig.append(cap)
            img.parent.replace_with(fig)
    toc = []
    for i, heading in enumerate(soup.select("h2"), 1):
        heading["id"] = f"chapter-{i}"
        toc.append(f'<a href="#chapter-{i}">{html.escape(heading.get_text())}</a>')
    import sys
    sys.path.insert(0, str(ROOT))
    import experiments
    states = {"pass":"通过", "fix":"修复", "correct":"更正", "neg":"负结果", "pos":"正向", "pending":"待完成"}
    records = []
    for h in list(soup.select("h3")):
        match = re.match(r"E(\d+)\s", h.get_text())
        if not match:
            continue
        eid = "E"+match[1]
        wrapper = soup.new_tag("section", attrs={"class":"exp-record", "id":"guide-"+eid})
        h.insert_before(wrapper)
        wrapper.append(h.extract())
        while wrapper.next_sibling and getattr(wrapper.next_sibling, "name", None) not in ("h2", "h3"):
            wrapper.append(wrapper.next_sibling.extract())
        badge = soup.new_tag("span", attrs={"class":"status"})
        badge.string = states[experiments.BY_ID[eid]["status"]]
        h.append(badge)
        p = soup.new_tag("p", attrs={"class":"chapter-links"})
        a = soup.new_tag("a", href=f"lab-notebook.html#exp-{eid}")
        a.string = "查看实验原始记录与更正"
        p.append(a)
        wrapper.append(p)
        records.append(eid)
    assert sorted(records, key=lambda e:int(e[1:])) == [f"E{i}" for i in range(1,42)]
    intro = soup.find("h2", id="chapter-13")
    controls = BeautifulSoup('<div class="exp-controls"><label for="exp-search">查找实验编号或关键词</label><input id="exp-search" type="search" placeholder="例如 E39、OCR、配额、为什么做"/><div class="exp-count" aria-live="polite">显示全部 41 项实验</div></div>', "html.parser")
    intro.insert_after(controls)
    grid = soup.new_tag("div", attrs={"class":"jump-grid"})
    for eid in records:
        a=soup.new_tag("a", href="#guide-"+eid); a.string=eid; grid.append(a)
    intro.insert_after(grid)
    for table_el in soup.find_all("table"):
        wrapper=soup.new_tag("div", attrs={"class":"table-scroll", "tabindex":"0", "role":"region", "aria-label":"可横向滚动的对照表"})
        table_el.wrap(wrapper)
    body = str(soup)
    js = '''const input=document.querySelector('#exp-search');const records=[...document.querySelectorAll('.exp-record')];
input.addEventListener('input',()=>{const q=input.value.trim().toLocaleLowerCase();let n=0;records.forEach(el=>{const match=el.innerText.toLocaleLowerCase().includes(q);el.hidden=!match;if(match)n++;});document.querySelector('.exp-count').textContent=`显示 ${n} / 41 项实验`;});
function revealHash(){const el=document.getElementById(decodeURIComponent(location.hash.slice(1)));if(el&&el.classList.contains('exp-record')&&el.hidden){input.value='';input.dispatchEvent(new Event('input'));el.scrollIntoView();}}window.addEventListener('hashchange',revealHash);revealHash();
if('IntersectionObserver' in window){const obs=new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting){document.querySelectorAll('.toc a').forEach(a=>a.classList.toggle('active',a.hash==='#'+e.target.id));}});},{rootMargin:'0px 0px -65% 0px'});document.querySelectorAll('h2[id]').forEach(h=>obs.observe(h));}'''
    doc=f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MMDocRAG 项目实现与实验路线详解</title><meta name="description" content="原论文、本地实现、E1至E41实验、指标参数与后续研究路线的完整说明"><style>{CSS}</style></head><body><a class="skip" href="#main">跳到正文</a><aside class="sidebar"><div class="brand">MMDocRAG 研究指南</div><div class="meta">实现 · 实验 · 指标 · 路线<br>2026 年 9 月 6 日</div><nav class="toc" aria-label="章节目录">{''.join(toc)}</nav><hr><p><a href="PROJECT_GUIDE.md">Markdown 源文</a><br><a href="lab-notebook.html">实验记录与更正</a><br><a href="research-status.html">简短状态说明</a></p><button type="button" onclick="window.print()">打印或另存 PDF</button></aside><div class="layout"><main id="main" class="document">{body}<footer class="footer">本文为研究说明文档。当前实验结论与已撤回历史分开呈现。HTML 可离线阅读，不加载外部脚本、字体或分析服务；数字来自明确的保存运行。生成入口：docs/build_project_guide.py。</footer></main></div><script>{js}</script></body></html>'''
    (DOCS / "project-guide.html").write_text(doc, encoding="utf-8")
    print(json.dumps({"markdown_chars":len(md), "experiments":len(records), "chapters":len(toc), "figures":len(figures), "html_bytes":len(doc.encode()), "assets_bytes":sum(p.stat().st_size for p in ASSETS.glob('*.svg'))},ensure_ascii=False))


if __name__ == "__main__":
    main()
