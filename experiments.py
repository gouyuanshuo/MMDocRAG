"""Registry of every experiment in this project: what it asked, what it found, how to re-run it.

The lab notebook (docs/lab-notebook.html) is the narrative record; this file is
the executable one. Every entry carries the exact commands that produced its
numbers, so a result can be re-derived without reading prose, and a claim that
no longer reproduces becomes visible the moment someone runs it.

    python experiments.py list                     # one line per experiment
    python experiments.py list --suite replay      # only what a replay can run
    python experiments.py show E27                 # detail, commands, caveats
    python experiments.py run E27 --offline        # re-run one experiment
    python experiments.py run-suite replay --offline          # recommended
    python experiments.py run-suite retrieval --offline
    python experiments.py run-suite full-local --offline --include-expensive
    python experiments.py run-suite api --allow-api           # costs money
    python experiments.py run-suite replay --dry-run          # show argv only
    python experiments.py verify E24               # assert contested numbers
    python experiments.py report <run_id|latest>   # re-read a finished run
    python experiments.py artifacts --adopt        # register derived artifacts
    python experiments.py plan                     # the pending end-to-end run
    python experiments.py corrections              # every superseded number

Every run writes to artifacts/runs/<run_id>/: stdout and stderr in full, a
status.json per experiment, machine-readable metrics, per-question CSVs, and
summary.{json,csv,md,html}. Nothing is overwritten -- a re-run gets a new
run_id, and artifacts/runs/latest.json points at the most recent one.

Suites
------
    replay      recompute metrics from existing DBs, vectors, rankings and
                response files. No network, no API, no OCR, no index rebuild.
    retrieval   the current-vintage retrieval experiments and audits.
    full-local  may rebuild OCR, chunks, embeddings and the ColQwen index;
                requires --include-expensive.
    api         experiments that call a paid endpoint; requires --allow-api.
                No other suite can reach them.

Statuses
--------
    pass      infrastructure gate that passed
    neg       a hypothesis that did not survive
    pos       a measured improvement that survived its controls
    fix       a bug found and fixed
    correct   a conclusion revised or retracted after further evidence
    pending   designed and staged, not yet run

`superseded` is never deleted. A number that was published and later corrected
stays in the record next to what replaced it, because a reader who saw the old
figure needs to find out here that it moved.
"""

import argparse
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
NOTEBOOK = "https://claude.ai/code/artifact/41d0a96f-f0a8-4bc8-8f9b-f01e98498a4a"
AUDIT = "https://claude.ai/code/artifact/29d4751e-010a-48a5-a3f8-782c29a61842"

