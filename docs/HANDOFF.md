# MMDocRAG 项目交接

> 写于 2026-08-30，2026-09-01 大幅更新（E37/E38、统计机器测试、全池索引解除阻塞）。
> 给下一个会话（或换回来的我自己）直接接手用。
> **先读这份，再读 `docs/lab-notebook.html`。** 前者是地图，后者是每个实验的完整叙述。
> 可执行的权威记录是 `experiments.py`——每条实验都带着产出它数字的确切命令。

---

## 0. 三十秒版本

课程项目（UTS 32933 Research Project, Spring 2026, Type I 原型研究），
proposal 标题是 *Hierarchical Query-Conditioned Routing for Efficient and
Faithful Multimodal Document RAG*。

**已经建成一条完整的因果链，每一环都有区间和口径：**

```
canonical 数据层
   → 检索配置改进        E27  nested CV 四格全显著
   → 组件归因            E30  Holm 校正后 12/12 存活
   → 答案质量            E29  +2.90 F1，CI [+1.01,+4.77]，p=0.0025
   → 基线加强后仍成立     E34  换 bge-large 后 k=10 提升不降反升
```

**proposal 标题承诺的「逐题路由」已经做完（E35/E36），但它交付的是成本结论而不是质量结论。**

```
E35 天花板   一半 CPU 预算下完美选择 − 静态 RRF = +0.040 ~ +0.052（四格全显著）
             同预算最优固定动作 − 静态 RRF     = −0.016 ~ −0.022
             → 路由器要补的缺口 ≈ 该预算内 oracle 空间的三成
E36 实测     以下为「特征组事先固定」的口径，折内选特征组的口径另列，两者不可混
             CPU 融合决策  够不到（同预算相对随机 0/4 存活 Holm，capture −0.9%~8.6%）
             GPU 升级决策  够到一部分（3/4 存活 Holm，capture 10.2%~11.8%；
                           特征组改为折内选择时降到 1/4 存活，四格点估计仍全为正）
             → 路由器的 recall 曲线追平静态系统所需的预算是 B=0.05~0.15，
               即 ColQwen 只在 5%~15% 的题上跑，CPU 遍历相应多付 2%~7%
               （两种货币不相加，只能这样并列写）。
               **这个交点是从曲线上读出来的，本身不是一次检验**——
               没有做过等价性检验，被检验的是上面那一行（相对同预算随机分配）
```

于是项目有**两条并列且不可互相顶替**的表述：静态配置的改进是**质量**结论
（E27 → E29 端到端 +2.90 F1）；逐题路由的结果是**成本**结论。两条都是 exploratory。

**2026-09-01 新增两条，都是回答 proposal 自己提的问题：**

```
E37 切片   E27 的提升在题型上稳健（k=10 八格全部存活 Holm，两个池都是），
           但异质性显著：纯视觉题 +0.104，跨模态题 +0.035，
           对照 −0.069 [−0.097,−0.042]，Holm p=0.0010 —— 它主要是视觉召回的提升。
           proposal Experiment 2 要的五类里，pure text 只有 1 题、
           unanswerable 一题都没有，**两类在这个 benchmark 上无法评价**。
E38 天花板 proposal 给 RQ1b 设的 R² 目标问错了。把 R² 推到 1.0（完美预测），
           配额分配也只买到 +0.023（canonical）/ +0.028（selfbuilt），
           而 E23 已经拿到的 0.136 处是 +0.009 / +0.012。
           → 三个未试特征源最多在争夺 +0.014 recall，其中 LLM 充分性判断
             正是 CRAG 的机制，CRAG 实测该机制自身要付 41% 时延。**用数字关掉的方向。**
```

---

## 1. 环境与硬约束