# Anything here is EXPLORATORY unless it says otherwise: the document-disjoint
# split was observed repeatedly across E1-E28 and used to choose methods. Only
# E28's nested CV is free of that selection leak.
E = [
dict(id="E1", phase="1A", status="pass",
     title="复现锚点",
     asks="官方评测代码是否与论文公布的数字自洽？",
     cmds=["{py} eval_all.py --model gemini-2.0-flash --setting 20 --mode multimodal"],
     result="17 项指标逐位命中："
            "3708.7 & 226.4 & 72.8 & 69.7 & 71.2 & 37.8 & 63.4 & 47.4 & 60.0 & 0.130 & 0.292；"
            "judge 3.69/2.79/3.17/2.86/3.05/3.11",
     note="这条是全项目的回归测试。改动任何评测路径后都必须重跑，且必须逐位一致。"),

dict(id="E2", phase="0", status="fix",
     title="评测脚本的静默截断缺陷",
     asks="断点续跑产生的部分结果会不会被静默地在更少样本上求均值？",
     cmds=["{py} eval_all.py --model gemini-2.0-flash --setting 20 --mode multimodal"],
     result="会。eval_all.py:155 用 zip(gold, eval)，对较短列表静默截断且不报错。"
            "已改为按 q_id 建字典 join 并显式报告覆盖率。",
     note="同时修了 :216 的 judge 未对齐——judge 独立遍历，与自动指标不在同一题集上。"),

dict(id="E3", phase="0", status="fix",
     title="工程可复现性",
     asks="仓库能否在本机复现？",
     cmds=["{py} -c \"import manifest; print('manifest module present')\""],
     result="API key 改环境变量、NLTK 资源预下载、断点续跑、删除硬编码 CUDA_VISIBLE_DEVICES、"
            "requirements 冻结、每次实验写 manifest。",
     note=""),

dict(id="E4", phase="0.5", status="correct",
     title="局部 quote 标签不是身份，q_id 也不是主键",
     asks="text5 / image7 这样的局部编号能否当全局 ID？",
     cmds=["{py} -m canonical.build"],
     result="不能。同题 gold 在 15 档与 20 档下局部标签字符串仅 4.6% 相同，"
            "canonical 身份 100% 相同。q_id 跨 split 碰撞，主键必须是 (split, q_id)。"
            "answer_interleaved 也是设置相关的（3,890/4,055 题不同），须单表存放。",
     result2="另：官方 187 个模型-设置组合中 62 个 judge 文件不完整（最低 1,165/2,000），"
             "因此无法从发布产物构造同底的跨模型 Judge 比较。",
     superseded=("曾表述为「论文的 Judge 列不是同底比较」，"
                 "暗示作者内部用了不同分母",
                 "只能就发布文件立论：发布产物不足以构造同底比较，"
                 "不对作者内部流程作断言"),
     note=""),

dict(id="E5", phase="0.5", status="pass",
     title="Gate 1 — gold 全部可映射",
     asks="所有 gold quote 能否映射回 canonical evidence？",
     cmds=["{py} -m canonical.build"],
     result="21,978 / 21,978 = 100%。",
     note=""),

dict(id="E6", phase="0.5", status="pass",
     title="Gate 2 — 自建 chunk 能否文本匹配回官方 gold",
     asks="自己切的 chunk 能不能承载官方 gold？",
     cmds=["{py} -m canonical.gate2"],
     result="82%（精确子串）→ 94.28%（字符 8-gram）→ 98.47%（页级 OCR）→ 98.63%（全语料 OCR + 拼接）。",
     note="精确匹配失败是因为 MinerU 往 gold 里塞幻觉字形（把 62% 写成 $\\mathbf{\\mathcal{G}}_{62}\\%$）。"
          "凡是 gold↔chunk 对齐一律用 8-gram 重叠，不能用精确包含。"),

dict(id="E7", phase="0.5", status="pass",
     title="全语料 OCR",
     asks="没有文本层的页面能否救回？",
     cmds=["{py} -m canonical.ocr --min-chars 100"],
     result="1,983 页 / 93 分钟。无文本页 1,748 → 357，100% 不可见的文档 27 → 0。",
     note=""),

dict(id="E8", phase="1A.5", status="correct",
     title="oracle 增益不是机会，它是测量噪声的产物",
     asks="逐题在两种模态间取较好者，能得到多少增益？",
     cmds=["{py} -m router.build_outcomes",
           "{py} -m router.splits --write",
           "{py} -m router.features --setting 20",
           "{py} -m router.oracle --setting 20 --pareto"],
     result="同模型跨模态 oracle 增益 +8.7 F1（19/19 模型一致，+5.8~+12.3）；"
            "但两个不同模型、同一模态的对照增益是 +9.0。增益不是模态特有的。",
     note="L1 的来源：凡报告 oracle 上界，必同时报告同类系统之间的参照水平。"),

dict(id="E9", phase="1A.5", status="neg",
     title="模态路由不可学",
     asks="能否只看问题就判断这题该用图片还是文字描述？",
     cmds=["{py} -m router.train_modality --all --features shape",
           "{py} -m router.train_modality --all --features all",
           "{py} -m router.diagnose"],
     result="六个探针。正对照预测 question_type AUC 0.874（管道没坏）；test 加权 AUC 0.513；"
            "171 个模型对的 Cohen's kappa 均值 0.038，0/171 超过 0.2；"
            "106 道所有模型都有严格偏好的题里零道达成一致。",
     result2="特征分组重跑：shape(5维,可部署) 8/19、+0.2 F1、2% 空间；"
             "shape+qtype(13维) 9/19、+0.2 F1、2%；emb(384维) 6/19、−0.3 F1、−5%；"
             "all(397维) 5/19、−0.4 F1、−6%。",
     superseded=("13 维下 2/19 显著提升、4/19 显著下降",
                 "平均 +0.2 F1 / 2% 空间已复现；但显著性计数需要逐模型 bootstrap，"
                 "当前脚本只输出原始胜负计数，故显著性数字仍撤下"),
     note="决定性证据是 kappa 0.038：若「这题适合多模态」是问题的属性，模型之间就该达成一致。"
          "另：5 维可部署特征即可拿到与 13 维相同的结果，人工标注的 question_type 无额外贡献。"),

dict(id="E10", phase="1A.5", status="pos",
     title="模态选择的成本-质量表",
     asks="多模态输入值不值它的 token？",
     cmds=["{py} -m router.cost_quality"],
     result="2000 题配对 bootstrap：7/19 模型两种模式 ΔF1 的 CI 跨 0；4 个模型多模态明显更差"
            "（gpt-4.1-nano −11.9、internvl3-8b −11.1、llama4-scout −9.3）；"
            "13 个 token 可信模型中 6 个被纯文本严格支配。"
            "盈亏平衡 548（gpt-4o）~ 43,906（gpt-4.1-mini）token / F1 点。",
     note="价格未核验：router/prices.json 每条都是 verified:false，脚本会打印横幅。"
          "引用任何美元数字前必须先核对。Gemini 系的 in_tok 不含图片 token，成本数字不可用。"),

dict(id="E11", phase="1A.5", status="fix",
     title="泄漏探针的一个自查 bug",
     asks="按 gold 模态路由（需要答案）能否胜过固定策略？",
     cmds=["{py} -m router.diagnose"],
     result="我的探针写成 `\"image\" in s or \"table\" in s`，但 evidence_modality_type "
            "从不含 \"image\"，所以它其实只匹配了 table。改用 VISUAL_KINDS 后，"
            "结论是即使知道 gold 模态也只在 2/19 模型上胜过 best-fixed。",
     note=""),

dict(id="E12", phase="1B", status="correct",
     title="我自己的 OCR 消解了我自己的立论",
     asks="有多少 gold 落在文本检索够不着的地方？",
     cmds=["{py} -m router.retrieval_signal",
           "{py} -m router.retrieval_signal --no-ocr"],
     result="补 OCR 前 12.1% 的 gold 够不着、30 篇文档完全不可见；"
            "补 OCR 后降到 0.7%、0 篇。",
     note="「结构性不可见」的论据不成立，RQ1b 必须改为实证立论。该不该跑这个 OCR？该跑——"
          "真实系统一定会 OCR，不跑等于打稻草人。但结论必须随之修正。"),

dict(id="E13", phase="1B", status="neg",
     title="页粒度上文本检索对视觉证据没有劣势",
     asks="页粒度上视觉 gold 是不是更难被文本检索找到？",
     cmds=["{py} -m retrieval.corpus", "{py} -m retrieval.eval_page_recall"],
     result="text gold 0.845 vs figure/table gold 0.829 @10，差 +0.015。"
            "混淆已排除：758 道纯视觉 gold 的题 recall@10 仍有 0.780。",
     note=""),

dict(id="E14", phase="1B", status="pos",
     title="模态信号是粒度依赖的",
     asks="模态差距为什么在页粒度上消失？",
     cmds=["{py} -m retrieval.eval_quote_recall"],
     result="quote 粒度上 text gold 0.501、image gold 0.680 @10。"
            "页粒度上图表与周边文字捆绑，文本检索顺带找到；quote 粒度上图被剥离出来，差距才显现。",
     note="L2 的来源：粒度决定模态问题是否可见。这是 RQ1b × RQ3 的交互效应。"),

dict(id="E15", phase="1B", status="neg",
     title="「图片 quote 更好检索」是池组成的产物",
     asks="图片 quote 更容易被检索，是因为 VLM 描述与问题词汇对齐吗？",
     cmds=["{py} -m retrieval.diagnose_modality"],
     result="不是。按长度分桶后，idf 加权的覆盖率差距从 +0.080 翻转为 −0.014。"
            "反事实分解：@10 处池大小贡献 +0.236、表示质量贡献 −0.013。",
     note="L3 的来源：长度与池组成是最常见的两个混淆。"),

dict(id="E16", phase="1B", status="pos",
     title="检索器交叉：符号翻转，四个 k 全部一致",
     asks="BM25 与 dense 的相对优劣是否随证据模态变化？",
     cmds=["{py} -m retrieval.dense --image-repr vlm", "{py} -m retrieval.eval_retrievers"],
     result="dense − bm25 = +0.091（文字 gold）/ −0.082（图片 gold），所有 k 一致。",
     note="池是问题条件化的 canonical，绝对值偏乐观；可比的是同池内的相对关系。"),

dict(id="E17", phase="1B", status="correct",
     title="二元检索器路由：结论已被正确的标签推翻一半",
     asks="逐题在 BM25 与 dense 之间二选一，能否胜过固定策略？",
     cmds=["{py} -m retrieval.route_headroom",
           "{py} -m retrieval.route_outcome --features scores --k 10",
           "{py} -m retrieval.route_outcome --features all --k 10"],
     result="用正确的 outcome 标签（逐题 recall 差值、按 |regret| 加权）重做："
            "路由 0.7273 vs 最优固定 0.7113（+0.0160，CI [−0.0052,+0.0371] 跨 0），"
            "但显著输给静态 RRF 0.7551（−0.0279，CI [−0.0503,−0.0050]）。"
            "regret 加权 AUC 0.574；加入 384 维句向量压到 0.517。",
     superseded=("路由 0.706 输给最优固定 0.711，二元路由被证伪；"
                 "「61.9% 的题两种模态都有 gold」被用作结构性论据",
                 "原实验训练的是 gold 模态标签再写死映射，只否证了那一条人工策略。"
                 "正确结论：路由达不到融合的质量，它买到的只是把两次检索省成一次"),
     note="L15 的来源：训练的标签必须就是你要的决策。"),

dict(id="E18", phase="1B", status="pos",
     title="VLM 描述 vs 裁剪 OCR：+0.42 recall",
     asks="图表证据用 VLM 描述还是用裁剪 OCR 来检索？",
     cmds=["{py} -m retrieval.ocr_quotes",
           "{py} -m retrieval.eval_retrievers --image-repr ocr",
           "{py} -m retrieval.eval_retrievers --image-repr vlm"],
     result="image gold @20：VLM 描述 0.791 vs 裁剪 OCR 0.369，差 +0.422。"
            "两者拼接不改善（0.779）。",
     superseded=("差距来自视觉理解而非 OCR 提取失败（因为在 OCR 确实提取到文字的 "
                 "3,031 条上差距仍有 +0.416）；该效应比任何路由效应大 60 倍",
                 "只能说：在当前问题条件化池、BM25 与 RapidOCR 表示下 VLM 描述显著更好。"
                 "6,565 条中 1,270 条（19.3%）OCR 为空，非空也不代表提取完整准确。"
                 "「60 倍」是把 recall 差值与 router 的 F1 差值相除，跨指标比较无效，已作废"),
     note=""),

dict(id="E19", phase="1B", status="correct",
     title="自适应预算分配：上界远小于原报数字",
     asks="逐题分配文本/图片配额，有多少可争取的空间？",
     cmds=["{py} -m retrieval.budget_alloc --pool canonical --k 20",
           "{py} -m retrieval.audit_e19_ties --pool selfbuilt --k 20",
           "{py} -m retrieval.audit_e19_ties --pool canonical --k 20"],
     result="97% 的题有多个并列最优配额（中位 16 个 / 共 21 个），"
            "np.argmax 恒取最小索引，把 1,013/1,999 题判为 a=0，排列对照被推向极端。"
            "真实 regret（oracle − 最优固定）= +0.0694（自建）/ +0.0744（canonical）。"
            "固定配额对 79.5% / 78.2% 的题本身已是最优。",
     superseded=("查询特异成分 +0.173 / +0.179",
                 "那是 oracle 减一个退化对照。自适应分配的上界是 regret +0.069 / +0.074，"
                 "且近八成的题没有任何可改进空间"),
     note="L14 的来源：argmax 会在并列时悄悄制造结构。"),

dict(id="E20", phase="1B", status="pass",
     title="真实规模自建池上复现 E19",
     asks="E19 的结论是不是池偏差造成的？",
     cmds=["{py} -m retrieval.quote_corpus",
           "{py} -m retrieval.budget_alloc --pool selfbuilt --k 20"],
     result="自建 92,752 chunk / 220 篇 = 422/篇（论文 536 的 79%），gold 转移 96.86%。"
            "文字:图片比从 3.2:1 变到 14.3:1（真值 8.5:1），结论不变。",
     note="两个池从两侧夹住真实比例——但它们共用同一个不完整的图片侧，见 E28⑤。"),

dict(id="E21", phase="1B", status="pos",
     title="瓶颈收敛成一个可量化目标",
     asks="外部报告提出的比例分配规则管用吗？",
     cmds=["{py} -m retrieval.budget_alloc --pool canonical --target mostly"],
     result="用真实模态比例分配可兑现 41%~49% 的空间——规则本身是对的；"
            "但预测该比例的 R² 为负，所以输入拿不到。",
     note="外部报告另有三处硬错误，见 E22。"),

dict(id="E22", phase="1B", status="pass",
     title="核实外部报告引用的四篇论文",
     asks="外部研究报告引用的文献是否属实？",
     cmds=[],
     result="四篇中两篇属实、两篇的具体主张与原文不符。相关建议按核实结果取舍。",
     note="无脚本，人工核对。"),

dict(id="E23", phase="1B", status="correct",
     title="高维特征一直在埋掉低维真信号",
     asks="二次反思能否预测该用多少视觉配额？",
     cmds=["{py} -m retrieval.reflect_alloc --pool canonical",
           "{py} -m retrieval.reflect_alloc --pool selfbuilt"],
     result="R² −0.155（384 维句向量）→ +0.110（11 维分数）→ +0.136（22 维分数+首轮）。"
            "但分配收益仍是 0~2%。",
     note="L10 的来源：1,211 个训练样本 + 384 维句向量，把 R²=+0.11 的真实信号压成 −0.07。"
          "报负结果之前必须单独测一遍最小特征集。这条倒逼重查了 E9。"),

dict(id="E38", phase="1B", status="neg",
     title="RQ1b 的 R² 目标问错了：完美预测本身也只值 +0.023",
     asks="proposal 给 RQ1b 设了一个 R² 目标，并点名三个未试的特征源"
          "（视觉检索器分数、模型内部表示、LLM 证据充分性判断）。"
          "E23 把 R² 从 −0.155 抬到 +0.136 就停住了，只说「分配收益仍是 0~2%」。"
          "那么究竟是 R² 太低所以值得换特征源，还是 R² 到收益的映射本身就是平的？",
     cmds=["{py} -m retrieval.r2_target --pool canonical",
           "{py} -m retrieval.r2_target --pool selfbuilt"],
     result="**是后者。**对一格目标 R² 造一个无偏合成预测器 "
            "`p = v + N(0,σ²)`（σ 按裁剪后的**实测** R² 反解，"
            "因为 visual_share 大量堆在 0 和 1，闭式解会把目标 0 算成实测 0.29），"
            "收缩系数在**测试集**上选——两项都刻意取最乐观，所以每一行都是天花板。"
            "结果：canonical 池上 R²=0 买到 +0.0071、**R²=1.0 也只买到 +0.0229**"
            "（37% 空间）；selfbuilt 池 +0.0099 → **+0.0275**（45%）。"
            "**E23 已经拿到的 0.136 处是 +0.0089 / +0.0124；"
            "把 R² 一路推到完美，也只多 +0.014 recall。**",
     result2="给决策用的刻度：**要拿到真值分配一半的收益需 R²≈0.30，两池一致**。"
             "「区间不跨 0 所需的最低 R²」两池并不一致——canonical 是 0.20，selfbuilt 报 0.00，"
             "但后者那一行的下界是 +0.0000（四位小数下贴零），"
             "按本项目「CI 下界贴 0 不算显著」的纪律不能算作不跨 0。"
             "脚本原先用 `lo > 0` 判星，已改为下界须超过报告精度 5e-5。"
             "而从 0.136 推到 0.30 只值 +0.003（canonical）/ +0.002（selfbuilt）。"
             "**因此三个未试特征源最多在争夺 +0.014 recall**，"
             "其中「LLM 证据充分性判断」正是 CRAG 的机制，"
             "而 CRAG 实测该机制自身要付 +0.15 TFLOPs/token、0.512s vs 0.363s，"
             "即 41% 的时延开销。按这个量级对比，这条路不值得买。",
     note="L-ceiling：当一个中间量（这里是 R²）被设成目标时，"
          "先测「该中间量取到完美时下游收益是多少」，再决定要不要投入去提高它。"
          "做法是造一个校准到目标精度的合成预测器，而不是去猜新特征能带来多少。"
          "另两条实现纪律：(1) 合成预测器被裁剪到 [0,1] 后实测 R² 会显著偏离名义值，"
          "必须报实测值并按实测值反解噪声；"
          "(2) 各目标点要用**共同随机数**（同一批标准正态只按 σ 缩放），"
          "否则每点 ±0.001 的蒙特卡洛噪声会让曲线非单调，诱使读出并不存在的次序。",
     limits="exploratory：该切分自 E9 起被反复观察并用于挑方法。"
            "合成预测器的误差与真值独立且无偏，真实 ridge 会向训练均值收缩、"
            "误差与真值相关，因此在同一 R² 下**严格更差**——这条曲线是上界不是预报。"
            "收缩系数在测试集上选，任何可部署系统都做不到，同样是为了取上界。"
            "结论只覆盖 RQ1b 的配额分配决策，不能外推到 E36 的升级决策。"),

dict(id="E24", phase="1B", status="neg",
     title="ColQwen2 在本项目的池规模下不值它的 GPU 成本",
     asks="视觉检索器能否胜过打在 VLM 描述上的文本检索器？",
     cmds=[".venv-colpali/Scripts/python.exe -m retrieval.colqwen_index",
           "{py} -m retrieval.eval_colqwen"],
     result="同一图片池 @20：BGE 0.935 / BM25 0.929 / ColQwen 0.929，三者打平。"
            "互补性 +0.095，但两个文本检索器已给 +0.081 → 视觉特有只剩 +0.014。",
     result2="全量 2,000 题复核（E28）：在视觉槽位上单独替换，ColQwen − 描述检索 = "
             "+0.0075 / +0.0089 / +0.0039（k=10/15/20），CI 全部跨 0。原结论维持。",
     superseded=("（审计初版曾称）E24 方向错误，ColQwen 在 k=15/20 显著有益 +0.0269 / +0.0220",
                 "那只在 396 题探索半区成立，全量重算 CI 跨 0，该主张已由作者撤回"),
     note="池饱和是结构性的：图片候选按文档计中位仅 20 个（原记录写的 29 是按题计的），"
          "@20 对一半文档等于取走整个池。模型为 ColQwen2-v1.0、文本侧 bge-small，"
          "与论文的 v0.1 / bge-large 不同，故结论限于本项目可获得的池规模与裁剪粒度。"),

dict(id="E25", phase="4", status="pos",
     title="粒度 × 预算：两个轴给出完全相反的排序",
     asks="证据粒度能否改善质量与上下文成本的平衡？",
     cmds=["{py} -m retrieval.quote_corpus --target-chars 600 "
           "--out retrieval/quotes_t600.sqlite --no-gold-map",
           "{py} -m retrieval.eval_granularity",
           "{py} -m retrieval.eval_granularity --pack greedy"],
     result="固定 top-k 下越粗越好（t2400 比官方粒度高 +0.137 @20）；"
            "固定预算下排序完全倒转（t2400 在 500 预算处低 −0.097）。两向每一格都显著。"
            "粗粒度 top-20 花 4,273 个词元，细粒度只花 1,236——优势是用未计价的上下文买的。"
            "七档语料确认最优区是 50~300 字符的宽平台，且存在下限（不合并的原始区块显著更差）。",
     superseded=("固定 token 预算；RQ3 已完成",
                 "n_tok 是正则词元不是 BPE token，应称 word-like retrieval budget；"
                 "且仅覆盖 text gold + BM25 + 字符切分，应称「RQ3 的文本-BM25 切片已完成」"),
     note="没有任何粒度在论文自己的预算点上显著更优，所以 RQ3 的正面形式不成立；"
          "但「用 recall@k 比较 chunk 粒度会系统性偏袒粗粒度」是一个量级很大的方法学结论。"),

dict(id="E26", phase="4", status="neg",
     title="small-to-big 被证伪；细粒度优势一半是预算量化损失",
     asks="用细 chunk 排序、返回其粗 parent，能否兼得两者？",
     cmds=["{py} -m retrieval.eval_small2big --fine retrieval/quotes_t100.sqlite "
           "--coarse retrieval/quotes_t600.sqlite",
           "{py} -m retrieval.eval_small2big --fine retrieval/quotes_t100.sqlite "
           "--coarse retrieval/quotes_t600.sqlite --pack greedy"],
     result="small-to-big 在每个预算上都劣于两个纯臂（−0.006~−0.017），parent 映射率 99.94%。"
            "细粒度优势在 prefix 规则下 +0.028/+0.022/+0.015（显著），"
            "改 greedy 后降到 +0.015/+0.015/+0.011（均不显著）。",
     note="greedy 更贴近真实系统，因此不把 prefix 下的 +0.028 当作结论。"
          "这是第四次靠对照拦下会被写成正面结果的数字。"),

dict(id="E27", phase="2", status="pos",
     title="静态检索配置的改进",
     asks="模态内 RRF 融合 + 均衡配额，能比基线好多少？",
     # The headline is a 2x2: two candidate pools x two evidence budgets, each
     # scored out-of-fold. Reporting only two of the four cells (as this entry
     # used to) lets a reader assume the missing pair looks like the pair shown.
     # Commands 3-6 produce all four; nothing is filled in from prose.
     cmds=["{py} -m retrieval.dense_chunks",
           "{py} -m retrieval.eval_stack_v2 --k 10 --pool selfbuilt --dump",
           "{py} -m retrieval.eval_stack_v2 --k 20 --pool canonical --dump",
           "{py} -m retrieval.nested_cv --pool selfbuilt --k 10",
           "{py} -m retrieval.nested_cv --pool selfbuilt --k 20",
           "{py} -m retrieval.nested_cv --pool canonical --k 10",
           "{py} -m retrieval.nested_cv --pool canonical --k 20"],
     result="document-grouped 5 折 OOF（无脚本内选择泄漏，全部 2,000 题 out-of-fold，"
            "未映射 gold 计为 miss）相对最接近论文的本地 hybrid，完整 2x2："
            "自建池 k=10 +0.0608、k=20 +0.0304；canonical 池 k=10 +0.0541、k=20 +0.0269；"
            "四格 document-cluster CI 全部不跨 0。"
            "相对本地 BGE-small-only 替代基线：k=10 +0.0683 / +0.0616，k=20 +0.0343 / +0.0308。"
            "以上数字由 `python experiments.py verify E27` 从指定 run 的 metrics.json 断言，"
            "不从本段文字读取。",
     superseded=("比论文发布的检索配置高 +0.023 ~ +0.049，两个池 × 三个预算六格全显著",
                 "基线其实是本地 bge-small 同时跑文本与图片文字描述，既非论文的 bge-large "
                 "也不含 ColQwen 视觉检索器，不能称「优于论文配置」；"
                 "且当时按题 bootstrap（396 题只来自 55 篇文档），并静默丢弃 62 条未映射 gold"),
     note="这是 static retrieval baseline，不是 adaptive routing。"
          "本项目的自适应方法此后必须在相同预算与相同候选池上超过它"
          "（Phase 3 已做，见 E35/E36：静态配置未被逐题路由超过，"
          "路由买到的是成本而不是质量）。"
          "成本：基线本就跑 dense，融合只多加一遍文档内 BM25，纯 CPU。"
          "\n2026-08-30 修了一个报告路径的缺陷（发现于 Phase 3 的回归核对）："
          "`nested_cv.py` 对同一个比较**调了两次 `cluster_ci`**——"
          "一次给打印的表格，一次给 metrics.json——"
          "两次从同一条前进中的随机流里抽了**不同的 bootstrap 样本**，"
          "于是人读的 CI 与机器读的 CI 在第三位小数上不一致，"
          "而 metrics.json 才是权威记录。现在只算一次、两处共用。"
          "**点估计从未受影响**（0.06081109307359307 逐位不变），"
          "受影响的只有区间端点：selfbuilt k=10 的记录值由 "
          "[+0.0468,+0.0753] 变为 [+0.0471,+0.0748]，四格显著性与符号全部不变。"
          "另一条同期核对：为 Phase 3 给 `eval_stack_v2.build` 加的 "
          "`keep_scores` / `top_keep` 两个参数在默认关闭时是死代码，"
          "E27 四个点估计逐位复现，确认无影响。",
     result2="**2026-09-01：头条已在 bge-large 上复核，见 E40。**"
             "四格全部存活且点估计几乎不动（+0.0605 / +0.0329 / +0.0525 / +0.0267，"
             "对应本条的 +0.0608 / +0.0304 / +0.0541 / +0.0269，最大变动 +0.0025）。"
             "**本条的数字仍由 bge-small 产出**，作为历史记录保留；对外表述头条时"
             "应引用 E40，因为 bge-large 是本项目唯一字节可证的模型。"
             "另注：相对替代基线 A 的差值对编码器强度敏感（缩水 0.006~0.008），"
             "**头条应报相对论文式对照 E 的差值**。"
     ),

dict(id="E28", phase="audit", status="correct",
     title="复现性与结论边界审计",
     asks="已发布的结论有哪些超出了证据？",
     # Audit experiments only. The nested-CV cells and the stack evaluation moved
     # to E27, which owns that result: running them here too produced two copies
     # of selfbuilt k=10 in every summary, under two different experiment ids.
     cmds=["{py} -m retrieval.audit_e19_ties --pool selfbuilt --k 20",
           "{py} -m retrieval.route_outcome --features scores --k 10"],
     result="三处系统性错误：基线身份、bootstrap 抽样单位（396 题 / 55 篇文档）、"
            "recall 分母（62 条未映射 gold 被静默剔除）。四条结论被改写（E4/E9/E17/E19/E24/E25/E27）。"
            "并设计了 document-grouped nested CV，把主结果从 exploratory 提升为无脚本内选择泄漏；"
            "该协议的四格结果现由 E27 拥有并执行，本条目只保留审计实验本身。",
     note="审计过程中本人一度依据 396 题切分宣称 E24 方向反转，"
          "随后全量重算发现 CI 跨 0，已撤回——低功效切分上的假阳性，一并记录。"),

dict(id="E30", phase="audit", status="pos",
     title="归因消融：+0.054 究竟来自哪个组件",
     asks="主结果同时改了文本检索器、图片检索方式和配额，三者各占多少？",
     # One command, not four: Holm needs all twelve p-values in the same process.
     # Four separate runs could only ever report uncorrected stars.
     cmds=["{py} -m retrieval.ablation --all-cells"],
     result="2x2x2 因子设计，四格（两池 x 两预算）全部近乎完美可加（交互残差 |r|<0.00005）。"
            "12 个主效应（4 格 × 3 因子）的 raw 95% CI 全部不跨 0，"
            "且 **12/12 在 Holm 校正后仍然存活**（最大 p_holm = 0.0165）。"
            "量级排序随预算翻转："
            "k=10 配额 +0.026~+0.028 > 图片描述检索 +0.016 > RRF 文本融合 +0.010~+0.012；"
            "k=20 图片描述检索 +0.014 > RRF 文本融合 +0.010~+0.013 > 配额 +0.005~+0.006。"
            "即：RRF 文本融合在任何一格都是三者中最小的一项，紧预算下只占总量约 19%。",
     note="补上了 E28 自己提出但一直未做的归因要求。三点边界："
          "(1) 这是归因不是确认——每格用固定配置在全部 2,000 题上评价，"
          "区间描述的是效应在本 benchmark 上的稳定性，泛化性仍只由 nested_cv 支持；"
          "(2) 配额因子用的是事先命名的 BALANCED_QUOTA，不是各折选出的配额，"
          "否则会把选择偷渡进分解；"
          "(3) 「ColQwen -> 描述检索 +0.014~+0.016 显著」与 E24「CI 跨 0」不矛盾——"
          "E24/nested_cv 比的是 ColQwen 对 **dense-only** 描述检索（+0.0075，CI 跨 0），"
          "本实验比的是对 **RRF** 描述检索。即 dense 描述 ≈ ColQwen < RRF 描述。"
          "ColQwen 臂经审计未被削弱：它排完每篇文档图片池的 100%，一条视觉 gold 都没漏；"
          "但该池只覆盖这 220 篇 evaluation 文档 13,999 张唯一图片中的 6,487 张"
          "（46.34%；此前写的 46.8% 是用 6,548 条 evidence row 除以唯一图片数，"
          "单位不一致，已作废），按文档中位仅 20 个候选，k=20 已接近饱和，"
          "因此这是 image-description retrieval 在**当前不完整池**上的结果，"
          "不能写成视觉检索器能力不如描述检索。"),

dict(id="E35", phase="3", status="pos",
     title="路由的天花板：tie-aware oracle 与匹配预算的置换对照",
     asks="在训练任何路由器之前——逐题挑检索动作到底有没有可学的空间？"
          "表观上界里有多少只是 tie 和动作配比造成的假象？"
          "在只花一半 CPU 预算的动作集合里，完美选择能不能打过静态 RRF？",
     cmds=["{py} -m router.actions --pool selfbuilt",
           "{py} -m router.actions --pool canonical",
           "{py} -m router.tie_audit --pool selfbuilt --k 10",
           "{py} -m router.tie_audit --pool selfbuilt --k 20",
           "{py} -m router.tie_audit --pool canonical --k 10",
           "{py} -m router.tie_audit --pool canonical --k 20"],
     result="**天花板存在，而且没有被 tie 假象吃掉**。动作空间是 12 个"
            "（文本检索器 3 × 图片侧检索器 4），固定配额。四格一致："
            "把动作限制在 cpu<=2（静态 RRF 要 4）时，完美选择相对静态 RRF 为 "
            "selfbuilt k=10 **+0.0502** [+0.0413,+0.0594]、k=20 +0.0405、"
            "canonical k=10 +0.0520、k=20 +0.0399，四格 CI 全部不跨 0。"
            "同预算下的**最优固定动作**则输给静态 RRF −0.0164 ~ −0.0220（四格全显著）。"
            "两者相减即路由器要补上的缺口：约为该预算内 oracle 空间的 **26%~33%**。",
     result2="E19 的两项高估在这里都被单独量化。"
             "(1) **tie**：97.5% 的题有不止一个最优动作，中位 9 个；"
             "**47.9% 的题所有 12 个动作完全同分**（其中 33.4% 全对、1.9% 全错），"
             "这些题按构造不含任何可路由信号。用 argmax 破 tie 的置换对照"
             "（E19 的做法）把表观空间抬高了 +0.0087~+0.0132。"
             "(2) **动作配比**：置换对照保持 oracle 的动作多重集、只打乱谁配到哪个动作。"
             "本实验里它落在 0.6844，**低于**最优固定动作 0.7101——"
             "与 E19 方向相反，说明 oracle 的优势不来自配比，而确实是逐题的。"
             "因此这里的约束下界是**最优固定动作**，不是置换对照；"
             "两者取更强的那个，是 E8 纪律的正确形式。",
     note="L-tie：报 oracle 上界必须同时给 tie-aware oracle 和保配比的置换对照，"
          "并明确说明哪一个才是约束下界——它不总是同一个。"
          "另：cpu pass 与 ColQwen 的 gpu pass 是两种货币，本项目没有测过它们之间的"
          "兑换率，因此预算是一对上限而不是一个标量，"
          "「最便宜的最优动作」必须在两种字典序下各报一次。",
     limits="exploratory：该切分自 E9 起被反复观察并用于挑方法。"
            "配额固定为 BALANCED_QUOTA，--include-quota 可展开为"
            "检索器 × 配额的联合空间，但配额是免费的，那只是空间上界而不是预算问题。"),

dict(id="E40", phase="2", status="pos",
     title="E27 头条在 bge-large 上复核：提升不是弱编码器的产物",
     asks="E27 的 +0.061 是真实的配置提升，还是 bge-small 太弱制造出来的？"
          "换成本项目唯一字节可证、且更接近论文规模的文本检索器之后，四格还剩几格？",
     cmds=["{py} -m retrieval.nested_cv --pool selfbuilt --k 10 --dense-model models/bge-large-en-v1.5",
           "{py} -m retrieval.nested_cv --pool selfbuilt --k 20 --dense-model models/bge-large-en-v1.5",
           "{py} -m retrieval.nested_cv --pool canonical --k 10 --dense-model models/bge-large-en-v1.5",
           "{py} -m retrieval.nested_cv --pool canonical --k 20 --dense-model models/bge-large-en-v1.5"],
     result="**四格全部存活，且点估计几乎不动。**折外提升相对论文式对照 E："
            "自建池 k=10 **+0.0605** [+0.0466,+0.0752]、k=20 **+0.0329** [+0.0232,+0.0428]；"
            "canonical 池 k=10 **+0.0525** [+0.0379,+0.0672]、k=20 **+0.0267** [+0.0173,+0.0361]。"
            "与 bge-small 的 +0.0608 / +0.0304 / +0.0541 / +0.0269 相比，"
            "最大变动是 selfbuilt k=20 的 +0.0025，四格 CI 全部不跨 0。"
            "**结论：E27 的头条提升不是编码器强度的产物**，"
            "这正是 E34 撤回 E−A 那条结论之后必须补上的对照。",
     result2="**但相对替代基线 A 的差值确实缩水了**，方向与 E34 的 D−A 一致："
             "自建池 k=10 从 +0.0683 落到 +0.0626，k=20 从 +0.0343 落到 +0.0291；"
             "canonical 池 k=20 从 +0.0308 落到 +0.0229。"
             "机制清楚——A 本身就是纯 dense 文本臂，换强编码器只让基线单边变强，"
             "而选出的流水线是 RRF 融合，增益来源本就不止 dense。"
             "**因此头条应当报相对 E 的差值，而不是相对 A 的**，后者对编码器强度敏感。",
     note="L-encoder：`retrieval/nested_cv.py` 此前没有 `--dense-model`，"
          "第 117 行按位置调用 `build(...)` 因而静默使用 bge-small 默认值——"
          "**头条结果的编码器是一个从不出现在 argv 里的自由变量**。"
          "本次先补上该参数，再用默认值重跑 selfbuilt k=10 作对照，"
          "拿到 +0.0608 / +0.0683 与记录逐位相同，证明改动是 no-op，"
          "然后才相信 bge-large 的四格。**先证明重构没改变旧数，再报新数。**",
     limits="本条只搬了 E27。其余 14 个依赖 bge-small-vlm 的实验仍是 bge-small 的结果，"
            "作为历史记录保留；其中 E35/E36/E37 的增益是两臂同时换编码器的相对量，"
            "对编码器不敏感，但**尚未实测**，不应写成已复核。"
            "同样地，这条切分自 E9 起被反复观察，本结果与 E27 一样只能标 exploratory。"),

dict(id="E37", phase="2", status="pos",
     title="静态提升按题型切片：增益集中在纯视觉题，且只在 k=10",
     asks="E27 的 +0.061 到底落在谁身上？"
          "proposal Experiment 2 要求按题型分报，那五类在 MMDocRAG 上还剩几类可评？"
          "「某一类显著、另一类不显著」能不能当成异质性证据？",
     cmds=["{py} -m retrieval.slice_by_type --pool selfbuilt",
           "{py} -m retrieval.slice_by_type --pool canonical"],
     result="**主结论是稳健性：k=10 上八个切片全部存活 Holm**"
            "（16 个切片检验一个家族）。增益不是某一类问题带来的，"
            "cross-modal +0.0346、pure visual +0.1037、cross-page +0.0586、"
            "single-page +0.0634，四个 question_type 全部在 +0.047 ~ +0.068。"
            "唯一失手的一格是 k=20 的 Analytical（+0.0130，CI 跨 0，n=201/99 篇）。"
            "**canonical 池独立复现**：k=10 八格同样全部存活，"
            "cross-modal +0.0239、pure visual +0.1037、cross-page +0.0532、"
            "single-page +0.0553；k=20 有两格不显著"
            "（pure visual Holm p=0.084、Analytical CI 跨 0）。"
            "纯视觉题的 +0.1037 在两个池上逐位相同，这是应当出现的一致性检查——"
            "纯视觉题的 gold 全在图片侧，换文本池不改变它的召回。",
     result2="**异质性只出现在一个轴上，而且必须用对照检验而不是「一个显著一个不显著」来判定**。"
             "模态对照 cross-modal − pure visual 在 k=10 为 **−0.0691** "
             "[−0.0967,−0.0420]，Holm p=0.0010：纯视觉题拿到的提升约为跨模态题的三倍。"
             "机制自洽——选出的配额把视觉槽位从论文式的 3 提到 6，"
             "gold 全在图片侧的题因此受益最大。"
             "canonical 池上是 −0.0798 [−0.1077,−0.0534]，同样 Holm p=0.0010。"
             "这个异质性到 k=20 就消失（selfbuilt +0.0078、canonical +0.0162，CI 均跨 0），与 E25/E26 的"
             "预算量化损失一致：槽位一多，配额差异就不再是瓶颈。"
             "**跨页轴在两个池、两个 k 上都查不出异质性**（四个对照 CI 全部跨 0），"
             "所以这条提升与跨页推理无关。",
     note="L-slice：切片必须在选择之后做。折外选择在全语料上按文档分组完成一次，"
          "切片只是对已经算好的折外向量做划分——若让每个切片自己选配置，"
          "得到的就不再是 E27 的数字，而是 16 个各自过拟合的新实验。"
          "另：两个家族分开声明并各自 Holm（16 个切片检验、4 个对照检验），"
          "对照检验才是异质性问题的答案。",
     limits="exploratory：该切分自 E9 起被反复观察并用于挑方法。"
            "**proposal Experiment 2 的五类里有两类在 MMDocRAG evaluation split 上无法评价**："
            "pure text 只有 1 题（n=1，无区间可言），unanswerable 一题都没有"
            "（每题都带 gold 证据）。这是 benchmark 的属性，不是分析的缺口，"
            "写报告时必须照此说明而不能假装跑了五类。"
            "question_type 里 Inferential/Procedural/Causal/Application-based "
            "四类均低于 100 题或 20 篇的阈值，只描述不检验。"),

dict(id="E36", phase="3", status="neg",
     title="逐题路由：GPU 决策可学，CPU 融合决策不可学",
     asks="静态 RRF 对每个 query 都付两个检索器。"
          "路由器能否用更少的检索代价达到同样的质量？",
     cmds=["{py} -m router.phase3_cells --features search",
           "{py} -m router.phase3_cells --features shape+firstpass",
           "{py} -m router.budget_router --pool selfbuilt --k 10 --policy A "
           "--features free",
           "{py} -m router.budget_router --pool selfbuilt --k 10 --policy B "
           "--features shape+firstpass"],
     result="两条级联，八格（2 级联 × 2 池 × 2 预算），一个 Holm 家族，"
            "主家族是**同预算下路由器 − 随机分配**（B=0.50 事先声明）。"
            "以下 result 段的区间**全部是「特征组事先固定为低维组」的口径**，"
            "折内选特征组的口径见 result2，两者不可混用。"
            "**CPU 级联**（bm25 两分支 → RRF 两分支，2→4 pass）：0/4 格存活 Holm，"
            "点估计 +0.0005 ~ +0.0046；路由器只拿到 oracle 相对随机优势的 "
            "−0.9%~8.6%，且在任何低于满预算的 B 上都达不到静态 RRF 的质量。"
            "**GPU 级联**（dense 文本 + bm25 图片描述 → RRF 文本 + ColQwen 视觉）："
            "特征组事先固定为低维组时 **3/4 格存活 Holm**（第 4 格 p_holm=0.080），"
            "delta +0.0064 ~ +0.0111。"
            "该级联在 B=0.05~0.15 就追平「总是用 ColQwen」的质量，"
            "即 **只在 5%~15% 的 query 上真的看像素**，"
            "代价是 CPU pass 从 2.00 升到 2.05~2.15（首轮被丢弃的那一遍是沉没成本）。",
     result2="但把**特征组也放进折内选择**之后（不再由我看着结果挑），"
             "主家族只剩 **1/8 存活 Holm**，GPU 级联四格点估计仍全为正"
             "（+0.0015 ~ +0.0102）、两格 raw 显著；"
             "CPU 级联落到 −0.0016 ~ +0.0043（capture −2.1%~7.1%），依旧是零。"
             "原因是内层目标在 1,200~1,600 条训练样本上**选不稳特征组**："
             "40 个 fold 里换了 5 种组合，其中 6 次选中含 384 维句向量的 free 组。"
             "这是 E23 的教训上升一层：不只是「别把句向量拼进去」，"
             "而是「在这个样本量下，连该不该拼进去都选不准」。"
             "因此本条的可辩护结论是**方向一致但强度取决于特征组是否事先固定**，"
             "两种口径都必须报。",
     result3="**Policy A（检索前就选检索器，成本恒为 2 pass）是干净的负结果**："
             "四种特征组下路由器全部**输给**折内选出的最优固定动作"
             "（−0.0044 ~ −0.0088，其中两组 CI 不跨 0），"
             "与 E17 在 quote 粒度上的结论一致。"
             "次要家族（路由器 B=0.50 − 总是升级）：CPU 级联 4/4 显著为负"
             "（−0.0134 ~ −0.0169），GPU 级联 4/4 不显著、点估计全为正——"
             "即**在一半的 ColQwen 调用下打平**，这是成本主张而非质量主张。",
     note="L-budget：主对照必须是**同预算的随机分配**。"
          "「比不升级好」是废话——升级本身就多做了检索。"
          "L-sunk：级联的升级成本要按**增量**计费，"
          "首轮做了而升级用不上的那一遍是沉没成本、不退款；"
          "GPU 级联在 B=1 时是 3 cpu + 1 gpu，比直接跑静态系统（2 cpu + 1 gpu）更贵。"
          "L-exactness：随机对照的逐题期望可以**精确算出**"
          "（均匀抽 m/n 时第 i 题的期望是 base_i + (m/n)·gain_i），"
          "用几百次抽样去估它会给唯一承载主张的对照引入蒙特卡洛噪声，"
          "本实验里那点噪声足以让 Holm 校正后的 p 跨过 0.05。",
     superseded=("CPU 级联点估计 −0.0004 ~ +0.0046、capture −1%~9%；"
                 "oracle regret +0.034 ~ +0.070。"
                 "另：交接文档与记录簿曾把成本结论写作「同质量下 / 质量差异不显著的前提下，"
                 "ColQwen 调用降到 5%~15%」",
                 "三个区间都把**两个口径各取一端**拼在了一起——下界来自折内选特征组、"
                 "上界来自事先固定。按口径拆开后：事先固定口径 CPU 级联 "
                 "+0.0005 ~ +0.0046、capture −0.9%~8.6%、regret +0.0337 ~ +0.0615；"
                 "折内选口径 CPU 级联 −0.0016 ~ +0.0043、capture −2.1%~7.1%、"
                 "regret +0.0339 ~ +0.0701。结论未变：CPU 级联两个口径下都是零。"
                 "另（2026-09-01）：「同质量下」暗示做过一次等价性检验，**没有做过**。"
                 "B=0.05~0.15 是路由器 recall 曲线追平静态系统的交点，"
                 "是从曲线上读出来的描述量；被检验的是「相对同预算随机分配」。"
                 "本条注册表的 limits 一直写对，**丢掉限定词的是转写进叙述文档的那一步**——"
                 "所以核对不能只核对注册表，还要核对引用它的每一处"),
     limits="exploratory：该切分自 E9 起被反复观察并用于挑方法。"
            "oracle regret 仍然很大（事先固定口径 +0.0337 ~ +0.0615，"
            "折内选口径 +0.0339 ~ +0.0701），"
            "路由器只实现了可得空间的约十分之一，"
            "**不能**写成「路由有效」，只能写成"
            "「在图片侧的升级决策上存在可学的逐题信号，且它买到的是成本而不是质量」。"
            "B=0.05~0.15 这个「追平静态系统的预算」是看着曲线读出来的，"
            "属描述性数字，不是检验。"
            "端到端生成质量未测——本条全部指标是 evidence recall，"
            "要接到 F1 需要一次配对 API 运行，未做。"),

dict(id="E39", phase="3", status="pending",
     title="待执行：把 E36 的 GPU 级联接到端到端生成",
     asks="「同质量下 ColQwen 调用从 100% 降到 5%~15%」这句话目前只在 evidence recall 上成立。"
          "它在 quote-selection F1 上还成不成立？",
     cmds=["{py} -m router.budget_router --pool canonical --k 10 --policy B "
           "--features shape+firstpass --metrics-out artifacts/e39/router",
           "# 然后照 E29 的两臂配对生成，唯一变量是候选块"],
     result="**尚未执行。** 需要一次付费的配对 API 运行，预算参照 E29："
            "600 题 × 2 臂 = 1,225 次调用、12.09 AUD。**未获批准前不跑。**",
     result2="设计已定死，照 E29 的协议：同模型、同 prompt、同 gold，只有候选块不同。"
             "静态臂 = `rrf text + colqwen visual`（每题都调 ColQwen）；"
             "路由臂 = 同一配置，但只对路由器选中的题调 ColQwen，其余题走 RRF 描述分支。"
             "**逐题的升级决策已经落盘**，不需要下游重新推导："
             "`router/budget_router.py` 的 per_question.csv 现在带 "
             "`escalate_at_B005` / `escalate_at_B015` / `escalate_at_B050` 三列布尔，"
             "由与实验同一个 `escalation_mask` 生成（实测比例逐位等于 0.05/0.15/0.50）。"
             "**判读事先说好**：若 F1 差值的 CI 包含 0 而 ColQwen 调用少了 85%~95%，"
             "那就是本项目最干净的成本结论；若 F1 显著下降，则 E36 的成本表述必须撤回，"
             "因为 recall 上的等价没有传导。",
     note="L-dump：一个实验若要给下游消费逐题决策，就必须**把决策本身落盘**，"
          "而不是只落盘推导决策所用的分数。只要两边的 tie-break 有一点不同，"
          "被升级的题集就会悄悄换掉，而任何指标都不会暴露这件事。"
          "另：开跑前先定死 thinking 开关（§5.3-12），配对比较中途改开关等于把已花的钱作废。",
     limits="未执行。执行前需要：(1) 预算批准；(2) 冻结 thinking 开关；"
            "(3) 确认用 canonical 池——它的检索单元就是官方 quote，F1 语义才与论文一致，"
            "自建池上「quote」是本项目发明的 chunk，F1 会悄悄变成另一个量。"),

dict(id="E31", phase="infra", status="fix",
     title="可复现运行系统：一条命令重算全部当前有效实验",
     asks="终端里出现过的数字，还能不能被找回、被复算、被 diff？",
     cmds=["{py} experiments.py run-suite replay --offline",
           "{py} experiments.py verify E24",
           "{py} -m tests.test_runner"],
     result="新增 expkit/ 六个模块（paths/results/artifacts/runner/report/verify/apilog）"
            "与四个套件（replay / retrieval / full-local / api）。每次运行落在 "
            "artifacts/runs/<run_id>/：完整 stdout+stderr、每实验 status.json、"
            "metrics.json、per_question.csv、manifest.json，以及 run 级 "
            "summary.{json,csv,md,html} 与 metrics.jsonl。"
            "首个 replay 运行 20260828T073440Z_replay 落盘 188 条指标，"
            "E24/E27/E28/E30 原生输出结构化结果，E1/E2/E3 如实标为「仅日志」。"
            "verify E24 的 22 项断言全过；tests/test_runner.py 44 项断言全过。",
     result2="同时修掉三个会静默出错的地方："
             "(1) eval_colqwen 的 `if eid not in eids: continue` 会在候选池缺 gold 时"
             "悄悄缩小分母——改为用全部视觉 gold 建分母、池外 gold 计 miss，"
             "覆盖率不足时默认 fail loudly，需 --allow-partial 才继续并打标；"
             "实测：抽掉 40 题的 ranking 后，旧口径仍会报 0.9294，新口径降到 0.9149。"
             "(2) colqwen_index 的 `except: pass` 改为写 colqwen_failed_images.jsonl 并汇报。"
             "(3) runner 从 shell=True 改为 argv + shell=False；E29 里的 Unix `cp` "
             "改用 make_eval_jsonl 的 --out。",
     superseded=("图片池覆盖率 46.8%；图片候选每篇文档中位 29",
                 "唯一图片覆盖率 46.34%（6,487/13,999）；按文档中位 20、均值 29.76，"
                 "按问题加权中位 29、均值 34.92。46.8% 是拿 6,548 条 evidence row 除以"
                 "13,999 张唯一图片得到的，单位不一致；6,504 则是全库 223 篇文档的 "
                 "distinct img_path，与 13,999 也不同口径。"),
     note="API 侧只用 mock provider 验证，本次没有发生任何真实调用、模型下载或索引重建。"
          "每个请求记录 request_hash（含实际展示的 quotes，因此换检索配置不会串用旧答案）、"
          "token usage、provider request id、错误与 rate-limit 详情；"
          "密钥经 redact() 过滤，且已断言 input_tokens/total_tokens 不被误删。"
          "价格一律作为 price_verified=false 的估计，只有 token 数是实测量。"),

dict(id="E33", phase="infra", status="fix",
     title="可追溯性与科学表述收尾：source bundle、E24 视觉分支命名、覆盖率数据模型",
     asks="source_manifest 说能还原源码——它真的还原得了吗？"
          "E24 那一行「隔离了两种表示」，隔离的到底是什么？",
     cmds=["{py} experiments.py run-suite replay --offline",
           "{py} experiments.py verify E24",
           "{py} experiments.py verify E27",
           "{py} -m tests.test_runner --scratch-root artifacts/test-runs",
           "{py} -m tests.test_source_bundle --scratch-root artifacts/test-runs"],
     result="source_manifest 此前声明 `git checkout <commit> && git apply "
            "source.patch` 可还原本次源码，实测**做不到**：`git diff HEAD` 只看得见"
            "已跟踪文件，而 25 个被指纹覆盖的源文件里有 **18 个从未提交**"
            "（experiments.py、整个 expkit/、retrieval/nested_cv.py、"
            "retrieval/ablation.py 等）。对基准 run 20260828T080756Z_replay 实测："
            "commit+patch 只还原 7/25，其余 18 个文件缺失。指纹能**发现**源码不同，"
            "却**产生不出**跑过的源码——这正好是源码记录一半的用处。"
            "现在每个 run 生成 source_bundle.zip：按原相对路径存放 manifest 中"
            "全部源文件的字节，tracked 与 untracked 一视同仁；manifest 记录 bundle "
            "路径、SHA-256、文件数与每个成员的路径/大小/哈希。"
            "bundle 只含源码——数据集、模型、向量、索引、API 日志、response "
            "与任何凭据形状的路径都被构造性排除并二次校验。"
            "run.json 与 summary 显示 fingerprint、bundle 路径与哈希、源文件数、"
            "重建命令与**重建测试状态**：每次 run 会在 artifacts/test-runs 下"
            "用 `git archive`（只读，绝不 checkout 脏工作区）→ `git apply` → "
            "解压 bundle 的顺序重建一棵树并重算全部哈希，结果直接写进 run.json。",
     result2="E24 的表述与覆盖率数据模型一并修正。"
             "(1) `RRF(描述) − ColQwen` 此前被写成「isolates the two "
             "representations」——不成立：这一步同时改了**表示**（原始像素 → "
             "VLM 文字描述）与**检索架构**（单个后交互检索器 → 两个检索器 RRF 融合），"
             "一个同时移动两个变量的对比无法把效应归给其中任何一个。"
             "现更名为 visual branch comparison，并写明它是完整的视觉分支比较、"
             "不是被隔离出来的表示效应。可支持的说法只有：在当前不完整的图片池中、"
             "紧预算 k=10 下，完整的 description-RRF 分支检索更好"
             "（+0.0269，CI 不跨 0；k=20 为 +0.0111，CI 跨 0）；"
             "**不能**说 VLM 文字表示优于像素表示。"
             "(2) 覆盖率不再硬编码 2000，全部由数据算出并分成两个总体："
             "全部问题 2000/2000，有视觉 gold 的问题 1995/1995，实际计分 1995；"
             "另外 5 题没有视觉 gold，因此视觉 Recall 对它们没有分母——"
             "这是总体的边界，不是被悄悄缩小的分母。"
             "(3) verify E24 从 22 项扩到读取指定 run 的 metrics：断言覆盖率的"
             "分子/分母/比值三者自洽、四类比较在 k=10/20 都在且都带 "
             "document-cluster CI、指标名未漂移、被禁表述未复活。",
     superseded=("source_manifest 声明 commit+patch 可还原本次源码；"
                 "E24 的 RRF(描述)−ColQwen「隔离了两种表示」；"
                 "「每篇文档中位 29 个图片候选，@20 等于取走 69% 的池」",
                 "commit+patch 只还原 7/25 个源文件，须叠加 source_bundle.zip；"
                 "该对比同时改变表示与架构，只能称为完整视觉分支比较；"
                 "按文档中位 20、均值 29.76，k=20 对 111/220 篇（50.5%）"
                 "等于取走整个池，29 与 69% 都只在按问题加权口径下成立。"),
     note="本轮没有调用任何真实 API、没有下载模型、没有重跑 OCR、"
          "没有重建向量/语料/ColQwen 索引，旧 run 全部保留。"),

dict(id="E32", phase="infra", status="fix",
     title="replay 完整性与可追溯性修复",
     asks="报告出来的四格结果，真的都是这一次跑出来的吗？跑它的源码还找得回来吗？",
     cmds=["{py} experiments.py run-suite replay --offline",
           "{py} experiments.py verify E24",
           "{py} experiments.py verify E27",
           "{py} -m tests.test_runner --scratch-root artifacts/test-runs"],
     result="E27 的 2x2 主结果矩阵此前只跑两格（自建 k=10、canonical k=20），"
            "另两格来自 result 文字。现在四格全部由 E27 执行，"
            "`verify E27` 的 61 项断言只读指定 run 的 metrics.json——"
            "缺任意一格 exit 1（已用旧 run 实测：pass 0 / FAIL 29 / exit 1）。"
            "E28 去掉与 E27 重复的 selfbuilt k=10，只保留审计实验。"
            "每个 run 新增 source_manifest.json：25 个源文件的 SHA-256、"
            "完整注册表快照、关键数据文件哈希、脱敏 git diff patch，"
            "以及 16 位 source fingerprint，summary 中显示。",
     result2="E24 增补三组配对 document-cluster bootstrap CI，并补了一个描述端"
             "融合臂——此前的 `rrf` 是 RRF(BM25描述, ColQwen)，它**包含** "
             "ColQwen，拿它减 ColQwen 只能测互补性。"
             "结果：ColQwen−BM25 与 ColQwen−BGE 在 k=10/20 上 CI 全部跨 0；"
             "描述端 RRF 分支 − ColQwen 在 k=10 为 +0.0269（显著）、"
             "k=20 为 +0.0111（跨 0）。"
             "【E33 更正】当时把这一项写成「隔离出两种表示」是错的，见 E33。"
             "E30 改为单命令 --all-cells，对 4 格×3 主效应共 12 个检验做 Holm 校正："
             "raw CI 12/12 不跨 0，Holm 后 **12/12 存活**（最大 p_holm=0.0165），"
             "raw CI 一并保留。视觉因子更名为 "
             "「visual branch: ColQwen over images -> BM25+BGE RRF over VLM descriptions」，"
             "因为它同时换了表示与检索器数量，不能简称为表示效应。",
     superseded=("E27 四格主结果（其中两格未在同一次运行中产生）；"
                 "E24 的 `rrf` 臂被当作「RRF over descriptions」",
                 "四格全部由 E27 在同一次 run 中产生并由 verify E27 从 metrics 断言；"
                 "描述端融合臂单列为 rrf_desc，原 `rrf` 更名为 RRF(BM25-text, ColQwen) "
                 "并注明它包含 ColQwen"),
     note="derived registry 增加 model name / revision / dtype / shape / normalization / "
          "input corpus hash / id order hash / 生成命令 / 软件版本；"
          "无法确认的字段写 unknown 并置 metadata_incomplete=true，不猜测——"
          "例如 legacy 向量的 model_revision 与 production-time corpus hash。"
          "实测 bge-small-vlm 为 float32 (25716,384)、已归一化（row norm 中位 1.0000）、3 行零向量。"
          "测试隔离：inference_api.py 增加 --dataset-dir/--response-dir，"
          "mock 不再写入正式 dataset/ 与 response/，此前遗留的三个测试文件已移入 "
          "artifacts/test-runs/legacy-mocktest/；tests 增加 --scratch-root 并断言两个正式目录未被污染。"
          "Git 策略见 docs/artifacts-git-policy.md：轻量 summary/manifest/metrics 入库，"
          "日志/逐题 CSV/向量/模型缓存/API 原始流量不入库，API 内容按敏感处理。"),

dict(id="E29", phase="2", status="pos",
     title="端到端：检索改进能否传导到生成质量",
     asks="k=10 上 +0.054 的检索优势，能否变成 quote-selection F1 的提升？",
     # `--out` writes straight into dataset/, so there is no copy step. The
     # earlier `cp` lines were Unix-only and could not run on this machine.
     cmds=["{py} -m retrieval.make_eval_jsonl --config paper --limit 600 --k 10 "
           "--out dataset/evaluation_paperk10.jsonl",
           "{py} -m retrieval.make_eval_jsonl --config ours  --limit 600 --k 10 "
           "--out dataset/evaluation_oursk10.jsonl",
           "{py} inference_api.py gemini-3.6-flash --setting paperk10 --mode pure-text --rpm 10",
           "{py} inference_api.py gemini-3.6-flash --setting oursk10  --mode pure-text --rpm 10",
           "{py} eval_all.py --model gemini-3.6-flash --setting paperk10 "
           "--mode pure-text --no-judge",
           "{py} eval_all.py --model gemini-3.6-flash --setting oursk10 "
           "--mode pure-text --no-judge",
           "{py} eval_e29_paired.py"],
     result="检索增益传导到了生成（2026-08-29）。600 题、两臂同模型同 prompt 同 gold，"
            "只有候选块不同：论文式配置（dense 文本 + ColQwen 视觉，配额 7/3）"
            "final_f1 = 55.21；本项目配置（RRF 文本 + RRF 视觉，配额 4/6，"
            "即 nested CV 在 E27 选出的那一组）final_f1 = 58.11。"
            "配对差 +2.90 F1，document-cluster 95% CI [+1.01, +4.77]，不跨 0，"
            "bootstrap p=0.0025（220 篇文档、600 题重采样）。"
            "逐题 210 胜 / 156 负 / 234 平。"
            "检索侧 k=10 的 +0.054 recall 优势因此不是纸面数字，它到达了答案质量。",
     result2="口径三条，缺一不可。(1) gemini-3.6-flash 不在论文模型表里，"
             "因此 55.21 / 58.11 这两个绝对值不可与论文任何一行比较，"
             "可解释的只有配对差。(2) 估计量必须与 eval_all 的 final_f1 一致"
             "（逐题 F1 的均值）；eval_e29_paired.py 在算任何区间之前先断言"
             "两臂均值复现 eval_all 打印的 55.2 / 58.1，不符就拒绝报告——"
             "围绕另一个量算出来的区间比没有区间更糟。(3) 重采样单位是文档而非问题，"
             "因为题嵌套在文档里。附带一个反直觉的观察：本数据上按题重采样的区间"
             "[+0.94,+4.99] 反而略宽于按文档的 [+1.01,+4.77]——聚类不必然放宽区间，"
             "用它的理由是单位匹配，不是它更保守。",
     note="配额实测：网上流传的「免费层 250 RPD」是旧模型的数字，当前模型是 20 RPD。"
          "可行路径只剩三条：(1) 付费 API，约 $1.5~2 的用量（最低充值通常 $5）；"
          "(2) 本地 Qwen2.5-7B——论文评过、发布 F1 45.8，但 8GB 卡需 4-bit 量化"
          "（就不再是发布的那个模型了）且依赖 ms-swift；"
          "(3) 放弃 E29，项目以检索侧结果交付——E27 已由 nested CV 确认，本身完整。"
          "本地 Qwen2.5-3B 虽可跑，但发布 F1 仅 25.0、文本引用 recall 10.7，"
          "太弱，会把要检测的信号压掉。"
          "生成模型不是复现锚点：gemini-2.0-flash 已下线（404），"
          "gemini-2.5-flash 对新 key 不可用，论文用过的 Gemini 模型全部调不到。"
          "改用 gemini-3.6-flash——它不在论文的模型表里，因此本实验的绝对 F1 "
          "不可与论文任何一行比较；但两臂用同一模型、同一批题，配对比较仍然有效。"
          "6 次调用的对照测试显示它比 gemini-3.1-flash-lite 引用更克制"
          "（flash-lite 过度引用会压低精确率）。见 `python experiments.py plan`。"),

dict(id="E34", phase="2", status="pos",
     title="论文式基线：bge-large 文本检索器与完整图片池的 ColQwen 量级核对",
     asks="本项目的「论文式对照」臂，与论文实际发布的系统差在哪几项？"
          "把差得最多的那一项补上之后，先前的提升还剩多少？",
     cmds=["{py} -m retrieval.fetch_model BAAI/bge-large-en-v1.5 --check",
           "{py} -m retrieval.dense --model models/bge-large-en-v1.5 "
           "--image-repr vlm",
           "{py} -m retrieval.dense_chunks --model models/bge-large-en-v1.5",
           ".venv-colpali/Scripts/python.exe -m retrieval.colqwen_index "
           "--image-source fulldisk --out retrieval/colqwen_scores_fullpool.sqlite",
           "{py} -m retrieval.eval_fullpool"],
     expensive=True,
     result="逐项核对见 docs/paper-baseline-audit.md。核对推翻了两条先前的表述："
            "(1) **论文没有给出任何检索器的版本或 HF id**，只写了族名（BGE、ColQwen）；"
            "先前把「bge-large-en-v1.5 与 ColQwen2-v0.1」说成论文配置是推断而非原文，"
            "因此换用 bge-large 只能说成「更接近论文规模的文本检索器」，"
            "不能说成「与论文版本一致」。"
            "(2) **视觉侧早已是真的**——models/colqwen2-v1.0 与 colqwen2-base 已在本地，"
            "colqwen_index.py 走 MaxSim 后交互直接读像素，先前「需要下载 ColQwen」不成立。"
            "真正的主要缺口是**图片池规模**：论文 63 图/篇，本项目此前 29.8 图/篇，"
            "即官方候选并集，且每一条都因为是某题的 gold 或 hard negative 才在池中——"
            "被问题条件化的池会让 recall 乐观偏置。磁盘上 220 篇 evaluation 文档共有 "
            "13,999 张图（63.6/篇），与论文吻合，全池索引因此可建。",
     result3="实测（两个池 × 两个 k，其余全部固定，document-cluster bootstrap B=4000）。"
            "**k=10 的头条提升没有被更强的基线吃掉，反而变大**："
            "G−E（最佳混合 vs 论文式）在 canonical 池 +0.0464* → +0.0453*，"
            "在 selfbuilt 池 +0.0473* → **+0.0605***；D−E 同向（+0.0371* → +0.0511*）。"
            "原因是对照臂 E 本身也用 dense 文本检索器，两臂一起变强，"
            "而 D/G 用的是 RRF(BM25,dense)，更强的 dense 让融合受益更多。"
            "唯一明显缩水的是 D−A（基线是纯 dense，升级只让基线单边变强）："
            "canonical 池 +0.0452* → +0.0256*。"
            "**同时必须撤回一条结论**：「ColQwen 读像素优于在 VLM 描述上做检索」"
            "此前在 k=20 的 CI 不含 0（E−A = +0.0220*），换 bge-large 后落到 "
            "+0.0086 [−0.0101,+0.0274] 且跨 0——它测的不是视觉表示的优势，"
            "是文本检索器太弱。k=20 的 G−E 与 D−E 在四个组合下全部跨 0，"
            "与 E27 早已记录的「只有 k=10 稳健」一致。",
     result2="扩池不能对两个分支同时做，这是本条目最要紧的设计判断。"
             "13,999 张图里**只有 5,056 张（36.1%）带 VLM 描述**——描述只存在于官方候选池。"
             "ColQwen 读像素，可覆盖全部 13,999；BM25/BGE 跑描述，只能覆盖 5,056。"
             "天真扩池等于让 ColQwen 面对 2.1 倍的干扰项、再把差距报成检索器效应，"
             "**方向与旧偏置相反，但同样是错的**。因此拆成两个互不替代的测量："
             "(A) eval_fullpool.py 只报 ColQwen 在全池上的绝对 recall，"
             "用于与论文 Table 6 的 ColQwen 图片列（70.8/79.2/84.3）核对量级；"
             "(B) eval_colqwen.py 继续锁在候选池上做公平配对比较，"
             "并在检测到 unpooled: 条目时**直接拒绝运行**而不是加个脚注。"
             "论文的 ColQwen **文本** recall 不可复现——论文从未说明视觉检索器如何排文本 quote，"
             "其配额句（top10 = 3 图 + 7 文）只对 hybrid 检索给出——故不做任何文本侧对照。",
     result4="**2026-09-01 全池索引已完成（220/220 篇，1995 题）。**"
            "论文值在三个 k 上全部落在区间之外——池规模不是唯一原因。"
            "同文档配对下补全池的降幅是 -0.0374 [-0.0509,-0.0265]（k=10），"
            "池规模解释了到论文值距离的 33%。"
            "**同文档配对对照是本次新增的**：原脚本把部分样本的全池数与全语料候选池数并排，"
            "两者相减同时混进池规模效应与文档抽样效应；现在用同一批问题、同一个 gold 分母把候选池也跑一遍，报配对区间。",
     limits="**当前限制**：全池索引已完成，但它只让 ColQwen 的**图片** recall 与论文可比。"
            "论文从未说明视觉检索器如何排文本 quote，其 text 列（28.5/33.7/36.0）不可复现，"
            "任何数字都不应与之并列。**仍然不能写「优于论文配置」**——"
            "可写的是「相对最接近论文的本地对照」，即配额、模态分工、检索器族名对齐，"
            "而版本与解析流水线不可确定；本次结果恰恰把这条纪律从告诫变成了实测："
            "池规模只解释了 33% 的差距，剩下的差异**无法从发表物里定位**。"
            "描述分支上全池仍未做，需为 8,943 张图补 VLM 描述，属付费项，未批准。"
            "\n\n**以下为已作废的历史记录，保留以说明这条结论是怎么来的，"
            "其中每一句「未验证 / 受阻」都已不再成立**："
            "**（历史）ColQwen 全池索引未完成：只索引了 5/220 篇文档**"
            "（2026-08-31 复核仍是 5/220，39 题、124 图，其中 96 条 "
            "unpooled；阻塞原因是 GPU 被用户自己的 Ollama 占用 "
            "6832/8188 MiB 且不能停，ColQwen2 的 4.49 GB 放不下。"
            "另发现 colqwen_scores_fullpool.ckpt 是空目录而非检查点文件，"
            "续跑粒度只到文档级，文档内被打断需整篇重跑），"
            "因此 eval_fullpool.py 尚无可报告的结果，"
            "「补齐池后 Recall@10 应从 0.820 降向论文的 0.708」这一预测当时未验证"
            "（**已于 2026-09-01 验证并证伪**：降了，但只降了三分之一）。"
            "受阻于资源而非正确性：ColQwen2 权重需 4.49 GB，"
            "而本机 8.19 GB 显存中 Ollama 的 llama-server.exe 持有 3.26 GB，"
            "余下的放不下大图激活；全量实测需 5–9 小时 GPU。"
            "机制已就绪且可无人值守续跑：--doc-order random 使任何停止点都是"
            "文档的简单随机样本，文档内检查点让 660 张图的文档也能跨窗口续跑，"
            "eval_fullpool 只在已索引文档上估计而不把未索引文档的 gold 计为 miss。"
            "即使全部完成也**不能**写「优于论文配置」。可写的是「相对最接近论文的本地对照」，"
            "即配额、模态分工、检索器族名对齐，而版本与解析流水线不可确定。"
            "若全池 recall 的 CI 覆盖论文值，只能声明**本地实现通过量级核查**，"
            "这是实现验证，不是复现论文系统。"
            "要让描述分支也上全池，需为 8,943 张图补 VLM 描述，属付费项，未批准。",
     note="bge-large 是本项目唯一**字节可证**的模型：retrieval/fetch_model.py 写下 "
          "models/bge-large-en-v1.5/fetch.json，含 revision "
          "d4aa6901d3a41ba39fb536a557fa166f842b0e09 与逐文件 SHA-256，"
          "`--check` 可随时重算。其余条目都只能报出模型名，无法证明加载了哪份权重。"),
]

# ---------------------------------------------------------------------------
# Structured metadata
# ---------------------------------------------------------------------------
# The prose entries above are the historical record and are not edited here.
# This table adds the machine-readable half: what a suite runner needs in order
# to decide whether an experiment may run, what it depends on, and how its
# result should be read. Keeping it separate means adding scheduling metadata
# never risks rewording a published conclusion.
#
#   lifecycle   active     current vintage; may be published from this run
#               superseded an older measurement kept for the record only
#               manual     verified by hand; nothing to execute
#               blocked    cannot run here (quota, missing dependency)
#   replay      indices into `cmds` that ONLY read existing artifacts.
#               An empty list means nothing in this experiment is replay-safe.
#   deps        artifact names from expkit.artifacts.DAG
#   sample_unit the unit a bootstrap must resample. `document` wherever
#               questions nest inside documents -- which is everywhere here.

_DEFAULT_META = dict(
    lifecycle="active", suites=(), replay=(), deps=(), requires_api=False,
    requires_gpu=False, expensive=False, expected_outputs=(),
    estimated_runtime=60, primary_metric="", sample_unit="document",
    how="", metric_meaning="", limits="",
)

CANON = "corpora/canonical-db"
QUOTES = "corpora/quotes-selfbuilt"
PAGES = "corpora/page-corpus"
BGE = "embeddings/bge-small-vlm"
BGEC = "embeddings/bge-small-chunks"
# E18 compares the VLM-description surrogate against the OCR one, so it reads
# these vectors -- but it declared only the canonical db, which left the suite
# planner unable to see that the OCR encode is a prerequisite.
BGEO = "embeddings/bge-small-ocr"
COLQ = "indexes/colqwen-rankings"