| 项 | 值 |
|---|---|
| 代码 | `D:\Playground\MMDocRAG` |
| 数据 | `D:\Dataset\MMDocRAG`（图片在 `images\images\`，注意是两层） |
| proposal | `E:\Courses\2026 Spring 32933 Research Project\Research_Project_Proposal.docx` |
| GPU | RTX 4060 Laptop **8 GB**——ColQwen2 权重就占 4.49 GB |
| 磁盘 | D 盘常年只剩几十 GB，且与 Ollama 模型、其他工程共享 |
| Python | 3.13.7，torch 2.6.0+cu124 |
| 第二个 venv | `.venv-colpali`（colpali-engine 要 transformers≥5，主环境锁在 4.57.3） |
| HF 缓存 | `D:\AI\HuggingFace`（`HF_HOME` 已设） |

**跑不了**：`inference_checkpoint.py`（7B+ 推理）、`train_swift_qwen.py`（ms-swift 微调）。
**生成侧走 API**（Gemini 付费层），检索与 router 侧本地跑。

### 会话执行模型（吃过大亏，务必先读）

- **后台任务活不过回合边界。** 观察到被杀的间隔从 9 分钟到 48 分钟不等，
  且我的回合一结束就必被杀。
- **前台 Bash 单次最长 600 秒。**
- 结论：**任何超过 8 分钟的任务都必须自带检查点并可续跑**，然后用多次前台调用推进。
  没有检查点的长任务在这个环境里等于必然全损——本会话为此损失过 2h13m + 33min。

---

## 2. 已完成（E1–E36）

完整叙述见 `docs/lab-notebook.html`。这里只给状态与最要紧的数字。

### 数据层（E1–E7）
- **E1** 复现锚点：`gemini-2.0-flash` C20 multimodal 全 17 项指标与论文逐位一致。
- **E4** 关键结构发现：quote 的局部编号（`text5`/`image7`）**不是全局 ID**，
  同题 gold 在 15 档/20 档下局部 ID 仅 4.6% 相同、canonical 身份 100% 相同。
  `q_id` 也不是主键（dev/eval 各自从 0 编号），主键必须是 `(split, q_id)`。
- **E5** Gate 1：21,978 条 gold **100%** 可映射到 `(doc,page,layout)`。
- **E6** Gate 2：自建 chunk 能匹配回官方 gold text 的比例 **98.63%**。
  精确子串只能到 82%（MinerU 会往 gold 里塞幻觉字形），**必须用字符 8-gram 重叠**。
- **E7** 全语料 OCR：14,763 页，补 OCR 后无文本页从 1,748 降到 357。

### 生成输入层的模态路由（E8–E12）—— **负结果，已结案**
- **E9**：证据已给定时，逐题选「真图喂 VLM」还是「文字描述喂 LLM」**不可预测**。
  决定性证据是**跨模型 Cohen's kappa 均值 0.038，171 个模型对中 0/171 超过 0.2**。
- **E8** 是必须带走的方法学纪律：**per-question oracle 增益大 ≠ 有可路由的空间**。
  选两个含噪声测量的较大者本身就产生正增益。**任何 adaptive 工作报 oracle 上界时都要跑对照。**
- **E10** 正面产出：模态选择的成本-质量表。多模态在大多数模型上不值得买，
  13 个 token 可信模型里 **6 个被纯文本严格支配**。
- **E12**：我自己跑的 OCR **消解了我自己的立论**（「28~30 篇文档对文本检索完全不可见」
  在补 OCR 后变成 0 篇）。立论方式因此从「结构性」改为「实证性」。

### 检索层（E13–E27, E30）
- **E14** 模态信号是**粒度依赖**的：页粒度上文本检索对视觉 gold 没有劣势
  （R@10 差 +0.015），quote 粒度上才出现论文 Table 6 的双向交叉。
- **E15**：「图片 quote 更好检索」**不是**可路由信号，是**池组成的产物**
  （k≥10 处贡献几乎全部来自池大小）。
- **E19/E23** 两次自我推翻：oracle 上界被高估；高维特征一直在埋掉低维真信号。
- **E27 主结果**：nested CV 选出的配置相对最接近论文的本地对照，
  k=10 为 **+0.061 / +0.054**（两个池），k=20 为 +0.030 / +0.027，四格全显著。
  选出的配额是 **{10:(4,6), 15:(7,8), 20:(9,11)}**——注意**不是**通用的 5/5。
- **E30** 归因消融：Holm 校正后 12/12 比较存活。

### 逐题路由（E35–E36）—— **一半正向，且是成本而非质量**
- **E35 先做天花板，不先写 router**（这是 §4① 当时定下的顺序，照做了）。
  12 个动作（文本检索器 3 × 图片侧 4），固定配额，两种货币分开记：
  `cpu_passes`（对分支候选池的单检索器遍历，RRF 记 2）与 `gpu_passes`（ColQwen 后交互）。
  **本项目没有测过两者的兑换率，所以预算是一对上限而不是一个标量。**
- **tie 与配比这两种高估被分别量化**：97.5% 的题有多个最优动作，
  **47.9% 的题 12 个动作完全同分**（33.4% 全对、1.9% 全错），
  最优固定动作对 77.0% 的题已经最优。E19 式 argmax 破 tie 让表观空间虚高 +0.009~+0.013。
- **约束下界这次是最优固定动作，不是置换对照**（0.7101 vs 0.6844），
  与 E19 方向相反 —— 说明 oracle 的优势确实是逐题的，不是动作配比带来的。
- **E36 主对照是同预算下的随机分配**，不是「比不升级好」。八格一个 Holm 家族。
  GPU 级联 3/4 存活（特征组事先固定时），CPU 级联 0/4。
- **把特征组也放进折内选择后只剩 1/8 存活**，GPU 四格点估计仍全为正。
  原因是内层目标在 1,200~1,600 样本上选不稳特征组（40 个 fold 换了 5 种组合，
  6 次选中含句向量的组）。**两种口径都必须报。**
- **Policy A（检索前就选检索器）是干净的负结果**：四种特征组全部输给折内最优固定动作，
  与 E17 一致。

### 按题型切片（E37）—— **正向，且是稳健性证据**
- **主结论是稳健性**：k=10 上八个切片全部存活 Holm（16 个切片检验一个家族），
  两个池独立复现。增益不是某一类问题撑起来的。
- **异质性只在模态轴上，且必须用对照检验判**：「一格显著、另一格不显著」不是差异的检验。
  `cross-modal − pure visual` 在 k=10 为 **−0.0691** [−0.0967,−0.0420]
  （canonical 池 −0.0798），两池 Holm p=0.0010。**纯视觉题的提升约为跨模态题的三倍。**
  机制自洽：选出的配额把视觉槽位从论文式的 3 提到 6。
- 这个异质性**到 k=20 就消失**，与 E25/E26 的预算量化损失一致。
  **跨页轴四个对照 CI 全部跨 0**——这条提升与跨页推理无关。
- **proposal Experiment 2 的五类只剩三类可评**：pure text 在 evaluation split
  只有 **1 题**，unanswerable **0 题**（每题都带 gold）。这是 benchmark 的属性，
  写报告时必须照此说明，不能假装跑了五类。
- 一致性检查：纯视觉题的 +0.1037 在两个池上**逐位相同**——两池只在文本侧不同，
  而纯视觉题的 gold 全在图片侧，本来就不该变。

### RQ1b 的 R² 目标（E38）—— **负结果，结案性**
- 对每个目标 R² 造无偏合成预测器 `p = v + N(0,σ²)`，收缩系数在测试集上选，
  两项都刻意取最乐观 → 每一行都是**天花板不是预报**。
- **从「几乎无信息」到「完美」，全程只有 +0.007 → +0.023 recall。**
  E23 已达到的 0.136 处是 +0.009 / +0.012；推到完美**只多 +0.014**。
- 两个决策刻度（两池一致）：天花板意义下区间不跨 0 需 R²≈0.14；
  拿到真值分配一半的收益需 R²≈0.30。从 0.136 推到 0.30 只值 +0.002~+0.003。
- 两处实现细节必须踩对，否则结论会被自己的构造污染：
  1. **闭式解 σ²=(1−R²)Var(v) 在这里是错的。** visual_share 大量堆在 0 和 1，
     裁剪到 [0,1] 消掉大部分注入误差，名义目标 0 的实测 R² 落在 **0.29**——
     会把 E23 的 0.136 悄悄放到曲线三分之二高处。必须对**实测** R² 二分反解 σ。
  2. **各目标点要用共同随机数。** 独立抽噪声时每点 ±0.001 的蒙特卡洛噪声
     足以让曲线非单调，诱使读出并不存在的次序。

### 端到端（E29）—— **正向**
600 题配对生成，两臂同模型、同 prompt、同 gold，只有候选块不同：

| 臂 | 配置 | final_f1 |
|---|---|---|
| paper | dense 文本 + ColQwen 视觉，配额 7/3 | 55.21 |
| ours | RRF 文本 + RRF 视觉，配额 **4/6** | **58.11** |

**Δ = +2.90 F1，document-cluster 95% CI [+1.01, +4.77]，p = 0.0025**，
220 篇文档 / 600 题，210 胜 / 156 负 / 234 平。增益几乎全在图片侧（img_f1 +5.0）。
实际花费 **12.09 AUD / 1,225 次调用**。

### 论文式基线（E34）—— **正向，但有一半未完成**
- **核对推翻两条我自己的说法**：论文**没有给出任何检索器的版本**（Table 6 只列族名）；
  ColQwen2-v1.0 **早已在本地且真跑像素**，从来不需要下载。
- 真正的主缺口是**图片池规模**：论文 63 图/篇，此前只有 29.8（官方候选并集，
  被问题条件化 → recall 乐观偏置）。
- **k=10 的头条提升没被更强基线吃掉，反而变大**：
  G−E 在 selfbuilt 池 +0.0473\* → **+0.0605\***。
  机制：对照臂自己也用 dense 检索器，两臂一起变强；而我方用 RRF，融合受益更多。
- **必须撤回一条**：「ColQwen 读像素优于图片描述检索」在 k=20 的显著性
  （+0.0220\* → +0.0086，跨 0）**是文本检索器太弱造成的**。
- **未完成**：ColQwen 全池索引只做了 **5/220 篇**，见 §4。

---

## 3. 基础设施（E31–E33）

### 可复现运行系统 `expkit/`
```bash
python experiments.py list                    # 一行一个实验
python experiments.py show E27                # 详情、命令、限制
python experiments.py run-suite replay --offline
python experiments.py verify E24 --run <replay_run_id>   # 断言有争议的数字
# 注意 --run：verify 默认取 latest，而 latest 常常是刚跑过的单个实验。
python experiments.py report latest
python experiments.py corrections             # 每一个被推翻的旧数字
```
每次 run 写到 `artifacts/runs/<run_id>/`：完整 stdout/stderr、每个实验的
`status.json`、机器可读 metrics、per-question CSV、四种 summary。**不覆盖任何旧 run。**

### source bundle（E33）
`source_manifest.json` 只能**判定**源码是否相同，**产生不出**源码——
`git diff HEAD` 只看得见已跟踪文件，而 25 个被指纹覆盖的源文件里 **18 个从未提交**。
实测 `commit + patch` 只还原 7/25。所以每个 run 额外写 `source_bundle.zip`
（tracked + untracked 一视同仁），并当场重建一棵树重算全部哈希，结果写进 `run.json`。

**重建树是中间物，不是证据**——通过即删（`tree_kept: false`），失败才保留。
这条是被 36.6 GB 的教训换来的，见 §5。

### 测试
```bash
python -m tests.test_runner --scratch-root artifacts/test-runs     # 64 项
python -m tests.test_source_bundle --scratch-root artifacts/test-runs  # 21 项
python -m tests.test_phase3                                        # 33 项
python -m tests.test_statistics                                    # 25 项
```
**当前全绿（2026-09-01 二次复核，行尾缺陷彻底修好之后）：runner 64/0、
source_bundle 21/0、phase3 33/0、statistics 25/0，
verify E24 68/0、E27 61/0（**必须带 `--run <replay_run_id>`**），
`run-suite replay --offline` 全链复算通过，E29 端到端复现 +2.90 / p=0.0025。**

`verify` 默认对 `latest` run 取数，而 latest 常常是刚跑过的某个单实验。
对着那样的 run 跑 `verify E27` 会打出 29 行 FAIL/MISSING，
**读起来与「头条结果崩了」一模一样**，而数据其实完好。
已加一条守卫：该 run 里没有 E27 的块时，第一行直接说明是哪个 run、
并提示改传 `--run`，而不是把 29 个检查全部报成失败。
见 §5.4-44。

其中 `source_bundle` 一度是 **20/1**，唯一失败项是 `experiments.py` 还原后哈希对不上。
根因不是本轮改动，而是**提交源码之后才被暴露的行尾问题**，见 §5.4-39/40/41，已修。

### 可再生产物的体积（按 §5.4-19，量过才算数）
| 路径 | 体积 | 性质 |
|---|---|---|
| `artifacts/runs/` | 82 MB / 22 个 run | 证据，保留 |
| `artifacts/test-runs/` | **285 MB / 26 个目录** | 测试中间物。成功时会自清，**失败时保留**——目前这 285 MB 主要是行尾缺陷修好之前那些失败留下的重建树（单棵可达 71 MB）。缺陷已修，可安全清理：`rm -rf artifacts/test-runs/*`（不碰 `response/` 与 `artifacts/api/`） |
| `retrieval/colqwen_scores_fullpool.sqlite` | 220 篇跑满约 26 MB | 索引，保留 |
| `retrieval/colqwen_scores_fullpool.ckpt/` | 运行中最高约 76 MB | 纯中间物，每篇文档提交后自清，跑完为空 |
| `router/cache/` | 9.8 MB | 可再生，已 gitignore |

`tests/test_statistics.py` 是 2026-09-01 新增的，堵的是一个**没有任何东西在看**的口子：
六个模块各自带着一份 `cluster_ci`，它们今天一致，但**没有测试断言它们一致**。
若某一份漂移成按题重采样、或漂移成「各文档均值的均值」，
受影响的实验会报出比数据支持的更窄的区间，而**仓库里每一项检查仍然全绿**。
该测试断言的是性质不是代码：六份实现在同一输入上的点估计与区间（实测**逐位相同**）；
注入纯文档效应时聚类区间必须**变宽**（实测 0.0446 vs 0.0118），
而文档间无差异时**不得**明显变宽；点估计必须是比值之和而不是均值的均值
（100 题的文档与 2 题的文档不能等权）；Holm 的单调性、不低于原始 p、不超过 Bonferroni；
bootstrap 的 p 被下限截在 1/n_boot 而不是打印 0。

`tests/test_phase3.py` 断言的是 Phase 3 数字成立所依赖的性质，而不是代码长什么样：
动作缓存截断到 top-32 后每个 recall 逐位不变；级联特征只读它真的跑过的那个检索器
（把另一个检索器的分数改成 −99 倍，特征必须一位不动）；升级成本按增量计费；
随机对照确实是它自称的那个精确期望；折外预测真的在折外
（纯文档效应的目标在折内可学、折外不可学）。

---

## 4. 剩余工作（按建议优先级）

### ① 把 E36 的 GPU 级联接到端到端生成 ← **建议下一步（已注册为 E39，状态 blocked）**
`python experiments.py show E39` 有完整设计与事先说好的判读规则。
**2026-09-01 补上了一个会静默出错的缺口**：路由器此前只落盘 `predicted_gain`，
下游生成得自己按预算重推升级决策。只要两边的 tie-break 有一点不同，
被升级的题集就悄悄换掉，而**任何指标都不会暴露这件事**。
现在 `router/budget_router.py` 的 per_question.csv 直接带
`escalate_at_B005` / `escalate_at_B015` / `escalate_at_B050` 三列布尔，
由与实验同一个 `escalation_mask` 生成（实测比例逐位等于 0.05 / 0.15 / 0.50）。

Phase 3 现在全部指标是 **evidence recall**。「同质量下 ColQwen 调用降到 5%~15%」
这句话**在 F1 上尚未验证**。需要一次配对 API 运行，照 E29 的做法：
同模型、同 prompt、同 gold，只有候选块不同，两臂是

- 静态臂：`rrf text + colqwen visual`（每题都调 ColQwen）
- 路由臂：`router/phase3_cells.py` 在 B≈0.15 处的升级决策（逐题落盘在 per_question.csv）

预算参照 E29：600 题、1,225 次调用、12.09 AUD。**开跑前先定死 thinking 开关**（§5.3-12）。
若 F1 差值的 CI 包含 0 而 ColQwen 调用少了 85%，那就是本项目最干净的成本结论。

### ② 补完 ColQwen 全池索引
机制全部就绪且测试通过，只差 GPU 时间（**5–9 小时**）。显存空闲时：
```bash
.venv-colpali/Scripts/python.exe -m retrieval.colqwen_index \
    --image-source fulldisk --doc-order random \
    --out retrieval/colqwen_scores_fullpool.sqlite
python -m retrieval.eval_fullpool
```
- `--doc-order random` 让**任何停止点都是文档的简单随机样本**，部分索引也可报告。
- 文档内检查点：660 张图的文档也能跨窗口续跑。
- **待验证的预测**：候选池上本项目 Recall@10 = 0.820，论文 0.708；
  补齐池后应当**下降并逼近 0.708**。不降就说明差距从来不是池造成的。
- **前提**：Ollama 的 `llama-server.exe` 不能占着 GPU（它会拿 3.26 GB，
  剩下的放不下大图激活，表现是模型能加载但一片都写不出来）。

#### 2026-09-01：**已完成**，且三条旧判断都要更正

| 旧记录 | 实测 | 处置 |
|---|---|---|
| GPU 被 Ollama 的 `llama-server.exe` 占着 6832/8188 MiB | **1238/8188 MiB，进程表里没有 llama-server** | 阻塞解除 |
| 预计 5–9 小时 | **0.50 s/图**，全部 13,936 张约 **1.9 小时** | 估计偏高 3–5 倍 |
| 「文档内不能续跑，某篇跑到一半被打断就要整篇重来」 | **文档内检查点一直是好的** | 该判断是错的 |

第三条要说清楚，因为它当时把人吓住了没敢开跑。`colqwen_scores_fullpool.ckpt`
之所以是**空目录**，不是因为没写检查点，而是因为 `colqwen_index.py` 在每篇文档
提交 ranking 之后会**逐片删掉自己的检查点**。运行中去看那个目录就能看到分片
（实测 `inditex_2021__b2__000000.pt` … 一篇 448 张图写了 224 片）。
分片键里带批大小（`__b2__`）正是 §5.4-17 那条教训的产物。
**结论：这个任务一直是可以随时打断、随时续跑的，当时不该被「空目录」误导。**
教训见 §5.4-32。

**同时补上了这个脚本真正缺的东西：同文档配对对照。**
原来的 `eval_fullpool.py` 把「部分样本的全池数」和论文的「全语料 0.708」并排放，
读者只能拿它跟候选池上的 0.820 比——而那是 220 篇的数。
两者相减**同时混进了池规模效应和文档抽样效应**。
现在脚本会用同一批问题、同一个 gold 分母，把候选池索引也跑一遍，
报**配对的 document-cluster 区间**。这才是这个索引真正存在的理由。

**结果（220/220 篇，1995 题）**：论文值在三个 k 上全部落在区间之外——池规模不是唯一原因。

| k | 全池 recall | 95% CI | 论文 | 同文档配对：全池 − 候选池 |
|---|---|---|---|---|
| 10 | 0.782 | [0.747, 0.817] | 0.708 | -0.0374 [-0.0509, -0.0265] |
| 15 | 0.856 | [0.823, 0.885] | 0.792 | -0.0334 [-0.0493, -0.0218] |
| 20 | 0.894 | [0.864, 0.919] | 0.843 | -0.0359 [-0.0542, -0.0225] |

**预测被证伪。**补全图片池确实把 Recall@10 从候选池上的 0.820 拉低到 0.782，方向对，配对降幅 -0.0374 [-0.0509,-0.0265]；但论文的 0.708 **落在 95% CI [0.747,0.817] 之外，三个 k 都是**。池规模只解释了到论文值距离的 **33%**，剩下的来自别处。论文没有给出任何检索器版本，因此那个差异**无法从发表物里定位**——这本身就是对「不能声称复现了论文系统」这条纪律的一次实证支持。

覆盖率仍然是**两个池方向相反，不要混为一谈**：

| 索引 | 覆盖 | 谁在用 | 状态 |
|---|---|---|---|
| 候选池 `colqwen_scores.sqlite` | **220/220 篇**，2,000 题，6,548 图，0 条 unpooled | E24/E27/E34/E35/E36 | **完整** |
| 全池 `colqwen_scores_fullpool.sqlite` | **220/220 篇**，1995 题 | 只有 eval_fullpool | **完整** |

**已发表的配对比较没有被这件事削弱**：ColQwen 臂排完了每篇文档候选池的 100%。
canonical 里 6,565 条非文本证据、索引到 6,548，差的 17 条在候选池之外，
`colqwen_failed_images.jsonl` 是空的——没有失败样本。

### ③ 写报告
材料已经够了。写的时候注意 Phase 3 的两条口径必须并列出现（特征组事先固定 vs 折内选择），
以及 §5.1-4：这条切分自 E9 起被反复观察，**Phase 3 的结论同样只能标 exploratory**。

### 已明确不做
- 让描述分支也上全池 —— 需为 8,943 张图补 VLM 描述，付费，未批准。
- Phase 4 粒度 / Phase 5 dynamic top-k —— proposal §16 属「最好完成」与「扩展」，可裁。

---

## 5. 踩过的坑（**这一节最值钱**）

### 5.1 统计与口径
1. **重采样单位必须与真实抽样单位一致。** 396 题只来自约 55 篇文档，
   按题 bootstrap 会低估区间。用 **document-cluster bootstrap**。
   但注意一个反直觉观察：**聚类不必然放宽区间**——E29 里按题
   [+0.94,+4.99] 反而略宽于按文档 [+1.01,+4.77]。用它的理由是**单位匹配**，
   不是「它更保守」。
2. **分母不能被静默改变。** 无法评价的 gold 默认计为 miss 进 unconditional recall，
   另行报映射覆盖率。要报子集口径就必须单独命名 conditional-on-mapped。
   每次评测都打印 QA 数 / gold 数 / mapped 数 / dropped 数。
3. **CI 下界贴 0 不能写「显著」**；多 k 多系统比较要说明多重比较。
4. **被反复观察并用于挑方法的切分不再是干净确认集**——只能标 exploratory。
5. **oracle 上界大 ≠ 有可路由空间**（E8）。报上界必须带对照。

### 5.2 基线身份
6. **只有当基线真的复现了被比较论文的系统，才能说「优于已发表配置」。**
   否则命名为 *local surrogate baseline* / *closest local paper-style baseline*。
7. **不要把自己的推断说成论文原文。** MMDocRAG 论文**没有给出任何检索器的版本**，
   我却一度把「bge-large-en-v1.5 / ColQwen2-v0.1」当成论文配置写进代码与记录。
8. **术语纪律**：在 VLM 描述上跑 BM25/稠密检索叫 **image-description retrieval**，
   **不能**叫 visual retrieval——它根本没看像素。

### 5.3 成本
9. **价格表里没有该模型本身、已核验的条目时，不报美元，只报 token。**
   曾用 gemini-2.0-flash 的价算 gemini-3.6-flash，输入低估 7.5×、输出低估 9.4×。
10. **预算按 `total_tok`，不是 `in_tok + out_tok`。** thinking token 按**输出价**计费，
    占计费输出的 **81%**。
11. **provider 的计费面板是地面真值**，早期就要对一次账，差超一成说明计费模型漏了东西。
12. **thinking 开关属于开跑前的决定**——配对比较中途改开关等于把已花的钱作废。

### 5.4 执行工程（本会话新增，代价最惨重）
13. **绝不把长任务的输出接进 `tail`/`grep`/`head` 管道。**
    tqdm 高频写 stderr，管道缓冲写满后**进程阻塞在写操作上**，吞吐从 50/s 掉到个位数，
    而且整整两小时看不到一行进度。**一律 `> log 2>&1`，要看进度就另外去读文件。**
14. **长任务必须自带检查点**（见 §1 会话执行模型）。写分片要
    先写临时文件再 `os.replace`，载入时**校验行数/跨度**——被截断的分片若被当成完好的，
    任务会「成功」结束却带着错误数据。
15. **`np.save` 会给不以 `.npy` 结尾的路径自动追加 `.npy`**，
    所以 `np.save(p + ".tmp", a)` 实际写的是 `p.tmp.npy`，随后的原子改名必然
    `FileNotFoundError`。要传**已打开的文件句柄**。
16. **`os.path.relpath` 跨 Windows 盘符抛 `ValueError`**——为了打印好看的相对路径
    而崩掉整个任务不值得，用 try/except 兜住。
17. **检查点的键必须包含批大小。** 分片 `0` 在 batch=2 下是图 0–1、batch=4 下是图 0–3；
    只按偏移命名会让改批大小后的重跑命中旧分片却只拿到一半图片。
    实际后果：某文档「成功」完成但 **192 张图只排了 106 张**，不报任何错。
18. **每个 `encode()` 都重建模型会让吞吐掉 3 倍。** 分片化之后同一语料
    要付 23 次模型构造。已改为进程内缓存。
19. **凡是每次运行都产出目录的机制，都要把体积写进它自己的记录。**
    38 棵重建树吃掉 **36.6 GB**（`git archive` 无 pathspec，把整个仓库含数据集
    解进每棵树），直到 D 盘只剩 0.8 GB 才被发现。测试全绿、指纹全对——
    它们只在**没人量过体积**时才能存活。
20. **`--scratch-root` 决定的是放哪，不是留不留。** 中间物只在失败时值得保留。
21. **`git apply` 会向上找仓库。** 往仓库内的目录打补丁时它会认到本仓库、
    打印 `Skipped patch` 并**退出 0**。必须设 `GIT_CEILING_DIRECTORIES` 并检查输出，
    不能只看退出码。
22. **Windows 无开发者模式时 `huggingface_hub` 建不了符号链接缓存**（WinError 1314），
    且 xet 传输后端会挂起。用 `retrieval/fetch_model.py` 落成平铺目录。
23. **删目录树前先查 junction/符号链接**，`rm -rf` 会跟进去删到目标。
24. **批量删除前先确认不碰付费 API 产物**（`response/`、`artifacts/api/`）——
    它们花了真金白银且不可再生。
25. **这个 shell 的 heredoc 会被单双引号打断。** `cat > f <<'EOF'` 里只要出现
    `'` 或 `"`，就会报 `unexpected EOF while looking for matching`，而且**文件不会被创建**。
    写含引号的 Python/文本一律用 Write 工具，或先把补丁脚本写到 scratchpad 再执行。

### 5.6 Phase 3 新增的纪律
26. **约束下界是「最优固定策略」与「保配比置换对照」中更强的那个**，
    而哪个更强必须从数据读出来。E19 里置换对照更高，E35 里反过来。两个都要报。
27. **预算实验的主对照是同预算的随机分配。**「比不升级好」是废话——
    升级本身就多做了检索。只有在同样预算下胜过随机挑谁升级，才说明路由器懂 query。
28. **级联的升级成本按增量算，首轮做了而升级用不上的那一遍是沉没成本、不退款。**
    用「从零跑两个动作的成本之差」当增量会让级联显得更便宜：GPU 级联在 B=1 时是
    3 cpu + 1 gpu，比直接跑静态系统（2 cpu + 1 gpu）**更贵**。成本参照系是静态系统。
29. **对照的期望能算就不要抽样。** 均匀随机升级 m/n 时第 i 题的期望恰是
    `base_i + (m/n)·gain_i`。用几百次抽样去估它等于给唯一承载主张的对照加一层
    蒙特卡洛噪声——本实验里那点噪声足以让 Holm 校正后的 p 跨过 0.05。
30. **每格结果各自播种。** 八格共用一条 RNG 流时，「跑全部八格」与
    「用四格缓存再跑四格」会消耗掉不同数量的随机数，同一条命令因此打印不同的数字。
    按格的身份（crc32，不是 `hash()`，后者每进程加盐）派生种子。
31. **E23 的教训要上升一层**：不只是「别把 384 维句向量拼进低维特征」，
    而是「在这个样本量下，连**该不该拼进去**都选不准」——
    折内选择在 40 个 fold 里换了 5 种特征组，主家族存活数从 3/8 掉到 1/8。

32. **「检查点目录是空的」不等于「没有检查点机制」。** 正确的检查点实现会在
    工作单元完成后清理自己的分片，所以**空目录恰恰是它工作正常的表现**。
    判断续跑能力要去读代码或在运行中观察，不能从静态目录状态反推——
    我据此在交接文档里写了「文档内不能续跑」，把一个随时可中断的任务
    描述成了不敢开跑的任务。
33. **同一个量有六份实现时，要有测试断言它们一致。** 本项目六个模块各带一份
    `cluster_ci`，全部区间实测逐位相同——但在 `tests/test_statistics.py`
    之前，**没有任何东西在看这件事**。若其中一份漂移成按题重采样，
    受影响的实验会报出更窄的区间，而仓库里每一项检查仍然全绿。
34. **中间量被设成目标时，先测「它取到完美时下游值多少」。**
    做法是造一个校准到目标精度的**合成**预测器扫一遍，
    而不是去猜新特征能带来多少。E38 用两小时关掉了一整轮特征工程加一笔 API 开销。
35. **合成对照本身要校准并检查。** 把预测值裁到定义域会显著改变实测精度
    （名义 R²=0 实测成 0.29），必须报实测值并按实测值反解噪声；
    扫参数曲线要用**共同随机数**，否则每点的蒙特卡洛噪声会制造出假的次序。
36. **切片必须在模型选择之后做。** 折外选择在全语料上完成一次，
    切片只划分已经算好的折外向量。让每个切片自己选配置，
    得到的就不是原实验的数字，而是 N 个各自过拟合的新实验。
37. **异质性要用对照检验，不能用「一格显著、另一格不显著」。**
    后者是两个各自带噪声的判断之差，不是差的判断。
    对照要按文档 bootstrap，因为同一篇文档会同时贡献两半的问题。

38. **限定词在转写时最容易掉。** E36 的注册表 `limits` 一直正确地写着
    「B=0.05~0.15 是看着曲线读出来的，属描述性数字，不是检验」，
    但转写进 HANDOFF 摘要与记录簿时变成了「同质量下 / 质量差异不显著的前提下」——
    那暗示做过一次**从未做过**的等价性检验。
    **核对不能只核对注册表，还要核对引用它的每一处**；
    叙述文档比注册表更容易出这种错，因为它要把一句话压缩得更短。

39. **`.gitattributes` 必须先 pin 它自己。** Git 逐行解析该文件，行尾多一个 `\r`
    会让每行最后一个 token 变成 `-text\r`——不是合法属性，于是**整份规则被静默忽略**。
    本项目的字节精确性完全建立在这些 `-text` 规则上，而该文件**当时没有覆盖自己**：
    本机工作区碰巧是 LF，所以看不出问题；任何新克隆在 `core.autocrlf=true` 下
    拿到的是 CRLF 版本，届时**每个源文件记录的 SHA-256 都会对不上，而现象看起来像被篡改**。
    已加 `.gitattributes  -text`。**自指的配置文件都要先自检一遍。**
40. **重建的两步需要相反的处理，而这一条我第一次写错了。**
    初版写成「重建树里一律关掉行尾转换，因为重建要的是字节」。**那是错的**，
    并且错误方式很有教育意义：把整棵树强制成 blob 字节之后，项目自己钉住的文件对了，
    **七个上游文件反而全错**（`data_utils.py`、`eval_all.py`、`inference_*.py`、
    `prompt_bank/*`）。逐文件量出来才看清：

    | | blob | 工作区 | 强制 blob 字节后还原 |
    |---|---|---|---|
    | `data_utils.py`（未钉住） | 1253B / 0 CRLF | **1294B / 41 CRLF** | 1253B / 0 CRLF ❌ |
    | `experiments.py`（已钉住） | LF | LF | CRLF ❌ |

    **清单记的是工作区，而这台机器的工作区对未钉住的上游文件就是 CRLF。**
    所以「还原成 blob 字节」和「还原成工作区表示」都不是对的，正确的是
    **让 git 自己的属性机制工作**，它对钉住的给 LF、对没钉住的给工作区表示。

    于是两步分开处理：
    - **`git archive` 在仓库内运行**，属性机制本来就有效——只要那份
      `.gitattributes` 能被解析。所以修法是**把它从 blob 写回去**，一个文件、一行原因。
    - **`git apply` 在重建树里运行，且 `GIT_CEILING_DIRECTORIES` 让它找不到仓库。
      属性是仓库概念，树里那份 `.gitattributes` 根本不会被读**，
      `core.autocrlf=true` 于是作用到每个被补丁写过的文件上。这一步才需要
      `-c core.autocrlf=false`，依据是：补丁碰到的指纹文件全都是本项目自己钉住的，
      上游文件是原样继承、从不修改。这个前提**由这条测试本身守着**——
      哪天有个未钉住的文件被改了，它会在这里失败，而不是在某次 run 里静默出错。

    实测轨迹：0/20 hunk（补丁被整体拒绝）→ 12/20 → 16/20 → **19/20，1 个 MISSING
    正是本轮新建尚未跟踪的文件**，与 `n_source_files_tracked_by_git = 19` 吻合。
41. **一条缺陷可能是「被新提交暴露的」而不是「新写坏的」。** 上面这条在
    `experiments.py` 上失败，第一反应是当天的改动写坏了。逐个 run 回查后发现：
    三个 2026-08-30 的 run（commit `2fd7505`）全部通过，因为那时源码还没提交、
    25 个文件里 18 个记为 MISSING，**patch 路径根本没被走过**；
    而 `fae7457` 提交源码之后的**每一个** run 都在同一个文件上失败。
    **定位归因要横跨多个历史 run 比对，不能只看最近一次。**

42. **写进去但不渲染的字段，比缺字段更糟。** 注册表支持 `result` 与 `result2`，
    但 `cmd_show` 只打印这两个；E34 与 E36 的 `result3` 各自是一整段承载结论的文字
    （E34 那段里包含「**必须撤回一条结论**」），**存在仓库里、从未被显示过**。
    它读起来像是已经记录了，实际是隐形的。这与 §5.5 里 `status` 用错规范键
    是同一类缺陷：注册表与渲染器各自演化，中间没有东西在核对。
    已改为渲染任意 `resultN`。**加了字段就要立刻把每一条都渲染一遍看**——
    §5.5 末尾那条自查命令正是为此存在的，但它只检查「不抛异常」，
    查不出「字段被静默忽略」，所以还要肉眼比对一次字段清单与渲染输出。

43. **线索清单可能自带重复，只有查版本才看得出来。** 文献综述留了四条未入库的线索，
    其中「R1-Router」与「Mixture-of-Retrieval Experts」**是同一篇 arXiv 论文**
    （2505.22095），同一批作者在 v1（2025-05-28）与 v2（2026-04-06）之间改了题目和系统名，
    方法（Step-GRPO）没变。分别入库会让同一个系统在覆盖矩阵里被数两次，
    而**搜索结果本身不会提示这件事**——两个标题看上去就是两篇论文。
    凡是按标题攒起来的线索清单，入库前都要查一次版本历史。

44. **「没测过」和「测了但不对」不能打印成同一个样子。** `verify` 默认取 `latest` run，
    而 latest 往往是刚跑过的单个实验；对着它跑 `verify E27` 会把 29 个检查
    全部报成 FAIL/MISSING，与头条结果真的崩了**在输出上无法区分**。
    我自己在本轮就被这一屏吓到过一次，回查才发现数据完好、只是指错了 run。
    凡是「对某次运行取数」的检查器，都要先判断该运行里到底有没有这个实验，
    并把这件事作为第一行说清楚。

### 5.5 我犯过的具体错误类型（用于自查）
- **行数 vs 实体数**：把 30 行文件当成 30 条完成记录（实际只有 15 条有响应）；
  把 6,548 条 evidence row 除以 13,999 张唯一图片得到「46.8%」，单位不一致。
- **按题加权 vs 按文档**：「每篇文档中位 29 个图片候选」是按题加权的数，
  按文档中位数是 20。
- **同一个 cursor 既做外层迭代又做内层查询**，会把游标冲掉、静默漏掉后续行。
- **同时改两个变量却归因给一个**：`RRF(描述) − ColQwen` 同时改了表示与检索架构，
  不能叫「隔离了表示」。
- **把展示标签当成规范键**：注册表的 `status` 规范键是 `"pos"`，其中文标签才是「正向」。
  我一度直接写 `status="正向"`，`experiments.py show` 于是对 E29/E34 抛 `KeyError`——
  而 `list` 和 `run-suite` 都不碰这张表，所以缺陷藏了整整两个实验才暴露。
  **改了注册表字段之后，把每一条都渲染一遍**：
  `for id in $(python -c "import experiments as E; print(' '.join(x['id'] for x in E.E))"); do python experiments.py show $id >/dev/null || echo FAIL $id; done`

---

## 6. 文件地图

### 必须复用、不要重写
| 文件 | 为什么 |
|---|---|
| `eval_all.py:extract_citations` / `get_scores` | 官方口径的引用抽取与 P/R/F1。任何 F1 都必须走这条路径，否则与论文和项目内其它数字不可比 |
| `data_utils.py` | `load_jsonl` / `save_jsonl` / `encode_image` |
| `prompt_bank/*.txt` | 三个官方 prompt，Phase 2 起固定不变 |

### 数据层
| 路径 | 内容 |
|---|---|
| `canonical/mmdocrag.sqlite` | 48M。`questions` 4,055、`canonical_evidence` 25,716、`question_candidates` 141,480、`question_gold_evidence` 21,978、`question_settings` 8,110 |
| `retrieval/quotes.sqlite` | 57M。自建 chunk 92,752（421/篇）+ `gold_map` 3,151 |
| `retrieval/pages.sqlite` | 50M。页级语料 14,763 页 |
| `retrieval/colqwen_scores.sqlite` | 8.6M。**候选池** ColQwen 排名，69,842 行、6,548 张图 |
| `retrieval/colqwen_scores_fullpool.sqlite` | 168K。**全池**索引，只有 5/220 篇 |
| `manifests/split_doc_disjoint.json` | 冻结的 document-disjoint 切分 |
| `manifests/e29_subset.json` | E29 的 600 题子集 |

### 模型（本地，勿重下）
- `models/colqwen2-v1.0`（86M LoRA）+ `models/colqwen2-base`（8.3G）
- `models/bge-large-en-v1.5`（1.3G）——**本项目唯一字节可证的模型**，
  `fetch.json` 记录 revision `d4aa6901d3a41ba39fb536a557fa166f842b0e09` 与逐文件
  SHA-256，`python -m retrieval.fetch_model BAAI/bge-large-en-v1.5 --check` 可复验。

### 关键脚本
| 文件 | 作用 |
|---|---|
| `experiments.py` | 实验注册表 + 运行器。**权威可执行记录** |
| `expkit/` | run 系统：`runner` `results` `report` `source` `verify` `apilog` `artifacts` `paths` |
| `retrieval/eval_stack_v2.py` | **E27 的报告脚本**（`eval_stack.py` 保留但已过时）。`--pool {selfbuilt,canonical}` `--k` `--dense-model` |
| `retrieval/nested_cv.py` | nested CV 选配置 |
| `retrieval/ablation.py` | E30 归因消融 |
| `retrieval/colqwen_index.py` | ColQwen 索引。`--image-source {canonical,fulldisk}` `--doc-order random`，**在 `.venv-colpali` 里跑** |
| `retrieval/eval_colqwen.py` | 候选池上的配对比较。**检测到 `unpooled:` 会 exit 1** |
| `retrieval/eval_fullpool.py` | 全池 ColQwen 绝对 recall，对标论文 Table 6。**候选池索引会 exit 1** |
| `eval_e29_paired.py` | E29 配对分析。**算任何区间前先断言均值复现 `eval_all` 的打印值** |
| `router/` | Phase 1A.5 的模态路由（负结果）+ `cost_quality.py` 成本表 |
| `router/actions.py` | **Phase 3 底座**。复用 `eval_stack_v2.build(keep_scores=True)` 缓存逐题 12 动作 × recall × 成本；`cost` / `incremental_cost` / `cascade_cost` 两种货币分开 |
| `router/tie_audit.py` | **E35**。tie-aware oracle、保配比置换对照、按预算子空间的天花板 |
| `router/features_p3.py` | Phase 3 特征，按**何时可得**分组：shape / qtext / emb / firstpass |
| `router/budget_router.py` | **E36 单格**。Policy A（检索前选）与 Policy B（级联），折外 + 折内选模型 |
| `router/phase3_cells.py` | **E36 主表**。八格一个 Holm 家族，每格落盘可续跑（`router/cache/cells/`） |
| `router/cache/` | Phase 3 缓存，**9.8 MB**（两张 ~5 MB 动作表 + 16 个小 JSON）。已 gitignore：可再生且不是证据，权威记录是 run 的 metrics.json |
| `tests/test_phase3.py` | 33 项。截断无损、特征不越权、增量计费、随机对照精确、折外真在折外 |
| `retrieval/slice_by_type.py` | **E37**。把 E27 的折外提升按证据模态 / 跨页 / question_type 切片；两个 Holm 家族（切片检验、对照检验）分开声明 |
| `retrieval/r2_target.py` | **E38**。合成预测器扫 R² → 分配收益曲线；σ 按裁剪后实测 R² 二分反解，各点共同随机数 |
| `tests/test_statistics.py` | **25 项**。六份 `cluster_ci` 一致、聚类确实改变区间、比值之和而非均值的均值、Holm 正确性、bootstrap p 有下限、配对 bootstrap 保留配对 |

### 文档（2026-09-01 全量盘点）
| 路径 | 是什么 | 状态 |
|---|---|---|
| `docs/HANDOFF.md` | 本文件，地图 | **当前** |
| `docs/lab-notebook.html` | 叙述性主记录，每个实验一条 | **当前** |
| `docs/literature-review.html` | 文献综述渲染页（36 篇 / 15 精读） | **当前**，由 `literature.py render` 生成 |
| `docs/literature/papers.json` | 文献注册表，`literature.py check` 是它的守门人 | **当前** |
| `docs/literature/queries.json` | 每一次检索的词、日期、来源；**它逼出过一个错误结论**（modality 行为 0 是因为我根本没检索过） | **当前** |
| `docs/literature/gap.html` | 有证据支撑的 gap 段落 | **当前**。含**四处**被迫的更正：两处在综述期间（Modality-Utility 的随机对照、modality 行的 0 是没检索过），两处在 2026-09-01 补完四条线索之后（MAGE-RAG 迫使「没人分货币计价」收窄，R1-Router 成为第二个反例） |
| `docs/paper-baseline-audit.md` | 论文式基线逐项核对（E34） | **当前** |
| `docs/artifacts-git-policy.md` | 什么进 Git、什么不进、行尾为什么要 pin | **当前** |
| `docs/audit-e27.html` | E27 审计 | 定点记录，按时间戳读 |
| `docs/MMDocRAG_实验记录通俗解读与研究Roadmap.docx` | 2026-08-28 的旧综述 | **已过期**：早于 E29/E34/E35/E36/E37/E38，仓库里没有任何地方引用它。别拿它当现状 |
| `docs/*.backup-20260828-pre-ablation.docx` | 上面那份的备份 | **已过期**，同上 |

### 一条已查清并修好的报告路径缺陷（2026-08-30，发现于 Phase 3 的回归核对）
做 Phase 3 时顺手核对 E27 有没有被我的改动碰坏，发现**打印出来的 CI 与
metrics.json 里记的 CI 不一样**：selfbuilt k=10 打印 [+0.0471,+0.0748]，
记录 [+0.0468,+0.0753]。

原因不是我的改动，而是 `nested_cv.py` **对同一个比较调了两次 `cluster_ci`**，
一次给打印的表格、一次给 metrics 块，两次从**同一条前进中的随机流**里抽了
不同的 bootstrap 样本。点估计一直是同一个数（`0.06081109307359307` 逐位不变），
只有区间端点在第三位小数上分叉。因为 metrics.json 才是权威记录，
**错的是打印出来的那张表**。

已修：算一次、两处共用。记录值随之变成 [+0.0471,+0.0748]，四格符号与显著性不变。
已在 E27 的 `note` 里写清楚。同时确认：为 Phase 3 给 `eval_stack_v2.build` 加的
`keep_scores` / `top_keep` 在默认关闭时是死代码，E27 四个点估计逐位复现。

**可复用的检查**：凡是既打印又落盘同一个 bootstrap 量的脚本，
都要确认它只抽了一次。已逐个查过 `eval_stack_v2.py`、`ablation.py`、
`tie_audit.py`、`phase3_cells.py`、`budget_router.py`——只有 `nested_cv.py` 有这个毛病。

---

## 7. 接手第一步建议

```bash
cd D:\Playground\MMDocRAG
python experiments.py list                 # 看全景
python experiments.py show E36             # 看最近一条（Phase 3 路由）
python experiments.py show E35             # 它的天花板前提
python -m tests.test_runner --scratch-root artifacts/test-runs   # 确认 64/0
python -m tests.test_phase3                                      # 确认 33/0
python -m tests.test_statistics                                  # 确认 25/0
python experiments.py verify E27 --run <replay_run_id>           # 确认 61/0
python experiments.py run-suite replay --offline                 # 确认全链可复算
```

**Phase 3 已经做完（E35/E36），§4① 现在是另一件事**：把 E36 的 GPU 级联接到
端到端生成，因为 Phase 3 全部指标还是 evidence recall，「同质量下少调 85% 的
ColQwen」这句话在 F1 上尚未验证。那是唯一需要花钱的一步，开跑前先读 §5.3。

要重看 Phase 3 的结论，直接跑这两条（都有缓存，秒级到分钟级）：

```bash
python -m router.tie_audit --pool selfbuilt --k 10      # 天花板与两个对照
python -m router.phase3_cells --features shape+firstpass  # 八格 + Holm
python -m router.phase3_cells --features search            # 特征组也折内选的口径
```

**两种口径必须并列读**，不能只引强的那个：见 §2「逐题路由」与 §5.6-31。