META = {
 "E1":  dict(suites=("replay",), replay=(0,), estimated_runtime=90,
             primary_metric="quote-selection F1", sample_unit="question",
             expected_outputs=("stdout metrics table",),
             how="用仓库内已发布的 response 文件重算官方 17 项指标，不调用任何模型。",
             metric_meaning="逐位命中论文公布的数字即代表本地评分口径与论文自洽。",
             limits="这是评测复算，不是完整实验复现；没有重跑检索器，也没有重新调用模型。"),
 "E2":  dict(suites=("replay",), replay=(0,), estimated_runtime=90,
             primary_metric="覆盖率报告", sample_unit="question",
             how="按 q_id join 替换 zip()，并显式打印共同样本数。",
             metric_meaning="覆盖率 < 100% 时必须报错或显式声明，而不是静默在少数样本上求均值。",
             limits="只能说明已发布 judge artifacts 无法构造同底比较，不能推断作者内部流程。"),
 "E3":  dict(suites=("replay",), replay=(0,), estimated_runtime=5,
             primary_metric="模块可导入", sample_unit="question",
             how="检查 manifest 模块存在且可导入。",
             metric_meaning="基础设施可用性检查，不产生实验数字。",
             limits="这是工程整改，不是方法贡献。"),
 "E4":  dict(suites=("full-local",), deps=(CANON,), expensive=True,
             estimated_runtime=600, primary_metric="gold 映射率",
             how="构建 canonical evidence 数据层，用 (doc,page,layout) 生成稳定证据身份。",
             metric_meaning="局部 quote 编号是位置不是身份；canonical ID 才能跨设置比较。",
             limits="不要把 answer_interleaved 里的局部编号当成跨设置固定的答案文本。"),
 "E5":  dict(suites=("full-local",), deps=(CANON,), expensive=True,
             estimated_runtime=600, primary_metric="Gate 1 映射率 21978/21978",
             how="构建五张表并做往返检查。",
             metric_meaning="100% 指官方两档候选可归一到统一证据层。",
             limits="100% 是官方处理结果之间的映射，不代表能映射到任意自建 chunk。"),
 "E6":  dict(suites=("full-local",), deps=(CANON, QUOTES), expensive=True,
             estimated_runtime=900, primary_metric="Gate 2 映射率 ~98.63%",
             how="字符 8-gram 覆盖替代精确子串匹配。",
             metric_meaning="重新切 chunk 后 gold 仍可评价的比例。",
             limits="未映射项必须计为 miss；阈值变化要做敏感性报告。"),
 "E7":  dict(suites=("full-local",), deps=(CANON,), expensive=True,
             estimated_runtime=5600, primary_metric="无文本页数",
             expected_outputs=("retrieval/pages.sqlite",),
             how="RapidOCR 扫描低文本页（<100 字符），与原文本层拼接。",
             metric_meaning="OCR 后仍无可用文本的页数，衡量文本索引的可达性。",
             limits="约 93 分钟。OCR 能找出文字，不等于理解图表关系。"),
 "E8":  dict(suites=("full-local",), deps=(BGE,), expensive=True,
             estimated_runtime=900, primary_metric="oracle 增益 vs 同族对照",
             sample_unit="question",
             how="计算逐题 oracle，并用两个同模态不同模型的系统做参照水平。",
             metric_meaning="oracle 增益必须减去同族对照才是真实可路由空间。",
             limits="oracle 仍可作上界，但必须配排列对照并使用 regret。"),
 "E9":  dict(suites=("retrieval", "full-local"), replay=(0, 1, 2),
             deps=(BGE,), estimated_runtime=600, primary_metric="test AUC / kappa",
             sample_unit="question",
             how="19 个模型的成对结果上训练轻量分类器，检查 AUC、kappa 与跨模型迁移。",
             metric_meaning="kappa≈0 表示不同模型对「这题该用哪种输入」几乎不一致。",
             limits="不能写成「该属性不存在」或「所有 Router 都不可能」。"),
 "E10": dict(suites=("retrieval", "full-local"), replay=(0,),
             estimated_runtime=120, primary_metric="tok / F1 点",
             sample_unit="question",
             how="比较同一模型 pure-text/multimodal 的 F1、token 与 Pareto 前沿。",
             metric_meaning="每换 1 分 F1 需要多付的输入 token，provider-neutral。",
             limits="Gemini 图片 token 未计入；美元价格未核验，跨供应商成本不可直接比。"),
 "E11": dict(suites=("retrieval", "full-local"), replay=(0,),
             estimated_runtime=300, primary_metric="探针一致性",
             sample_unit="question",
             how="修正 evidence 类型识别后重跑泄漏探针。",
             metric_meaning="原探针只识别 table，修正后覆盖全部视觉类型。",
             limits="这是 bug 修复，结论随之改变。"),
 "E12": dict(suites=("retrieval", "full-local"), replay=(0, 1),
             deps=(PAGES,), estimated_runtime=300,
             primary_metric="gold 不可达比例",
             how="在补 OCR 前后分别重算 gold 证据的文本可达性。",
             metric_meaning="补 OCR 后从 12.1% 降到 0.7%，原「结构性不可见」论据被消解。",
             limits="OCR 后文本可达不代表视觉关系已被正确理解。"),
 "E13": dict(suites=("retrieval", "full-local"), replay=(1,),
             deps=(PAGES,), expensive=True, estimated_runtime=240,
             primary_metric="页级 Recall@k",
             how="以整页为证据单元比较文本 gold 与视觉 gold 的召回。",
             metric_meaning="页粒度上两类 gold 差距很小，因为图与周围文字捆在一起。",
             limits="找到正确页不等于找到图中正确区域。"),
 "E14": dict(suites=("retrieval", "full-local"), replay=(0,),
             deps=(CANON,), estimated_runtime=180,
             primary_metric="quote 级 Recall@k",
             how="以细粒度 quote/region 为证据单元重做同一比较。",
             metric_meaning="模态效应是粒度依赖的：quote 级才显现交叉。",
             limits="报告任何模态结论都必须同时说明证据粒度。"),
 "E15": dict(suites=("retrieval", "full-local"), replay=(0,),
             deps=(CANON,), estimated_runtime=180,
             primary_metric="长度匹配后的覆盖率差",
             how="控制 quote 长度并分解文字/图片池规模的贡献。",
             metric_meaning="+0.080 的表观优势在长度匹配后翻转为 −0.014。",
             limits="池级分解是描述性诊断，不替代完整对照语料实验。"),
 "E16": dict(suites=("retrieval", "full-local"), replay=(1,),
             deps=(CANON, BGE), expensive=True, estimated_runtime=300,
             primary_metric="按 gold 类型的 Recall@k",
             how="同一候选池上按 gold 类型比较 BM25 与 BGE 的逐证据召回。",
             metric_meaning="符号随证据类型翻转，说明存在值得融合的词法—语义互补性。",
             limits="证据条目层 ±0.09 的效应聚合到整题会缩小。"),
 "E17": dict(suites=("retrieval", "full-local"), replay=(0, 1, 2),
             deps=(CANON, BGE), estimated_runtime=420,
             primary_metric="Router recall vs 固定 vs RRF",
             how="以逐题 recall(Dense)−recall(BM25) 为标签和权重重新训练路由器。",
             metric_meaning="对固定 +0.016（CI 跨 0），对静态 RRF −0.0279（CI 不跨 0）。",
             limits="旧 E17 用 gold 模态标签写死映射，只能否证那一条人工策略。"),
 "E18": dict(suites=("retrieval", "full-local"), replay=(1, 2),
             deps=(BGEO, CANON,), expensive=True, estimated_runtime=300,
             primary_metric="image gold Recall@20",
             how="同一图片池、同一 BM25 下比较 VLM 描述与裁剪 OCR 两种文字表示。",
             metric_meaning="0.791 对 0.369，差距在 OCR 成功提取的子集上仍为 +0.416。",
             limits="OCR 有大量空/不完整结果；不能把全部差距断言为「视觉理解」。"),
 "E19": dict(suites=("retrieval", "full-local"), replay=(0, 1, 2),
             deps=(CANON, BGE), estimated_runtime=360,
             primary_metric="tie-aware regret 上界",
             how="计算 21 种配额的逐题 Recall 曲线，审计并列最优，改用 oracle−best-fixed regret。",
             metric_meaning="真实 regret 上界 0.069/0.074；约 79% 问题固定配额已最优。",
             limits="原 +0.173~+0.179 受 argmax 恒取最小并列索引影响，已作废。"),
 "E20": dict(suites=("retrieval", "full-local"), replay=(1,),
             deps=(QUOTES, BGEC), expensive=True, estimated_runtime=300,
             primary_metric="配额结论方向一致性",
             how="重建更大的文本 chunk 池，保持同一 QA、gold 与图片侧重跑。",
             metric_meaning="方向一致说明结论对文本池规模有一定稳健性。",
             limits="不是独立复现；视觉池仍相同且不完整。"),
 "E21": dict(suites=("retrieval", "full-local"), replay=(0,),
             deps=(CANON, BGE), estimated_runtime=240,
             primary_metric="visual share 预测 R²",
             how="以 gold 视觉占比为目标训练回归并评价实际 Recall 增益。",
             metric_meaning="R² 提升不一定转化为检索收益。",
             limits="visual share 是 gold 派生的诊断目标，不等同于最优行动。"),
 "E22": dict(lifecycle="manual", suites=(), estimated_runtime=0,
             primary_metric="（人工核对）",
             how="人工核对，没有可执行命令。",
             metric_meaning="—",
             limits="不能被 run-suite 假装执行成功。"),
 "E23": dict(suites=("retrieval", "full-local"), replay=(0, 1),
             deps=(CANON, BGE, QUOTES), estimated_runtime=360,
             primary_metric="反射式配额的实际增益",
             how="用首轮检索结果反射式地重新分配配额，两个池分别跑。",
             metric_meaning="预测目标改善不一定转化为检索收益。",
             limits="输入信号弱、样本少且目标平坦。"),
 "E24": dict(suites=("replay", "retrieval", "full-local"), replay=(1,),
             deps=(CANON, BGE, COLQ), requires_gpu=True, expensive=True,
             estimated_runtime=180,
             primary_metric="image gold Recall@k（ColQwen vs 描述检索）",
             expected_outputs=("metrics.json", "per_question.csv"),
             how="在当前 evaluation 图片池上比较 ColQwen2 像素排序与 BM25/BGE/RRF 描述检索。"
                 "第 0 条命令重建 GPU 索引（约 62 分钟），replay 只跑第 1 条评价命令。",
             metric_meaning="视觉 gold 落入 top-k 的比例。注意「在完整 ranking 中」"
                            "不等于「进入 top-k」。",
             limits="池只覆盖 13,999 张原始图片中的 6,487 张（46.34% 唯一图片）；"
                    "按文档中位仅 20 个候选，k=20 已接近饱和。"
                    "这是公平的池内排序比较，不是完整文档图片池上的检索比较。"),
 "E25": dict(suites=("retrieval", "full-local"), replay=(1,),
             deps=(QUOTES,), expensive=True, estimated_runtime=900,
             primary_metric="固定 top-k vs 固定预算下的 Recall",
             how="按 target-chars 建多档语料，分别在固定 top-k 与固定 word-like 预算下比较。",
             metric_meaning="固定 top-k 会把粗 chunk 携带的额外上下文当成免费收益。",
             limits="预算单位是正则 word-like token，不是 LLM BPE；仅覆盖文本 gold 与 BM25。"),
 "E26": dict(suites=("retrieval", "full-local"), replay=(0, 1),
             deps=(QUOTES,), estimated_runtime=600,
             primary_metric="small-to-big vs 纯臂的 Recall",
             how="比较 prefix-stop 与 greedy-skip 两种预算装填规则。",
             metric_meaning="早期正增益约一半来自「遇到塞不下就停止」的量化损失。",
             limits="仅覆盖特定档位、BM25 与文本证据，不能封闭整个 RQ3。"),
 "E27": dict(suites=("replay", "retrieval", "full-local"),
             replay=(1, 2, 3, 4, 5, 6),
             deps=(CANON, QUOTES, BGE, BGEC, COLQ), expensive=True,
             estimated_runtime=240,
             primary_metric="Evidence Recall@k",
             expected_outputs=("metrics.json", "per_question.csv", "manifest.json"),
             how="文本与图片描述分支内分别 RRF(BM25,BGE-small)，再采用较均衡配额，"
                 "与本地论文式对照（dense 文本 + ColQwen 视觉 + 官方配额）比较。",
             metric_meaning="每题被找回的 gold evidence 比例；未映射 gold 计为 miss。",
             limits="单切分结果为 exploratory；泛化性只由 E28 的 nested CV 支持。"),
 "E28": dict(suites=("replay", "retrieval", "full-local"), replay=(0, 1),
             deps=(CANON, QUOTES, BGE, BGEC), estimated_runtime=120,
             primary_metric="OOF Evidence Recall@k",
             expected_outputs=("metrics.json", "per_question.csv"),
             how="document-grouped 外层 CV，内层在训练折上重选检索器与配额，"
                 "每题由未参与其配置选择的折评分。",
             metric_meaning="无脚本内选择泄漏的 Recall；仍是 internal OOF，不是外部确认。",
             limits="并非严格双层 inner-CV；方法空间此前已用同一 2,000 题开发，"
                    "k=20 时各折选择不稳定。"),
 "E30": dict(suites=("replay", "retrieval", "full-local"), replay=(0,),
             deps=(CANON, QUOTES, BGE, BGEC, COLQ), estimated_runtime=120,
             primary_metric="主效应（配额 / 图片描述检索 / RRF 文本融合）",
             expected_outputs=("metrics.json", "per_question.csv", "manifest.json"),
             how="每格 2×2×2 因子设计，四格（两池 × 两预算）一次跑完，"
                 "按文档 cluster bootstrap 求主效应，并对 4×3=12 个主效应做 Holm 校正。",
             metric_meaning="每个主效应是该因子单独翻转、另两因子取遍所有水平的平均配对差。"
                            "raw 95% CI 与 Holm 校正后的 p 同时给出，校正不隐藏任何东西。",
             limits="这是**内部组件归因**，不是外部泛化验证：固定配置、单一 benchmark、"
                    "且该 benchmark 已被本项目用于挑选方法。"
                    "视觉因子同时换了表示（像素→VLM 文字）与检索器数量（单模型→双模型融合），"
                    "因此必须整条命名为 visual branch，不能简称为表示效应。"),
 "E40": dict(suites=("retrieval", "full-local"), lifecycle="active",
             # all four commands only READ artifacts -- nested_cv builds
             # nothing -- so every one of them is replay-safe.
             replay=(0, 1, 2, 3),
             deps=(CANON, QUOTES, "embeddings/bge-large-vlm", COLQ),
             estimated_runtime=240, primary_metric="Recall@k（折外）",
             sample_unit="document",
             expected_outputs=("metrics.json",),
             how="与 E27 完全相同的 document-grouped 5 折折外协议，"
                 "只把 dense 文本臂换成 models/bge-large-en-v1.5。"),
 "E37": dict(suites=("retrieval", "full-local"), lifecycle="active",
             deps=(CANON, QUOTES, BGE, BGEC, COLQ), estimated_runtime=240,
             primary_metric="折外选择 − 论文式基线 E 的 Recall@k，按切片",
             sample_unit="document",
             expected_outputs=("metrics.json", "per_question.csv"),
             how="复用 nested_cv 的折外选择（文档分组 5 折，全语料选一次），"
                 "再把已算好的折外差值向量按三种划分切片："
                 "证据模态、gold 跨页与否、语料自带的 question_type。"
                 "每个切片按文档 cluster bootstrap 求区间；"
                 "16 个切片检验为一个 Holm 家族，4 个对照检验为另一个。",
             metric_meaning="切片检验回答「这一类里提升还在不在」；"
                            "对照检验回答「提升是否依赖这一类」——"
                            "后者才是异质性问题，前者两格的显著性差异不能替代它。",
             limits="exploratory。pure text 在该 split 只有 1 题、"
                    "unanswerable 为 0 题，proposal 的五类切片有两类无法评价。"),
 "E38": dict(suites=("retrieval", "full-local"), lifecycle="active",
             deps=(CANON, QUOTES), estimated_runtime=120,
             primary_metric="给定 R² 下配额分配相对最优固定切分的 Recall@20 增益",
             sample_unit="document",
             expected_outputs=("metrics.json",),
             how="复用 reflect_alloc 的两段式召回矩阵与真实 visual_share。"
                 "对每个目标 R² 用二分法反解噪声标准差（按裁剪后的实测 R²），"
                 "共同随机数生成 200 组预测，收缩系数在测试集上取最优，"
                 "再按文档 cluster bootstrap 给区间。",
             metric_meaning="每一行是「精度达到该 R² 的预测器最好能买到多少」，"
                            "是上界不是预报：合成预测器无偏、误差与真值独立，"
                            "且收缩系数在测试集上选。",
             limits="exploratory。只覆盖配额分配决策，不外推到 E36 的升级决策。"),
 "E39": dict(suites=(), lifecycle="blocked", requires_api=True, expensive=True,
             deps=(CANON, QUOTES, COLQ), estimated_runtime=0,
             primary_metric="quote-selection F1，配对差值",
             sample_unit="document",
             expected_outputs=(),
             how="照 E29 的配对协议，两臂只有候选块不同；"
                 "路由臂消费 budget_router 落盘的 escalate_at_B* 列。",
             metric_meaning="主张是成本而不是质量：期望看到 F1 差值的 CI 包含 0 "
                            "而 ColQwen 调用大幅下降。",
             limits="未执行，等待预算批准。"),
 "E35": dict(suites=("retrieval", "full-local"), lifecycle="active",
             deps=(CANON, QUOTES, BGE, BGEC, COLQ), estimated_runtime=180,
             primary_metric="oracle / 最优固定 / 置换对照 的 Recall@k",
             sample_unit="document",
             expected_outputs=("router/cache/actions_<pool>_<model>.pkl",
                               "metrics.json", "per_question.csv"),
             how="router.actions 复用 eval_stack_v2.build（keep_scores=True）"
                 "缓存逐题的 12 个动作 × recall × 成本；"
                 "router.tie_audit 在每个预算子空间上报最优固定动作、"
                 "tie-aware oracle、保配比的置换对照，"
                 "并按文档 cluster bootstrap 给区间。",
             metric_meaning="oracle 与最优固定动作之差是表观空间；"
                            "与置换对照之差扣掉了动作配比带来的部分；"
                            "约束下界取两者中更强的那个。"
                            "预算是 (cpu pass, gpu pass) 一对上限，两种货币不相加。",
             limits="exploratory 切分；配额固定；"
                    "ColQwen 的 gpu pass 是对预建索引的打分，"
                    "一次性建索引与 4.49 GB 常驻权重是部署成本，"
                    "不能被任何逐题预算摊销掉。"),
 # Not in any suite, for the same reason as E34: a fresh run is ~40 minutes
 # because the in-fold feature-group search fits five model families on
 # five candidate groups inside every one of 40 folds. Per-cell results
 # are checkpointed, so a rerun resumes; a suite that carried it would
 # still pay the full cost the first time. Run it directly.
 # E36 was reachable only by typing its four commands out of `show E36`, which
 # made a published negative result the one thing `run-suite` could not recheck.
 # It is local CPU work with the same deps as E37, so it belongs in full-local;
 # `expensive` keeps a 40-minute job behind --include-expensive rather than in
 # the default path.
 "E36": dict(suites=("full-local",), lifecycle="active", expensive=True,
             deps=(CANON, QUOTES, BGE, BGEC, COLQ), estimated_runtime=2400,
             primary_metric="同预算下 路由器 − 随机分配 的 Recall@k",
             sample_unit="document",
             expected_outputs=("router/cache/cells/*.json", "metrics.json",
                               "per_question.csv"),
             how="折外预测（文档分组 5 折，折内再 4 折选模型族，"
                 "--features search 时连特征组一起在折内选）；"
                 "按预测增益排序买升级；对照是同预算的随机分配"
                 "（逐题期望精确计算而非抽样）、同预算 oracle、两个端点；"
                 "8 格一个 Holm 家族。每格结果落盘可续跑。",
             metric_meaning="主指标不是「比不升级好」——升级本身就多做检索。"
                            "唯一能证明路由器懂 query 的是它在**同样预算**下"
                            "胜过随机挑哪些 query 升级。"
                            "capture = (路由器 AUC − 随机 AUC) / (oracle AUC − 随机 AUC)。",
             limits="exploratory 切分；oracle regret 仍大；"
                    "「追平静态系统的预算」是读曲线得到的描述性数字；"
                    "未接到端到端生成质量。"
                    "特征组事先固定与折内选择两种口径结论强度不同，必须都报。"),

 # deliberately in NO suite: its first command IS `run-suite replay`, so a
 # suite that contained it would invoke itself. Run it directly with
 # `python experiments.py run E31` -- the nested suite excludes E31 and
 # therefore terminates.
 "E31": dict(suites=(), lifecycle="active", replay=(1, 2),
             estimated_runtime=180, primary_metric="断言通过数",
             sample_unit="question",
             expected_outputs=("artifacts/runs/<run_id>/summary.md",
                               "artifacts/verify/E24_latest.json"),
             how="run-suite 跑套件并落盘；verify E24 断言 22 项池口径；"
                 "tests/test_runner.py 断言失败处理、断点续跑与产物复用决策。",
             metric_meaning="全部断言必须通过；任何一项 FAIL 都意味着某个已发布"
                            "数字的口径或某条日志路径已经失效。",
             limits="API 路径只用 mock 验证过，真实 provider 的错误形态可能不同。"),
 # Like E31, deliberately in no suite: its first command is `run-suite replay`.
 "E32": dict(suites=(), lifecycle="active", replay=(1, 2, 3),
             estimated_runtime=300, primary_metric="断言通过数",
             sample_unit="question",
             expected_outputs=("artifacts/runs/<run_id>/source_manifest.json",
                               "artifacts/verify/E27_latest.json"),
             how="四格 E27 由同一次 run 产生；verify E27 只读该 run 的 metrics；"
                 "source_manifest 把 run 绑定到源码哈希与注册表快照。",
             metric_meaning="verify E27 61 项、verify E24 22 项、tests 49 项全部必须通过。",
             limits="source fingerprint 覆盖被调用的模块与注册表，不覆盖第三方依赖的"
                    "字节内容（只记版本号）。"),
 # Same reason as E31/E32: its first command is `run-suite replay`.
 "E33": dict(suites=(), lifecycle="active", replay=(1, 2, 3),
             estimated_runtime=420, primary_metric="断言通过数",
             sample_unit="question",
             expected_outputs=("artifacts/runs/<run_id>/source_bundle.zip",
                               "artifacts/runs/<run_id>/source_manifest.json",
                               "artifacts/verify/E24_latest.json"),
             how="run 写出 source_bundle.zip 并当场从 commit+patch+bundle 重建"
                 "一棵树、重算全部源文件哈希；verify E24 在数据库口径之外"
                 "再读该 run 的 metrics，断言覆盖率三元组自洽与四类比较齐全。",
             metric_meaning="重建测试必须 25/25 逐字节命中；任何一个文件缺失或被"
                            "改动都会让 `python -m expkit.source reconstruct` exit 1。",
             limits="bundle 覆盖 source_manifest 列出的源文件，不含第三方依赖的"
                    "字节内容（只记版本号），也不含数据集与模型——"
                    "完整复现仍需要本地的 canonical DB、向量与 ColQwen 排名。"),
 "E29": dict(lifecycle="active", suites=("api",), requires_api=True,
             deps=(CANON, BGE, COLQ), estimated_runtime=3600,
             primary_metric="quote-selection F1", sample_unit="document",
             expected_outputs=("response/gemini-3.6-flash_pure-text_quotes*k10_response.jsonl",
                               "artifacts/runs/<run_id>/experiments/E29/metrics.json"),
             how="把两种检索配置的 top-k 写成官方 schema，用同一模型同一批题配对生成；"
                 "eval_e29_paired.py 复用 eval_all 的 extract_citations/get_scores "
                 "算逐题 F1，按文档聚类做配对 bootstrap（B=4000）。",
             metric_meaning="未检索到的 gold 用哨兵 id 计入分母，因此 F1 对检索质量敏感。"
                            "主结果是配对差 +2.90 F1，CI [+1.01,+4.77] 不跨 0；"
                            "两个绝对值本身不可与论文比较。",
             limits="BLEU/ROUGE 在此无效不可报告。gemini-3.6-flash 不在论文模型表里，"
             "因此绝对 F1 不可与论文任何一行比较；有效的只有两臂的配对比较。"
             "成本口径：2026-08-29 已对照官方定价页核验并写入 router/prices.json"
             "（标准付费层 $0.75/Mtok 输入、$3.75/Mtok 输出，verified=true）。"
             "此前曾用 gemini-2.0-flash 的未核验价 $0.10/$0.40 代算，"
             "输入低估 7.5 倍、输出低估 9.4 倍——价格表里没有该模型时，"
             "正确做法是不报美元，而不是拿最像的一条顶上。"),
 "E34": dict(lifecycle="active", suites=(), requires_gpu=True, expensive=True,
             deps=(CANON, QUOTES, "embeddings/bge-large-vlm",
                   "indexes/colqwen-fullpool"),
             estimated_runtime=9000, primary_metric="Recall@k（图片 gold）",
             sample_unit="document",
             expected_outputs=("models/bge-large-en-v1.5/fetch.json",
                               "retrieval/embeddings/bge-large-en-v1.5_*.npz",
                               "retrieval/colqwen_scores_fullpool.sqlite",
                               "artifacts/runs/<run_id>/experiments/E34/metrics.json"),
             how="fetch_model 把 bge-large 落成平铺目录并记下 revision 与逐文件 "
                 "SHA-256；colqwen_index --image-source fulldisk 改从磁盘枚举"
                 "文档的全部图片（13,999，63.6/篇）而非官方候选并集（6,548，29.8/篇），"
                 "已在池中的图保留原 evidence_id，池外的记为 unpooled: 前缀；"
                 "eval_fullpool 只算 ColQwen 的绝对图片 recall，按文档聚类 bootstrap。",
             metric_meaning="核对的是**量级**而非数值相等。候选池上本项目测得 "
                            "Recall@10=0.820，论文为 0.708，差距的自然解释是池小一半；"
                            "把池补到论文规模后该数应当**下降**并逼近 0.708。"
                            "CI 覆盖论文值只说明本地实现通过量级核查，"
                            "不说明复现了论文系统。",
             limits="论文未给出任何检索器的版本，解析流水线也未发布，"
                    "因此与论文的绝对数值对齐永远不可达。"
                    "论文的 ColQwen 文本 recall 不可复现（论文未说明视觉检索器"
                    "如何排文本 quote），不做任何文本侧对照。"
                    "全池索引**只可**用于 ColQwen 单臂绝对值："
                    "13,999 张图里仅 5,056 张带 VLM 描述，"
                    "描述侧检索器无法表示其余 63.9%，"
                    "同池比较会单方面惩罚 ColQwen——eval_colqwen 因此对 "
                    "unpooled: 条目直接 exit 1。"),
}

for _e in E:
    _m = dict(_DEFAULT_META)
    _m.update(META.get(_e["id"], {}))
    for _k, _v in _m.items():
        _e.setdefault(_k, _v)
    # argv arrays are the executable form: shell=False, no cmd.exe quoting.
    _e["argv"] = [shlex.split(_c, posix=True) for _c in _e["cmds"]]

BY_ID = {e["id"]: e for e in E}
STATUS_LABEL = {"pass": "通过", "neg": "负结果", "pos": "正向", "fix": "修复",
                "correct": "已修正", "pending": "待运行"}
LIFECYCLE_LABEL = {"active": "有效", "superseded": "已被取代",
                   "manual": "人工核对", "blocked": "受阻"}

SUITES = {
    "replay": dict(
        label="只重算指标，不重建任何产物",
        desc="复用现有数据库、向量、排名与 response 文件。不联网、不调 API、"
             "不做 OCR、不重建 ColQwen 索引。这是推荐的一键复现命令。",
        replay_only=True, allow_expensive=False, allow_api=False),
    "retrieval": dict(
        label="当前有效的检索实验与审计",
        desc="E9–E28 与 E30 中当前口径的评价命令，复用已有向量与排名。"
             "superseded 的旧口径不会作为当前结果重新发布。",
        replay_only=True, allow_expensive=False, allow_api=False),
    "full-local": dict(
        label="可重建 OCR / chunk / 向量 / 索引",
        desc="包含昂贵的构建步骤。必须显式传入 --include-expensive。支持断点续跑："
             "已存在且哈希一致的产物会被复用。",
        replay_only=False, allow_expensive=True, allow_api=False),
    "api": dict(
        label="真正调用外部 API 的实验",
        desc="默认禁止。必须显式传入 --allow-api。调用前会打印模型、题数、"
             "预计请求数与已完成数，并写出计划文件。",
        replay_only=False, allow_expensive=True, allow_api=True),
}


def suite_members(suite):
    return [e for e in E if suite in (e.get("suites") or ())]


def fmt(cmd):
    return cmd.format(py="python")


def _gate(e, suite, cfg, include_expensive, allow_api, registry):
    """Decide run / skip for one experiment. Returns (indices, state, reason).

    A gate that lets something through when it should not is worse than one that
    is too strict: the cost of a wrong skip is a missing row in the summary, the
    cost of a wrong run is an unintended API charge or an overwritten artifact.
    """
    if e.get("lifecycle") == "manual" or not e["cmds"]:
        return None, "manual", "没有可执行命令（人工核对）"
    if e.get("lifecycle") == "superseded":
        return None, "skipped", "已被取代的口径，不作为当前结果重新发布"
    if e.get("requires_api") and not allow_api:
        return None, "blocked", ("需要外部 API；未传 --allow-api" if not allow_api
                                 else "")
    if e.get("lifecycle") == "blocked" and not allow_api:
        return None, "blocked", "受阻：" + (e.get("note", "").split("。")[0] or "见 show")

    # dependency check -- a missing input is a skip with a named cause, never a
    # crash halfway through a suite
    missing = []
    for dep in e.get("deps") or ():
        state, target = registry.status(dep)
        if state == "missing":
            missing.append(dep)
    if missing:
        return None, "skipped", "缺少依赖产物：" + "、".join(missing)

    if cfg["replay_only"]:
        idx = list(e.get("replay") or ())
        if not idx:
            return None, "skipped", "本实验没有 replay 安全的命令（其命令会重建产物）"
        return idx, "run", ""

    if e.get("expensive") and not include_expensive:
        return None, "skipped", "昂贵步骤；未传 --include-expensive"
    return list(range(len(e["cmds"]))), "run", ""


def cmd_list():
    ap = argparse.ArgumentParser(prog="experiments.py list")
    ap.add_argument("--status", choices=sorted(STATUS_LABEL))
    ap.add_argument("--phase")
    ap.add_argument("--suite", choices=sorted(SUITES))
    ap.add_argument("--lifecycle", choices=sorted(LIFECYCLE_LABEL))
    a = ap.parse_args(sys.argv[2:])
    print(f"{'id':<5}{'phase':<8}{'status':<9}{'生命周期':<11}{'套件':<29}title")
    print("-" * 112)
    for e in E:
        if a.status and e["status"] != a.status:
            continue
        if a.phase and e["phase"] != a.phase:
            continue
        if a.suite and a.suite not in (e.get("suites") or ()):
            continue
        if a.lifecycle and e.get("lifecycle") != a.lifecycle:
            continue
        mark = " !" if e.get("superseded") else "  "
        flags = "".join(c for c, on in (("A", e.get("requires_api")),
                                        ("G", e.get("requires_gpu")),
                                        ("$", e.get("expensive"))) if on)
        suites = ",".join(e.get("suites") or ()) or "—"
        print(f"{e['id']:<5}{e['phase']:<8}{STATUS_LABEL[e['status']]:<9}"
              f"{LIFECYCLE_LABEL.get(e.get('lifecycle'), ''):<11}"
              f"{suites:<29}{e['title']}{mark}{' [' + flags + ']' if flags else ''}")
    print("-" * 112)
    print("! = 含已被取代的数字（`corrections`）  A = 需要 API  G = 需要 GPU  $ = 昂贵")
    print(f"记录簿 {NOTEBOOK}")
    print(f"审计   {AUDIT}")


def cmd_show():
    if len(sys.argv) < 3:
        raise SystemExit("usage: experiments.py show E27")
    e = BY_ID.get(sys.argv[2].upper())
    if not e:
        raise SystemExit(f"unknown id: {sys.argv[2]}")
    print("=" * 78)
    print(f"{e['id']}  [{STATUS_LABEL[e['status']]}]  {e['title']}")
    print("=" * 78)
    print(f"phase       : {e['phase']}")
    print(f"生命周期    : {LIFECYCLE_LABEL.get(e.get('lifecycle'), '')}")
    print(f"套件        : {', '.join(e.get('suites') or ()) or '—'}")
    print(f"主指标      : {e.get('primary_metric') or '—'}")
    print(f"统计单位    : {e.get('sample_unit')}（bootstrap 按此重采样）")
    flags = [n for n, on in (("需要 API", e.get("requires_api")),
                             ("需要 GPU", e.get("requires_gpu")),
                             ("昂贵", e.get("expensive"))) if on]
    print(f"标记        : {', '.join(flags) or '无'}"
          f"　预计耗时 ~{e.get('estimated_runtime')}s")
    if e.get("deps"):
        print(f"依赖产物    : {', '.join(e['deps'])}")
    if e.get("expected_outputs"):
        print(f"预期产出    : {', '.join(e['expected_outputs'])}")
    print(f"\n问的是      : {e['asks']}")
    if e.get("how"):
        print(f"怎么做      : {e['how']}")
    if e.get("metric_meaning"):
        print(f"指标含义    : {e['metric_meaning']}")
    print(f"\n当前结论    : {e['result']}")
    # Every resultN beyond the first is printed. An earlier version stopped at
    # result2, so E34's and E36's result3 -- both load-bearing paragraphs --
    # sat in the registry and were never shown by `show`. A field that is
    # written but never rendered is worse than a missing one: it reads as
    # recorded while being invisible, which is how the status-key defect in
    # section 5.5 of the handoff survived two whole experiments.
    for _n in range(2, 10):
        _k = f"result{_n}"
        if e.get(_k):
            _label = "补充" if _n == 2 else f"补充{_n - 1}"
            print(f"\n{_label:<12}: {e[_k]}")
    if e.get("superseded"):
        old, new = e["superseded"]
        print(f"\n已取代的表述:\n  旧 · {old}\n  新 · {new}")
    if e.get("limits"):
        print(f"\n限制        : {e['limits']}")
    if e.get("note"):
        print(f"\n注意        : {e['note']}")
    if e["cmds"]:
        print("\n复现命令:")
        replay = set(e.get("replay") or ())
        for i, c in enumerate(e["cmds"]):
            tag = "  [replay 安全]" if i in replay else "  [会重建产物]"
            print(f"  {fmt(c)}{tag}")
    else:
        print("\n复现命令: 无（人工核对）")


def cmd_run():
    ap = argparse.ArgumentParser(prog="experiments.py run")
    ap.add_argument("id")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--offline", action="store_true",
                    help="pin all model caches into the project and forbid downloads")
    ap.add_argument("--artifact-root", default=None)
    ap.add_argument("--replay-only", action="store_true",
                    help="run only the commands that read existing artifacts")
    a = ap.parse_args(sys.argv[2:])
    e = BY_ID.get(a.id.upper())
    if not e:
        raise SystemExit(f"unknown id: {a.id}")
    if not e["cmds"]:
        raise SystemExit(f"{e['id']} has no runnable commands (manual verification)")
    if e.get("requires_api"):
        raise SystemExit(
            f"{e['id']} calls an external API and is not runnable through `run`. "
            f"Use: python experiments.py run-suite api --allow-api")

    from expkit import paths as P, runner, report, artifacts as A

    P.ensure_dirs(a.artifact_root)
    env = P.enforce_offline(a.artifact_root) if a.offline else P.online_env()
    run_id = P.new_run_id(e["id"].lower())
    os.environ["MMDOCRAG_RUN_ID"] = run_id
    idx = list(e.get("replay") or ()) if a.replay_only else None

    print(f"run_id {run_id}   offline={bool(a.offline)}")
    st = runner.run_experiment(e, run_id, cmd_indices=idx, dry_run=a.dry_run,
                               env_overlay=env, artifact_root=a.artifact_root)
    _finish_run(run_id, [e["id"]], {"suite": f"single:{e['id']}",
                                    "offline": bool(a.offline),
                                    "allow_api": False, "dry_run": a.dry_run},
                a.artifact_root,
                argv_lists=[e["argv"][i] for i in (idx or range(len(e["argv"])))])
    if st["status"] == "error":
        raise SystemExit(1)


def _git_info():
    import manifest as _m
    try:
        return _m.git_state()
    except Exception:
        return {}


def _reconstruction_test(run_id, artifact_root=None, skip=False):
    """Restore this run's source into artifacts/test-runs and re-hash it.

    Isolated by construction: `git archive` never touches the working tree (a
    `git checkout` here would destroy months of uncommitted work), and the tree
    is written under artifacts/test-runs, which is git-ignored and separate from
    both the project files and the run record.
    """
    from expkit import paths as P, source
    if skip:
        return {"status": "skipped", "why": "--no-reconstruct-test"}
    man = source.load(run_id, artifact_root)
    if not man:
        return {"status": "FAIL", "why": "no source_manifest.json"}
    dest = os.path.join(P.artifact_root(artifact_root), "test-runs",
                        f"{run_id}-reconstruct", "tree")
    try:
        steps = source.restore(man, dest)
        rows = source.verify_tree(man, dest)
    except Exception as exc:                       # never let this kill a run
        return {"status": "FAIL", "why": f"{type(exc).__name__}: {exc}"}
    n_pass = sum(1 for r in rows if r["status"] == "pass")
    n_fail = sum(1 for r in rows if r["status"] in ("FAIL", "MISSING"))
    ok = n_fail == 0 and n_pass
    tree_bytes = sum(os.path.getsize(os.path.join(d, f))
                     for d, _sub, fs in os.walk(dest) for f in fs)
    # The tree is scaffolding: the result of the test is the hash table above,
    # which goes into run.json and survives. A passing tree is a byte-identical
    # copy of files that are already on disk and already in the bundle, so
    # keeping one per run bought nothing and cost ~1 GB each. On failure it is
    # the only place to see which bytes diverged, so a failing tree stays.
    kept = bool(not ok)
    if not kept:
        shutil.rmtree(dest, ignore_errors=True)
        parent = os.path.dirname(dest)
        if os.path.isdir(parent) and not os.listdir(parent):
            os.rmdir(parent)
    return {
        "status": "pass" if ok else "FAIL",
        "n_pass": n_pass, "n_total": len(rows), "n_fail": n_fail,
        "tree": P.rel(dest),
        "tree_kept": kept,
        "tree_bytes": tree_bytes,
        "tree_note": ("kept for inspection because the test failed" if kept else
                      "removed after verification; the hash table in this "
                      "record is the evidence. Regenerate with: python -m "
                      f"expkit.source reconstruct --run {run_id} --into <dir>"),
        "steps": steps,
        "failures": [r["path"] for r in rows if r["status"] != "pass"],
        "protocol": "git archive <commit> -> git apply source.patch -> "
                    "unzip source_bundle.zip -> sha256 every manifest file",
    }


def _finish_run(run_id, exp_ids, run_meta, artifact_root=None, extra=None,
                argv_lists=(), skip_reconstruct=False):
    """Write run.json, source_manifest.json and the four summary files.

    Numbers come from metrics.json; the source fingerprint comes from hashing
    the code that produced them. `git dirty: true` plus a list of filenames is
    not enough to say what ran, so the fingerprint is what a reader compares.
    """
    from expkit import paths as P, report, source

    rdir = P.run_dir(run_id, artifact_root)
    os.makedirs(rdir, exist_ok=True)
    meta = dict(run_meta)
    meta.update({
        "run_id": run_id,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": sys.executable,
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "cwd": REPO,
        "artifact_root": P.artifact_root(artifact_root),
        "experiments": list(exp_ids),
        "git": _git_info(),
    })
    if extra:
        meta.update(extra)
    src, src_path = source.write(run_id, registry=E, argv_lists=argv_lists,
                                 artifact_root=artifact_root)
    meta["source_fingerprint"] = src["fingerprint"]
    meta["source_manifest"] = src_path
    meta["source_patch"] = src["git"].get("patch")
    meta["n_source_files"] = src["n_source_files"]
    b = src.get("source_bundle") or {}
    meta["source_bundle"] = b.get("path")
    meta["source_bundle_sha256"] = b.get("sha256")
    meta["source_bundle_files"] = b.get("n_files")
    meta["source_bundle_bytes"] = b.get("bytes")
    meta["reconstruct_command"] = f"python -m expkit.source reconstruct --run {run_id}"
    meta["reconstruction_protocol"] = b.get("reconstruction")
    # A run that merely *claims* its source can be restored has not shown it.
    # Rebuild the tree from commit + patch + bundle in an isolated directory and
    # re-hash every fingerprinted file, then stamp the outcome into run.json --
    # so the record and its proof ship together instead of the proof living in a
    # test somebody may or may not have run.
    meta["reconstruction_test"] = _reconstruction_test(run_id, artifact_root,
                                                       skip=skip_reconstruct)

    from expkit.results import atomic_json
    atomic_json(os.path.join(rdir, "run.json"), meta)

    entries = report.collect(run_id, BY_ID, artifact_root)
    paths_out = report.write_all(run_id, entries, meta, artifact_root)
    P.write_latest(run_id, artifact_root)

    print()
    print("=" * 88)
    print(f"RUN {run_id}")
    print("=" * 88)
    counts = {}
    for e in entries:
        counts[e["state"]] = counts.get(e["state"], 0) + 1
    print(f"{'id':<6}{'状态':<16}{'耗时':>9}  {'指标数':>6}  说明")
    print("-" * 88)
    for e in entries:
        n_m = sum(len(b.get("metrics", [])) for b in e["metrics"])
        label = report.STATE_LABEL.get(e["state"], e["state"])
        print(f"{e['id']:<6}{label:<16}{e['elapsed_sec']:>8.1f}s  {n_m:>6}  "
              f"{e.get('reason', '')[:44]}")
    print("-" * 88)
    print("  ".join(f"{report.STATE_LABEL.get(k, k)}={v}"
                    for k, v in sorted(counts.items())))
    print()
    print(f"  source fingerprint  {src['fingerprint']}   "
          f"({src['n_source_files']} files, {src['n_registry_entries']} registry entries)")
    print(f"                      {src['n_source_files_tracked_by_git']} tracked by git, "
          f"{src['n_source_files_untracked']} untracked "
          f"-- the patch alone restores only the tracked ones")
    print(f"  source bundle       {b.get('path')}")
    print(f"                      sha256 {b.get('sha256')}")
    print(f"                      {b.get('n_files')} files, {b.get('bytes')} bytes")
    rt = meta["reconstruction_test"]
    print(f"  reconstruction test {rt['status']}  "
          f"{rt.get('n_pass', 0)}/{rt.get('n_total', 0)} files byte-exact"
          + (f"  ({rt.get('why')})" if rt.get("why") else ""))
    print(f"  reconstruct with    python -m expkit.source reconstruct --run {run_id}")
    print()
    for k, v in paths_out.items():
        print(f"  {k:<14} {v}")
    print(f"  {'source':<14} {src_path}")
    if src["git"].get("patch"):
        print(f"  {'patch':<14} {src['git']['patch']}")
    print(f"  {'run.json':<14} {P.rel(os.path.join(rdir, 'run.json'))}")
    print(f"  {'latest':<14} {P.rel(os.path.join(P.runs_root(artifact_root), 'latest.json'))}")
    return paths_out


def cmd_run_suite():
    ap = argparse.ArgumentParser(prog="experiments.py run-suite")
    ap.add_argument("suite", choices=sorted(SUITES))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--include-expensive", action="store_true")
    ap.add_argument("--no-reconstruct-test", action="store_true",
                    help="skip rebuilding the source tree from the bundle. The "
                         "run then records reconstruction_test=skipped rather "
                         "than silently claiming a proof it did not perform.")
    ap.add_argument("--allow-api", action="store_true")
    ap.add_argument("--fail-fast", action="store_true")
    ap.add_argument("--only", default="", help="comma-separated ids to restrict to")
    ap.add_argument("--artifact-root", default=None)
    ap.add_argument("--force-rebuild", action="append", default=[],
                    help="artifact name to rebuild even if present (repeatable)")
    ap.add_argument("--timeout", type=int, default=0,
                    help="per-command timeout in seconds (0 = none)")
    a = ap.parse_args(sys.argv[2:])
    cfg = SUITES[a.suite]

    from expkit import paths as P, runner, artifacts as A

    P.ensure_dirs(a.artifact_root)
    reg = A.Registry(a.artifact_root)
    adopted = reg.adopt_legacy()

    if cfg["allow_api"] and not a.allow_api:
        raise SystemExit(
            f"suite '{a.suite}' calls external APIs. Re-run with --allow-api "
            f"once you have read `python experiments.py plan`. Nothing was run.")
    if a.allow_api and not cfg["allow_api"]:
        print(f"[note] --allow-api has no effect on suite '{a.suite}' "
              f"(it contains no API experiments); nothing will be called.")

    env = P.enforce_offline(a.artifact_root) if a.offline else P.online_env()
    only = {s.strip().upper() for s in a.only.split(",") if s.strip()}
    members = [e for e in suite_members(a.suite) if not only or e["id"] in only]

    run_id = P.new_run_id(a.suite)
    os.environ["MMDOCRAG_RUN_ID"] = run_id

    # dependency plan, printed before anything runs
    dep_names = sorted({d for e in members for d in (e.get("deps") or ())})
    dep_plan = A.plan(dep_names, reg, a.force_rebuild) if dep_names else []

    print("=" * 92)
    print(f"SUITE {a.suite}  ——  {cfg['label']}")
    print("=" * 92)
    print(cfg["desc"])
    print()
    print(f"run_id            {run_id}")
    print(f"artifact root     {P.artifact_root(a.artifact_root)}")
    print(f"offline           {bool(a.offline)}"
          + ("  （模型缓存已指向项目内，禁止下载）" if a.offline else ""))
    print(f"include-expensive {bool(a.include_expensive)}")
    print(f"allow-api         {bool(a.allow_api)}")
    print(f"dry-run           {bool(a.dry_run)}")
    print(f"fail-fast         {bool(a.fail_fast)}")
    if adopted:
        print(f"legacy artifacts  " + ", ".join(f"{n} ({s})" for n, s in adopted))
    if dep_plan:
        print()
        print(f"{'依赖产物':<30}{'状态':<14}{'决定':<10}原因")
        print("-" * 92)
        for d in dep_plan:
            print(f"{d['artifact']:<30}{d['state']:<14}{d['decision']:<10}{d['reason'][:40]}")
        print("-" * 92)
        exp = [d for d in dep_plan if d["expensive"] and d["decision"] == "rebuild"]
        if exp:
            print(f"[!] {len(exp)} 个昂贵产物需要重建："
                  + "、".join(d["artifact"] for d in exp))
            print("    GPU/CPU 需求见 expkit/artifacts.py 的 DAG 表。")

    print()
    print(f"{'id':<6}{'决定':<10}原因")
    print("-" * 92)
    gated = []
    for e in members:
        idx, state, reason = _gate(e, a.suite, cfg, a.include_expensive,
                                   a.allow_api, reg)
        gated.append((e, idx, state, reason))
        n = len(idx) if idx else 0
        print(f"{e['id']:<6}{state:<10}{reason or f'{n} 条命令'}")
    print("-" * 92)
    n_run = sum(1 for _, _, s, _ in gated if s == "run")
    print(f"将执行 {n_run} 个实验，跳过 {len(gated) - n_run} 个")

    if a.dry_run:
        print()
        print("DRY RUN —— 下面是将要执行的确切 argv，没有任何命令被运行：")
        for e, idx, state, reason in gated:
            if state != "run":
                continue
            for i in idx:
                argv = [x.replace("{py}", "python") for x in e["argv"][i]]
                print(f"  {e['id']}#{i}  {' '.join(argv)}")
        print()
        print("加 --offline 可把模型缓存钉在项目内。去掉 --dry-run 真正运行。")
        return

    for e, idx, state, reason in gated:
        if state != "run":
            runner.skip_experiment(e, run_id, state, reason, a.artifact_root)
            continue
        print()
        print("=" * 92)
        print(f"{e['id']}  {e['title']}")
        print("=" * 92)
        st = runner.run_experiment(e, run_id, cmd_indices=idx, dry_run=False,
                                   env_overlay=env, artifact_root=a.artifact_root,
                                   timeout=a.timeout or None)
        if st["status"] == "error" and a.fail_fast:
            print(f"\n[fail-fast] {e['id']} 失败，停止后续实验。"
                  f"已完成的结果保留在 {P.rel(P.run_dir(run_id, a.artifact_root))}")
            break

    ran_argv = [e["argv"][i] for e, idx, st, _ in gated if st == "run"
                for i in (idx or ())]
    _finish_run(run_id, [e["id"] for e in members],
                {"suite": a.suite, "offline": bool(a.offline),
                 "allow_api": bool(a.allow_api),
                 "include_expensive": bool(a.include_expensive),
                 "fail_fast": bool(a.fail_fast), "dry_run": False},
                a.artifact_root,
                extra={"dependency_plan": dep_plan,
                       "legacy_adopted": [{"name": n, "action": s} for n, s in adopted]},
                argv_lists=ran_argv,
                skip_reconstruct=bool(a.no_reconstruct_test))


def cmd_verify():
    ap = argparse.ArgumentParser(prog="experiments.py verify")
    ap.add_argument("id")
    ap.add_argument("--artifact-root", default=None)
    ap.add_argument("--run", default=None,
                    help="run_id whose metrics to verify (default: latest). "
                         "Only used by checks that read a run, e.g. E27.")
    a = ap.parse_args(sys.argv[2:])
    from expkit import verify, paths as P
    P.ensure_dirs(a.artifact_root)
    _payload, n_fail = verify.run(a.id, artifact_root=a.artifact_root,
                                  run_id=a.run)
    if n_fail:
        raise SystemExit(1)


def cmd_report():
    ap = argparse.ArgumentParser(prog="experiments.py report")
    ap.add_argument("run_id", nargs="?", default="latest")
    ap.add_argument("--artifact-root", default=None)
    ap.add_argument("--regenerate", action="store_true",
                    help="rebuild summary.* from the run's metrics files")
    a = ap.parse_args(sys.argv[2:])
    from expkit import paths as P, report
    run_id = P.resolve_run(a.run_id, a.artifact_root)
    rdir = P.run_dir(run_id, a.artifact_root)
    if not os.path.isdir(rdir):
        raise SystemExit(f"no such run: {run_id}")
    with open(os.path.join(rdir, "run.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    entries = report.collect(run_id, BY_ID, a.artifact_root)
    if a.regenerate:
        report.write_all(run_id, entries, meta, a.artifact_root)

    print("=" * 92)
    print(f"RUN {run_id}   suite={meta.get('suite')}   offline={meta.get('offline')}")
    print("=" * 92)
    print(f"commit {meta.get('git', {}).get('commit')}  dirty={meta.get('git', {}).get('dirty')}")
    print(f"created {meta.get('created_utc')}")
    print()
    print(f"{'id':<6}{'状态':<16}{'耗时':>9}{'指标':>7}  主指标")
    print("-" * 92)
    for e in entries:
        n_m = sum(len(b.get("metrics", [])) for b in e["metrics"])
        print(f"{e['id']:<6}{report.STATE_LABEL.get(e['state'], e['state']):<16}"
              f"{e['elapsed_sec']:>8.1f}s{n_m:>7}  {e.get('primary_metric', '')[:40]}")
    print("-" * 92)
    for f in ("summary.md", "summary.html", "summary.csv", "metrics.jsonl"):
        p = os.path.join(rdir, f)
        if os.path.exists(p):
            print(f"  {f:<15} {P.rel(p)}  ({os.path.getsize(p)} bytes)")


def cmd_artifacts():
    ap = argparse.ArgumentParser(prog="experiments.py artifacts")
    ap.add_argument("--artifact-root", default=None)
    ap.add_argument("--adopt", action="store_true",
                    help="register pre-existing artifacts in place")
    a = ap.parse_args(sys.argv[2:])
    from expkit import artifacts as A, paths as P
    P.ensure_dirs(a.artifact_root)
    reg = A.Registry(a.artifact_root)
    if a.adopt:
        for n, s in reg.adopt_legacy():
            print(f"  {n:<32}{s}")
    print(f"{'artifact':<32}{'state':<14}{'expensive':<11}path")
    print("-" * 100)
    for name in sorted(set(list(A.DAG) + list(reg.entries))):
        state, target = reg.status(name)
        exp = A.DAG.get(name, ([], None, "", False))[3]
        print(f"{name:<32}{state:<14}{'yes' if exp else 'no':<11}"
              f"{P.rel(target) if target else '—'}")
    print("-" * 100)
    print("state: present=已注册且哈希一致  unregistered=文件在但未登记  "
          "stale=哈希变了  missing=不存在")


def cmd_corrections():
    print("已发布后被修正或撤回的表述。旧数字保留，不删除。\n")
    for e in E:
        if not e.get("superseded"):
            continue
        old, new = e["superseded"]
        print("=" * 78)
        print(f"{e['id']}  {e['title']}")
        print(f"  旧 · {old}")
        print(f"  新 · {new}")
    print("=" * 78)
    print(f"\n完整审计报告: {AUDIT}")


def cmd_plan():
    print("""
E29 · 端到端运行计划（待执行）
==============================================================================
问题   k=10 上 +0.054 的检索优势，能否变成 quote-selection F1 的提升？

设计   池     canonical——它的检索单元就是官方 quote，所以 F1 的语义与论文完全一致。
              自建池上「quote」是我们发明的 chunk，F1 会悄悄变成另一个量。
       预算   k=10——检索差距在这里最大（+0.054，是 k=20 的两倍），最有机会看到传导。
       对比   E（论文式：dense 文本 + ColQwen 视觉，7/3） vs D（RRF/RRF，4/6），配对同题。
       分母   未检索到的 gold 用哨兵 id 写进 gold_quotes，模型引不到，必然记为 false
              negative。只列检索到的 gold 会让 F1 对检索质量免疫，必然得到 null。
       judge  不需要。主指标 quote-selection F1 是本地从引用算的。

⚠ BLEU / ROUGE 在此无效，不可报告：参考答案内嵌官方局部编号，而我们重新编了号。

样本量 已冻结 600 题（manifests/e29_subset.json），按文档轮转排序，任何前缀都是
       文档分层的。试点用前 100 题，其调用在扩量时不浪费。
       100 题只够验证管道：该子集上连检索差距都不显著（+0.034，CI [−0.024,+0.092]）。
       600 是算出来的：文档聚类 CI 半宽约 0.0144*sqrt(2000/n)，效应 +0.054，需 n>~555。

配额   gemini-2.0-flash 免费层 250 次/天、10 RPM。
       试点 200 次 → 一天内。 600 题 × 2 = 1,200 次 → 约 5 天。
       gemini-2.0-flash-lite 是 1,000 次/天（约 1.5 天），但它不是本项目的复现锚点模型，
       若使用必须在报告中注明。
       inference_api.py 的 --resume 默认开启：撞到日配额后次日重跑同一命令即可续上。

步骤   export GEMINI_API_KEY=...
       python experiments.py run E29
       扩到 600 题：把上面命令里的 --limit 100 改成 --limit 600，重新 cp，再跑一次
       inference（resume 会跳过已完成的 100 题）。

跑完   把两个 response 文件给我，我做配对的 document-cluster 检验并落盘。
==============================================================================
""".strip())


COMMANDS = {
    "list": cmd_list, "show": cmd_show, "run": cmd_run,
    "run-suite": cmd_run_suite, "verify": cmd_verify, "report": cmd_report,
    "artifacts": cmd_artifacts, "corrections": cmd_corrections, "plan": cmd_plan,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        return
    fn = COMMANDS.get(sys.argv[1])
    if fn is None:
        print(f"unknown command: {sys.argv[1]}")
        print()
        print(__doc__)
        raise SystemExit(2)
    fn()


if __name__ == "__main__":
    main()
