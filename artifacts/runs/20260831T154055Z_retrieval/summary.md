# 运行报告 · 20260831T154055Z_retrieval

- 套件：`retrieval`　离线：True　允许 API：False
- 生成时间（UTC）：2026-08-31 15:54:28
- 代码 commit：`fae74579f5e455ec6a321cb552df3664cd58f282`　工作区脏：True
- **source fingerprint：`4cabab7cb5ed85e1`**（39 个源文件 + 注册表快照的哈希）　清单：`artifacts/runs/20260831T154055Z_retrieval/source_manifest.json`
- **source bundle：`artifacts/runs/20260831T154055Z_retrieval/source_bundle.zip`**（39 个文件，213917 字节，sha256 `0574e6aa2d6e1cd38f296f8a80e18e39a1e615f39fb7cdb2665aefea98fbee6d`）——**这是本次源码的最终快照**
- 工作区补丁：`artifacts/runs/20260831T154055Z_retrieval/source.patch`（只含 **Git 已跟踪**文件的改动；本仓库多数源码未被跟踪，因此 patch 单独**不能**还原本次运行，须叠加 bundle）
- 重建测试：**pass** 39/39 个文件哈希逐字节命中（隔离目录 `artifacts/test-runs/20260831T154055Z_retrieval-reconstruct/tree`）
- 复现源码：`python -m expkit.source reconstruct --run 20260831T154055Z_retrieval`（git archive → git apply → 解压 bundle → 重算全部哈希）
- 实验状态：已运行 3，跳过 3，已运行（仅日志） 17

> 本报告中的每个数字都取自本次运行落盘的 `metrics.json`，不复制 `experiments.py` 里的历史文字。标记为「已运行（仅日志）」的实验尚未接入结构化输出，其数字请看对应的 `stdout.log`，不要从这里引用。

## E9　模态路由不可学

**状态**：已运行（仅日志）　耗时 8.7s
- **问什么**：能否只看问题就判断这题该用图片还是文字描述？
- **怎么做**：19 个模型的成对结果上训练轻量分类器，检查 AUC、kappa 与跨模型迁移。
- **指标含义**：kappa≈0 表示不同模型对「这题该用哪种输入」几乎不一致。
- **统计单位**：question（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260831T154055Z_retrieval/experiments/E9/cmd0/stdout.log`

- **限制**：不能写成「该属性不存在」或「所有 Router 都不可能」。

## E10　模态选择的成本-质量表

**状态**：已运行（仅日志）　耗时 0.9s
- **问什么**：多模态输入值不值它的 token？
- **怎么做**：比较同一模型 pure-text/multimodal 的 F1、token 与 Pareto 前沿。
- **指标含义**：每换 1 分 F1 需要多付的输入 token，provider-neutral。
- **统计单位**：question（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260831T154055Z_retrieval/experiments/E10/stdout.log`

- **限制**：Gemini 图片 token 未计入；美元价格未核验，跨供应商成本不可直接比。

## E11　泄漏探针的一个自查 bug

**状态**：已运行（仅日志）　耗时 2.1s
- **问什么**：按 gold 模态路由（需要答案）能否胜过固定策略？
- **怎么做**：修正 evidence 类型识别后重跑泄漏探针。
- **指标含义**：原探针只识别 table，修正后覆盖全部视觉类型。
- **统计单位**：question（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260831T154055Z_retrieval/experiments/E11/stdout.log`

- **限制**：这是 bug 修复，结论随之改变。

## E12　我自己的 OCR 消解了我自己的立论

**状态**：已运行（仅日志）　耗时 0.2s
- **问什么**：有多少 gold 落在文本检索够不着的地方？
- **怎么做**：在补 OCR 前后分别重算 gold 证据的文本可达性。
- **指标含义**：补 OCR 后从 12.1% 降到 0.7%，原「结构性不可见」论据被消解。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260831T154055Z_retrieval/experiments/E12/cmd0/stdout.log`

- **限制**：OCR 后文本可达不代表视觉关系已被正确理解。

## E13　页粒度上文本检索对视觉证据没有劣势

**状态**：已运行（仅日志）　耗时 2.6s
- **问什么**：页粒度上视觉 gold 是不是更难被文本检索找到？
- **怎么做**：以整页为证据单元比较文本 gold 与视觉 gold 的召回。
- **指标含义**：页粒度上两类 gold 差距很小，因为图与周围文字捆在一起。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260831T154055Z_retrieval/experiments/E13/stdout.log`

- **限制**：找到正确页不等于找到图中正确区域。

## E14　模态信号是粒度依赖的

**状态**：已运行（仅日志）　耗时 2.2s
- **问什么**：模态差距为什么在页粒度上消失？
- **怎么做**：以细粒度 quote/region 为证据单元重做同一比较。
- **指标含义**：模态效应是粒度依赖的：quote 级才显现交叉。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260831T154055Z_retrieval/experiments/E14/stdout.log`

- **限制**：报告任何模态结论都必须同时说明证据粒度。

## E15　「图片 quote 更好检索」是池组成的产物

**状态**：已运行（仅日志）　耗时 2.9s
- **问什么**：图片 quote 更容易被检索，是因为 VLM 描述与问题词汇对齐吗？
- **怎么做**：控制 quote 长度并分解文字/图片池规模的贡献。
- **指标含义**：+0.080 的表观优势在长度匹配后翻转为 −0.014。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260831T154055Z_retrieval/experiments/E15/stdout.log`

- **限制**：池级分解是描述性诊断，不替代完整对照语料实验。

## E16　检索器交叉：符号翻转，四个 k 全部一致

**状态**：已运行（仅日志）　耗时 125.9s
- **问什么**：BM25 与 dense 的相对优劣是否随证据模态变化？
- **怎么做**：同一候选池上按 gold 类型比较 BM25 与 BGE 的逐证据召回。
- **指标含义**：符号随证据类型翻转，说明存在值得融合的词法—语义互补性。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260831T154055Z_retrieval/experiments/E16/stdout.log`

- **限制**：证据条目层 ±0.09 的效应聚合到整题会缩小。

## E17　二元检索器路由：结论已被正确的标签推翻一半

**状态**：已运行（仅日志）　耗时 43.0s
- **问什么**：逐题在 BM25 与 dense 之间二选一，能否胜过固定策略？
- **怎么做**：以逐题 recall(Dense)−recall(BM25) 为标签和权重重新训练路由器。
- **指标含义**：对固定 +0.016（CI 跨 0），对静态 RRF −0.0279（CI 不跨 0）。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260831T154055Z_retrieval/experiments/E17/cmd0/stdout.log`

- **限制**：旧 E17 用 gold 模态标签写死映射，只能否证那一条人工策略。

## E18　VLM 描述 vs 裁剪 OCR：+0.42 recall

**状态**：已运行（仅日志）　耗时 250.5s
- **问什么**：图表证据用 VLM 描述还是用裁剪 OCR 来检索？
- **怎么做**：同一图片池、同一 BM25 下比较 VLM 描述与裁剪 OCR 两种文字表示。
- **指标含义**：0.791 对 0.369，差距在 OCR 成功提取的子集上仍为 +0.416。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260831T154055Z_retrieval/experiments/E18/cmd0/stdout.log`

- **限制**：OCR 有大量空/不完整结果；不能把全部差距断言为「视觉理解」。

## E19　自适应预算分配：上界远小于原报数字

**状态**：已运行（仅日志）　耗时 30.7s
- **问什么**：逐题分配文本/图片配额，有多少可争取的空间？
- **怎么做**：计算 21 种配额的逐题 Recall 曲线，审计并列最优，改用 oracle−best-fixed regret。
- **指标含义**：真实 regret 上界 0.069/0.074；约 79% 问题固定配额已最优。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260831T154055Z_retrieval/experiments/E19/cmd0/stdout.log`

- **限制**：原 +0.173~+0.179 受 argmax 恒取最小并列索引影响，已作废。

## E20　真实规模自建池上复现 E19

**状态**：已运行（仅日志）　耗时 26.8s
- **问什么**：E19 的结论是不是池偏差造成的？
- **怎么做**：重建更大的文本 chunk 池，保持同一 QA、gold 与图片侧重跑。
- **指标含义**：方向一致说明结论对文本池规模有一定稳健性。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260831T154055Z_retrieval/experiments/E20/stdout.log`

- **限制**：不是独立复现；视觉池仍相同且不完整。

## E21　瓶颈收敛成一个可量化目标

**状态**：已运行（仅日志）　耗时 28.1s
- **问什么**：外部报告提出的比例分配规则管用吗？
- **怎么做**：以 gold 视觉占比为目标训练回归并评价实际 Recall 增益。
- **指标含义**：R² 提升不一定转化为检索收益。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260831T154055Z_retrieval/experiments/E21/stdout.log`

- **限制**：visual share 是 gold 派生的诊断目标，不等同于最优行动。

## E23　高维特征一直在埋掉低维真信号

**状态**：已运行（仅日志）　耗时 59.2s
- **问什么**：二次反思能否预测该用多少视觉配额？
- **怎么做**：用首轮检索结果反射式地重新分配配额，两个池分别跑。
- **指标含义**：预测目标改善不一定转化为检索收益。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260831T154055Z_retrieval/experiments/E23/cmd0/stdout.log`

- **限制**：输入信号弱、样本少且目标平坦。

## E24　ColQwen2 在本项目的池规模下不值它的 GPU 成本

**状态**：已运行　耗时 4.0s
- **问什么**：视觉检索器能否胜过打在 VLM 描述上的文本检索器？
- **怎么做**：在当前 evaluation 图片池上比较 ColQwen2 像素排序与 BM25/BGE/RRF 描述检索。第 0 条命令重建 GPU 索引（约 62 分钟），replay 只跑第 1 条评价命令。
- **指标含义**：视觉 gold 落入 top-k 的比例。注意「在完整 ranking 中」不等于「进入 top-k」。
- **统计单位**：document（bootstrap 按此重采样）

**配置**：pool=canonical-image-quotes　k=20

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| total_visual_gold | 3231.0000 | — |  |
| mapped_visual_gold | 3231.0000 | — |  |
| missing_visual_gold | +0.0000 | — | out of pool; counted as miss |
| n_evaluation_questions | 2000.0000 | — | every question in the evaluation split |
| n_evaluation_questions_ranked | 2000.0000 | — | of those, ranked by ColQwen |
| ranking_coverage_all_questions | 1.0000 | — | ranked / all evaluation questions |
| n_visual_gold_questions | 1995.0000 | — | questions with at least one visual gold evidence |
| n_visual_gold_questions_ranked | 1995.0000 | — |  |
| ranking_coverage_visual_gold_questions | 1.0000 | — | ranked / questions with visual gold |
| n_questions_without_visual_gold | 5.0000 | — | no visual recall is defined for these; excluded from the population, not from the denominator |
| ranking_coverage | 1.0000 | — | deprecated alias of ranking_coverage_visual_gold_questions |
| questions_with_visual_gold | 1995.0000 | — | deprecated alias of n_visual_gold_questions |
| pool_median_per_document | 20.0000 | — | per document, NOT question-weighted |
| pool_mean_per_document | 29.7636 | — |  |
| recall@1_dense | +0.3587 | — | BGE dense over VLM-text |
| recall@5_dense | +0.6834 | — | BGE dense over VLM-text |
| recall@10_dense | +0.8273 | — | BGE dense over VLM-text |
| recall@20_dense | +0.9350 | — | BGE dense over VLM-text |
| recall@1_bm25 | +0.3699 | — | BM25 over VLM-text |
| recall@5_bm25 | +0.7128 | — | BM25 over VLM-text |
| recall@10_bm25 | +0.8344 | — | BM25 over VLM-text |
| recall@20_bm25 | +0.9291 | — | BM25 over VLM-text |
| recall@1_colqwen | +0.3705 | — | ColQwen2 (raw pixels) |
| recall@5_colqwen | +0.6880 | — | ColQwen2 (raw pixels) |
| recall@10_colqwen | +0.8199 | — | ColQwen2 (raw pixels) |
| recall@20_colqwen | +0.9294 | — | ColQwen2 (raw pixels) |
| recall@1_rrf_desc | +0.3798 | — | RRF(BM25,BGE) over VLM-text |
| recall@5_rrf_desc | +0.7298 | — | RRF(BM25,BGE) over VLM-text |
| recall@10_rrf_desc | +0.8468 | — | RRF(BM25,BGE) over VLM-text |
| recall@20_rrf_desc | +0.9406 | — | RRF(BM25,BGE) over VLM-text |
| recall@1_rrf | +0.3751 | — | RRF(BM25-text, ColQwen) |
| recall@5_rrf | +0.7283 | — | RRF(BM25-text, ColQwen) |
| recall@10_rrf | +0.8452 | — | RRF(BM25-text, ColQwen) |
| recall@20_rrf | +0.9437 | — | RRF(BM25-text, ColQwen) |
| paired_delta[ColQwen - BM25]@10 | -0.0145 | [-0.0314, +0.0033] | ColQwen - BM25 |
| paired_delta[ColQwen - BM25]@20 | +0.0003 | [-0.0122, +0.0124] | ColQwen - BM25 |
| paired_delta[ColQwen - BGE]@10 | -0.0074 | [-0.0216, +0.0066] | ColQwen - BGE |
| paired_delta[ColQwen - BGE]@20 | -0.0056 | [-0.0158, +0.0048] | ColQwen - BGE |
| paired_delta[visual branch: BM25+BGE RRF over VLM descriptions - ColQwen over raw images]@10 | +0.0269 | [+0.0127, +0.0412] * | visual branch: BM25+BGE RRF over VLM descriptions - ColQwen over raw images |
| paired_delta[visual branch: BM25+BGE RRF over VLM descriptions - ColQwen over raw images]@20 | +0.0111 | [-0.0010, +0.0230] | visual branch: BM25+BGE RRF over VLM descriptions - ColQwen over raw images |
| paired_delta[fusion complementarity: RRF(BM25 descriptions, ColQwen) - ColQwen alone]@10 | +0.0254 | [+0.0137, +0.0368] * | fusion complementarity: RRF(BM25 descriptions, ColQwen) - ColQwen alone |
| paired_delta[fusion complementarity: RRF(BM25 descriptions, ColQwen) - ColQwen alone]@20 | +0.0142 | [+0.0050, +0.0236] * | fusion complementarity: RRF(BM25 descriptions, ColQwen) - ColQwen alone |
| questions_scored_here | 1995.0000 | — | questions that actually contributed to the recall numerator and denominator |

**限制**：池只覆盖 13,999 张原始图片中的 6,487 张（46.34% 唯一图片）；按文档中位仅 20 个候选，k=20 已接近饱和。这是公平的池内排序比较，不是完整文档图片池上的检索比较。

<sub>逐题结果与 manifest：`artifacts/runs/20260831T154055Z_retrieval/experiments/E24`</sub>

## E25　粒度 × 预算：两个轴给出完全相反的排序

**状态**：已运行（仅日志）　耗时 64.0s
- **问什么**：证据粒度能否改善质量与上下文成本的平衡？
- **怎么做**：按 target-chars 建多档语料，分别在固定 top-k 与固定 word-like 预算下比较。
- **指标含义**：固定 top-k 会把粗 chunk 携带的额外上下文当成免费收益。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260831T154055Z_retrieval/experiments/E25/stdout.log`

- **限制**：预算单位是正则 word-like token，不是 LLM BPE；仅覆盖文本 gold 与 BM25。

## E26　small-to-big 被证伪；细粒度优势一半是预算量化损失

**状态**：已运行（仅日志）　耗时 63.4s
- **问什么**：用细 chunk 排序、返回其粗 parent，能否兼得两者？
- **怎么做**：比较 prefix-stop 与 greedy-skip 两种预算装填规则。
- **指标含义**：早期正增益约一半来自「遇到塞不下就停止」的量化损失。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260831T154055Z_retrieval/experiments/E26/cmd0/stdout.log`

- **限制**：仅覆盖特定档位、BM25 与文本证据，不能封闭整个 RQ3。

## E27　静态检索配置的改进

**状态**：已运行　耗时 40.2s
- **问什么**：模态内 RRF 融合 + 均衡配额，能比基线好多少？
- **怎么做**：文本与图片描述分支内分别 RRF(BM25,BGE-small)，再采用较均衡配额，与本地论文式对照（dense 文本 + ColQwen 视觉 + 官方配额）比较。
- **指标含义**：每题被找回的 gold evidence 比例；未映射 gold 计为 miss。
- **统计单位**：document（bootstrap 按此重采样）

**配置**：pool=selfbuilt　k=10　seed=20260825　bootstrap=4000

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| recall_uncond[A] | +0.6737 | — |  |
| recall_cond[A] | +0.6866 | — |  |
| recall_uncond[B] | +0.6951 | — |  |
| recall_cond[B] | +0.7086 | — |  |
| recall_uncond[C] | +0.6996 | — |  |
| recall_cond[C] | +0.7130 | — |  |
| recall_uncond[D] | +0.7198 | — |  |
| recall_cond[D] | +0.7348 | — |  |
| recall_uncond[E] | +0.6826 | — |  |
| recall_cond[E] | +0.6961 | — |  |
| recall_uncond[E2] | +0.7220 | — |  |
| recall_cond[E2] | +0.7370 | — |  |
| recall_uncond[F] | +0.6452 | — |  |
| recall_cond[F] | +0.6576 | — |  |
| recall_uncond[G] | +0.7299 | — |  |
| recall_cond[G] | +0.7448 | — |  |
| delta: D - A   full stack vs dense-only baseline | +0.0461 | [+0.0162, +0.0780] * | D - A   full stack vs dense-only baseline |
| delta: D - E   full stack vs closest paper-style | +0.0371 | [+0.0115, +0.0650] * | D - E   full stack vs closest paper-style |
| delta: G - E   best local hybrid vs paper-style | +0.0473 | [+0.0233, +0.0736] * | G - E   best local hybrid vs paper-style |
| delta: B - A   quota alone | +0.0214 | [+0.0008, +0.0408] * | B - A   quota alone |
| delta: C - A   fusion alone | +0.0259 | [-0.0003, +0.0539] | C - A   fusion alone |
| delta: D - C   quota on top of fusion | +0.0202 | [-0.0008, +0.0408] | D - C   quota on top of fusion |
| delta: D - B   fusion on top of quota | +0.0247 | [+0.0022, +0.0477] * | D - B   fusion on top of quota |
| delta: E - A   ColQwen visual vs image-description | +0.0089 | [-0.0196, +0.0371] | E - A   ColQwen visual vs image-description |
| delta: E2 - E  quota on paper-style hybrid | +0.0393 | [+0.0155, +0.0666] * | E2 - E  quota on paper-style hybrid |

**配置**：pool=canonical　k=20　seed=20260825　bootstrap=4000

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| recall_uncond[A] | +0.8417 | — |  |
| recall_cond[A] | +0.8417 | — |  |
| recall_uncond[B] | +0.8468 | — |  |
| recall_cond[B] | +0.8468 | — |  |
| recall_uncond[C] | +0.8563 | — |  |
| recall_cond[C] | +0.8563 | — |  |
| recall_uncond[D] | +0.8646 | — |  |
| recall_cond[D] | +0.8646 | — |  |
| recall_uncond[E] | +0.8637 | — |  |
| recall_cond[E] | +0.8637 | — |  |
| recall_uncond[E2] | +0.8639 | — |  |
| recall_cond[E2] | +0.8639 | — |  |
| recall_uncond[F] | +0.8085 | — |  |
| recall_cond[F] | +0.8085 | — |  |
| recall_uncond[G] | +0.8665 | — |  |
| recall_cond[G] | +0.8665 | — |  |
| delta: D - A   full stack vs dense-only baseline | +0.0229 | [+0.0049, +0.0420] * | D - A   full stack vs dense-only baseline |
| delta: D - E   full stack vs closest paper-style | +0.0008 | [-0.0179, +0.0199] | D - E   full stack vs closest paper-style |
| delta: G - E   best local hybrid vs paper-style | +0.0027 | [-0.0090, +0.0144] | G - E   best local hybrid vs paper-style |
| delta: B - A   quota alone | +0.0051 | [-0.0068, +0.0168] | B - A   quota alone |
| delta: C - A   fusion alone | +0.0146 | [-0.0041, +0.0339] | C - A   fusion alone |
| delta: D - C   quota on top of fusion | +0.0083 | [-0.0041, +0.0219] | D - C   quota on top of fusion |
| delta: D - B   fusion on top of quota | +0.0178 | [+0.0026, +0.0344] * | D - B   fusion on top of quota |
| delta: E - A   ColQwen visual vs image-description | +0.0220 | [+0.0029, +0.0410] * | E - A   ColQwen visual vs image-description |
| delta: E2 - E  quota on paper-style hybrid | +0.0002 | [-0.0076, +0.0081] | E2 - E  quota on paper-style hybrid |

**配置**：pool=selfbuilt　k=10　seed=20260825　bootstrap=4000

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| recall_surrogate_A | +0.6462 | — | local BGE-small surrogate, official quota |
| recall_paper_style_E | +0.6537 | — | closest local paper-style hybrid (dense text + ColQwen) |
| recall_nested_cv_oof | +0.7145 | — | out-of-fold, configuration chosen without the question |
| delta: nested-CV - paper-style (E) | +0.0608 | [+0.0471, +0.0748] * | nested-CV - paper-style (E) |
| delta: nested-CV - surrogate (A) | +0.0683 | [+0.0550, +0.0817] * | nested-CV - surrogate (A) |
| delta: paper-style (E) - surrogate (A) | +0.0075 | [-0.0048, +0.0202] | paper-style (E) - surrogate (A) |
| fold0_selected_quota_text | 4.0000 | — | fold 0 inner selection: rrf/rrf, 4/6 |
| fold1_selected_quota_text | 4.0000 | — | fold 1 inner selection: rrf/rrf, 4/6 |
| fold2_selected_quota_text | 4.0000 | — | fold 2 inner selection: rrf/rrf, 4/6 |
| fold3_selected_quota_text | 4.0000 | — | fold 3 inner selection: rrf/rrf, 4/6 |
| fold4_selected_quota_text | 4.0000 | — | fold 4 inner selection: rrf/rrf, 4/6 |

**配置**：pool=selfbuilt　k=20　seed=20260825　bootstrap=4000

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| recall_surrogate_A | +0.7823 | — | local BGE-small surrogate, official quota |
| recall_paper_style_E | +0.7862 | — | closest local paper-style hybrid (dense text + ColQwen) |
| recall_nested_cv_oof | +0.8166 | — | out-of-fold, configuration chosen without the question |
| delta: nested-CV - paper-style (E) | +0.0304 | [+0.0192, +0.0415] * | nested-CV - paper-style (E) |
| delta: nested-CV - surrogate (A) | +0.0343 | [+0.0246, +0.0437] * | nested-CV - surrogate (A) |
| delta: paper-style (E) - surrogate (A) | +0.0039 | [-0.0047, +0.0127] | paper-style (E) - surrogate (A) |
| fold0_selected_quota_text | 10.0000 | — | fold 0 inner selection: rrf/rrf, 10/10 |
| fold1_selected_quota_text | 10.0000 | — | fold 1 inner selection: rrf/rrf, 10/10 |
| fold2_selected_quota_text | 8.0000 | — | fold 2 inner selection: rrf/rrf, 8/12 |
| fold3_selected_quota_text | 9.0000 | — | fold 3 inner selection: rrf/rrf, 9/11 |
| fold4_selected_quota_text | 9.0000 | — | fold 4 inner selection: rrf/rrf, 9/11 |

**配置**：pool=canonical　k=10　seed=20260825　bootstrap=4000

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| recall_surrogate_A | +0.6712 | — | local BGE-small surrogate, official quota |
| recall_paper_style_E | +0.6786 | — | closest local paper-style hybrid (dense text + ColQwen) |
| recall_nested_cv_oof | +0.7328 | — | out-of-fold, configuration chosen without the question |
| delta: nested-CV - paper-style (E) | +0.0541 | [+0.0402, +0.0689] * | nested-CV - paper-style (E) |
| delta: nested-CV - surrogate (A) | +0.0616 | [+0.0482, +0.0750] * | nested-CV - surrogate (A) |
| delta: paper-style (E) - surrogate (A) | +0.0075 | [-0.0048, +0.0202] | paper-style (E) - surrogate (A) |
| fold0_selected_quota_text | 4.0000 | — | fold 0 inner selection: rrf/rrf, 4/6 |
| fold1_selected_quota_text | 4.0000 | — | fold 1 inner selection: rrf/rrf, 4/6 |
| fold2_selected_quota_text | 4.0000 | — | fold 2 inner selection: rrf/rrf, 4/6 |
| fold3_selected_quota_text | 4.0000 | — | fold 3 inner selection: rrf/rrf, 4/6 |
| fold4_selected_quota_text | 4.0000 | — | fold 4 inner selection: rrf/rrf, 4/6 |

**配置**：pool=canonical　k=20　seed=20260825　bootstrap=4000

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| recall_surrogate_A | +0.8157 | — | local BGE-small surrogate, official quota |
| recall_paper_style_E | +0.8196 | — | closest local paper-style hybrid (dense text + ColQwen) |
| recall_nested_cv_oof | +0.8465 | — | out-of-fold, configuration chosen without the question |
| delta: nested-CV - paper-style (E) | +0.0269 | [+0.0170, +0.0367] * | nested-CV - paper-style (E) |
| delta: nested-CV - surrogate (A) | +0.0308 | [+0.0226, +0.0387] * | nested-CV - surrogate (A) |
| delta: paper-style (E) - surrogate (A) | +0.0039 | [-0.0047, +0.0127] | paper-style (E) - surrogate (A) |
| fold0_selected_quota_text | 11.0000 | — | fold 0 inner selection: rrf/rrf, 11/9 |
| fold1_selected_quota_text | 10.0000 | — | fold 1 inner selection: rrf/rrf, 10/10 |
| fold2_selected_quota_text | 11.0000 | — | fold 2 inner selection: rrf/rrf, 11/9 |
| fold3_selected_quota_text | 11.0000 | — | fold 3 inner selection: rrf/rrf, 11/9 |
| fold4_selected_quota_text | 10.0000 | — | fold 4 inner selection: rrf/rrf, 10/10 |

**限制**：单切分结果为 exploratory；泛化性只由 E28 的 nested CV 支持。

<sub>逐题结果与 manifest：`artifacts/runs/20260831T154055Z_retrieval/experiments/E27/cmd0`</sub>

## E28　复现性与结论边界审计

**状态**：已运行（仅日志）　耗时 4.7s
- **问什么**：已发布的结论有哪些超出了证据？
- **怎么做**：document-grouped 外层 CV，内层在训练折上重选检索器与配额，每题由未参与其配置选择的折评分。
- **指标含义**：无脚本内选择泄漏的 Recall；仍是 internal OOF，不是外部确认。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260831T154055Z_retrieval/experiments/E28/cmd0/stdout.log`

- **限制**：并非严格双层 inner-CV；方法空间此前已用同一 2,000 题开发，k=20 时各折选择不稳定。

## E30　归因消融：+0.054 究竟来自哪个组件

**状态**：已运行　耗时 20.8s
- **问什么**：主结果同时改了文本检索器、图片检索方式和配额，三者各占多少？
- **怎么做**：每格 2×2×2 因子设计，四格（两池 × 两预算）一次跑完，按文档 cluster bootstrap 求主效应，并对 4×3=12 个主效应做 Holm 校正。
- **指标含义**：每个主效应是该因子单独翻转、另两因子取遍所有水平的平均配对差。raw 95% CI 与 Holm 校正后的 p 同时给出，校正不隐藏任何东西。
- **统计单位**：document（bootstrap 按此重采样）

**配置**：pool=all(selfbuilt,canonical)　k=all(10,20)　seed=20260825　bootstrap=4000

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| cell_recall@10[text=dense,visual=colqwen,quota=7/3] | +0.6537 | — | dense + ColQwen over images + official 7/3 |
| cell_recall@10[text=dense,visual=colqwen,quota=5/5] | +0.6797 | — | dense + ColQwen over images + balanced 5/5 |
| cell_recall@10[text=dense,visual=rrf,quota=7/3] | +0.6682 | — | dense + BM25+BGE RRF over VLM descriptions + official 7/3 |
| cell_recall@10[text=dense,visual=rrf,quota=5/5] | +0.6971 | — | dense + BM25+BGE RRF over VLM descriptions + balanced 5/5 |
| cell_recall@10[text=rrf,visual=colqwen,quota=7/3] | +0.6649 | — | RRF(bm25,dense) + ColQwen over images + official 7/3 |
| cell_recall@10[text=rrf,visual=colqwen,quota=5/5] | +0.6927 | — | RRF(bm25,dense) + ColQwen over images + balanced 5/5 |
| cell_recall@10[text=rrf,visual=rrf,quota=7/3] | +0.6794 | — | RRF(bm25,dense) + BM25+BGE RRF over VLM descriptions + official 7/3 |
| cell_recall@10[text=rrf,visual=rrf,quota=5/5] | +0.7101 | — | RRF(bm25,dense) + BM25+BGE RRF over VLM descriptions + balanced 5/5 |
| total_E_to_all_three@10 | +0.0564 | [+0.0427, +0.0704] * | E (paper-style) -> all three changed |
| main_effect: text branch: BGE-small dense -> BM25+BGE RRF | +0.0121 | [+0.0065, +0.0177] * | text branch: BGE-small dense -> BM25+BGE RRF |
| main_effect: visual branch: ColQwen over images -> BM25+BGE RRF over VLM descriptions | +0.0160 | [+0.0047, +0.0265] * | visual branch: ColQwen over images -> BM25+BGE RRF over VLM descriptions |
| main_effect: modality quota: official -> balanced | +0.0283 | [+0.0207, +0.0359] * | modality quota: official -> balanced |
| interaction_residual | +0.0000 | — | total minus the sum of main effects; ~0 means additive |
| one_at_a_time: text branch only | +0.0112 | [+0.0054, +0.0173] * | vs E (paper-style) |
| one_at_a_time: visual branch only | +0.0145 | [+0.0026, +0.0262] * | vs E (paper-style) |
| one_at_a_time: quota only | +0.0260 | [+0.0170, +0.0352] * | vs E (paper-style) |
| cell_recall@20[text=dense,visual=colqwen,quota=12/8] | +0.7862 | — | dense + ColQwen over images + official 12/8 |
| cell_recall@20[text=dense,visual=colqwen,quota=10/10] | +0.7946 | — | dense + ColQwen over images + balanced 10/10 |
| cell_recall@20[text=dense,visual=rrf,quota=12/8] | +0.8018 | — | dense + BM25+BGE RRF over VLM descriptions + official 12/8 |
| cell_recall@20[text=dense,visual=rrf,quota=10/10] | +0.8071 | — | dense + BM25+BGE RRF over VLM descriptions + balanced 10/10 |
| cell_recall@20[text=rrf,visual=colqwen,quota=12/8] | +0.7996 | — | RRF(bm25,dense) + ColQwen over images + official 12/8 |
| cell_recall@20[text=rrf,visual=colqwen,quota=10/10] | +0.8067 | — | RRF(bm25,dense) + ColQwen over images + balanced 10/10 |
| cell_recall@20[text=rrf,visual=rrf,quota=12/8] | +0.8152 | — | RRF(bm25,dense) + BM25+BGE RRF over VLM descriptions + official 12/8 |
| cell_recall@20[text=rrf,visual=rrf,quota=10/10] | +0.8192 | — | RRF(bm25,dense) + BM25+BGE RRF over VLM descriptions + balanced 10/10 |
| total_E_to_all_three@20 | +0.0331 | [+0.0225, +0.0434] * | E (paper-style) -> all three changed |
| main_effect: text branch: BGE-small dense -> BM25+BGE RRF | +0.0128 | [+0.0074, +0.0181] * | text branch: BGE-small dense -> BM25+BGE RRF |
| main_effect: visual branch: ColQwen over images -> BM25+BGE RRF over VLM descriptions | +0.0141 | [+0.0062, +0.0219] * | visual branch: ColQwen over images -> BM25+BGE RRF over VLM descriptions |
| main_effect: modality quota: official -> balanced | +0.0062 | [+0.0021, +0.0105] * | modality quota: official -> balanced |
| interaction_residual | +0.0000 | — | total minus the sum of main effects; ~0 means additive |
| one_at_a_time: text branch only | +0.0134 | [+0.0079, +0.0191] * | vs E (paper-style) |
| one_at_a_time: visual branch only | +0.0157 | [+0.0067, +0.0244] * | vs E (paper-style) |
| one_at_a_time: quota only | +0.0084 | [+0.0033, +0.0131] * | vs E (paper-style) |
| cell_recall@10[text=dense,visual=colqwen,quota=7/3] | +0.6786 | — | dense + ColQwen over images + official 7/3 |
| cell_recall@10[text=dense,visual=colqwen,quota=5/5] | +0.7039 | — | dense + ColQwen over images + balanced 5/5 |
| cell_recall@10[text=dense,visual=rrf,quota=7/3] | +0.6932 | — | dense + BM25+BGE RRF over VLM descriptions + official 7/3 |
| cell_recall@10[text=dense,visual=rrf,quota=5/5] | +0.7213 | — | dense + BM25+BGE RRF over VLM descriptions + balanced 5/5 |
| cell_recall@10[text=rrf,visual=colqwen,quota=7/3] | +0.6890 | — | RRF(bm25,dense) + ColQwen over images + official 7/3 |
| cell_recall@10[text=rrf,visual=colqwen,quota=5/5] | +0.7135 | — | RRF(bm25,dense) + ColQwen over images + balanced 5/5 |
| cell_recall@10[text=rrf,visual=rrf,quota=7/3] | +0.7036 | — | RRF(bm25,dense) + BM25+BGE RRF over VLM descriptions + official 7/3 |
| cell_recall@10[text=rrf,visual=rrf,quota=5/5] | +0.7309 | — | RRF(bm25,dense) + BM25+BGE RRF over VLM descriptions + balanced 5/5 |
| total_E_to_all_three@10 | +0.0523 | [+0.0378, +0.0667] * | E (paper-style) -> all three changed |
| main_effect: text branch: BGE-small dense -> BM25+BGE RRF | +0.0100 | [+0.0039, +0.0158] * | text branch: BGE-small dense -> BM25+BGE RRF |
| main_effect: visual branch: ColQwen over images -> BM25+BGE RRF over VLM descriptions | +0.0160 | [+0.0046, +0.0264] * | visual branch: ColQwen over images -> BM25+BGE RRF over VLM descriptions |
| main_effect: modality quota: official -> balanced | +0.0263 | [+0.0183, +0.0342] * | modality quota: official -> balanced |
| interaction_residual | +0.0000 | — | total minus the sum of main effects; ~0 means additive |
| one_at_a_time: text branch only | +0.0104 | [+0.0044, +0.0163] * | vs E (paper-style) |
| one_at_a_time: visual branch only | +0.0145 | [+0.0026, +0.0267] * | vs E (paper-style) |
| one_at_a_time: quota only | +0.0252 | [+0.0165, +0.0349] * | vs E (paper-style) |
| cell_recall@20[text=dense,visual=colqwen,quota=12/8] | +0.8196 | — | dense + ColQwen over images + official 12/8 |
| cell_recall@20[text=dense,visual=colqwen,quota=10/10] | +0.8267 | — | dense + ColQwen over images + balanced 10/10 |
| cell_recall@20[text=dense,visual=rrf,quota=12/8] | +0.8353 | — | dense + BM25+BGE RRF over VLM descriptions + official 12/8 |
| cell_recall@20[text=dense,visual=rrf,quota=10/10] | +0.8393 | — | dense + BM25+BGE RRF over VLM descriptions + balanced 10/10 |
| cell_recall@20[text=rrf,visual=colqwen,quota=12/8] | +0.8297 | — | RRF(bm25,dense) + ColQwen over images + official 12/8 |
| cell_recall@20[text=rrf,visual=colqwen,quota=10/10] | +0.8357 | — | RRF(bm25,dense) + ColQwen over images + balanced 10/10 |
| cell_recall@20[text=rrf,visual=rrf,quota=12/8] | +0.8453 | — | RRF(bm25,dense) + BM25+BGE RRF over VLM descriptions + official 12/8 |
| cell_recall@20[text=rrf,visual=rrf,quota=10/10] | +0.8482 | — | RRF(bm25,dense) + BM25+BGE RRF over VLM descriptions + balanced 10/10 |
| total_E_to_all_three@20 | +0.0286 | [+0.0186, +0.0383] * | E (paper-style) -> all three changed |
| main_effect: text branch: BGE-small dense -> BM25+BGE RRF | +0.0095 | [+0.0042, +0.0146] * | text branch: BGE-small dense -> BM25+BGE RRF |
| main_effect: visual branch: ColQwen over images -> BM25+BGE RRF over VLM descriptions | +0.0141 | [+0.0063, +0.0222] * | visual branch: ColQwen over images -> BM25+BGE RRF over VLM descriptions |
| main_effect: modality quota: official -> balanced | +0.0050 | [+0.0009, +0.0095] * | modality quota: official -> balanced |
| interaction_residual | -0.0000 | — | total minus the sum of main effects; ~0 means additive |
| one_at_a_time: text branch only | +0.0100 | [+0.0044, +0.0157] * | vs E (paper-style) |
| one_at_a_time: visual branch only | +0.0157 | [+0.0069, +0.0246] * | vs E (paper-style) |
| one_at_a_time: quota only | +0.0071 | [+0.0021, +0.0121] * | vs E (paper-style) |
| holm[selfbuilt/k=10] text branch: BGE-small dense -> BM25+BGE RRF | +0.0121 | [+0.0065, +0.0177] * | text branch: BGE-small dense -> BM25+BGE RRF |
| holm[selfbuilt/k=10] visual branch: ColQwen over images -> BM25+BGE RRF over VLM descriptions | +0.0160 | [+0.0047, +0.0265] * | visual branch: ColQwen over images -> BM25+BGE RRF over VLM descriptions |
| holm[selfbuilt/k=10] modality quota: official -> balanced | +0.0283 | [+0.0207, +0.0359] * | modality quota: official -> balanced |
| holm[selfbuilt/k=20] text branch: BGE-small dense -> BM25+BGE RRF | +0.0128 | [+0.0074, +0.0181] * | text branch: BGE-small dense -> BM25+BGE RRF |
| holm[selfbuilt/k=20] visual branch: ColQwen over images -> BM25+BGE RRF over VLM descriptions | +0.0141 | [+0.0062, +0.0219] * | visual branch: ColQwen over images -> BM25+BGE RRF over VLM descriptions |
| holm[selfbuilt/k=20] modality quota: official -> balanced | +0.0062 | [+0.0021, +0.0105] * | modality quota: official -> balanced |
| holm[canonical/k=10] text branch: BGE-small dense -> BM25+BGE RRF | +0.0100 | [+0.0039, +0.0158] * | text branch: BGE-small dense -> BM25+BGE RRF |
| holm[canonical/k=10] visual branch: ColQwen over images -> BM25+BGE RRF over VLM descriptions | +0.0160 | [+0.0046, +0.0264] * | visual branch: ColQwen over images -> BM25+BGE RRF over VLM descriptions |
| holm[canonical/k=10] modality quota: official -> balanced | +0.0263 | [+0.0183, +0.0342] * | modality quota: official -> balanced |
| holm[canonical/k=20] text branch: BGE-small dense -> BM25+BGE RRF | +0.0095 | [+0.0042, +0.0146] * | text branch: BGE-small dense -> BM25+BGE RRF |
| holm[canonical/k=20] visual branch: ColQwen over images -> BM25+BGE RRF over VLM descriptions | +0.0141 | [+0.0063, +0.0222] * | visual branch: ColQwen over images -> BM25+BGE RRF over VLM descriptions |
| holm[canonical/k=20] modality quota: official -> balanced | +0.0050 | [+0.0009, +0.0095] * | modality quota: official -> balanced |
| n_significant_raw | 12.0000 | — | raw 95% intervals excluding 0 |
| n_significant_holm | 12.0000 | — | surviving Holm at alpha=0.05 |

**限制**：这是**内部组件归因**，不是外部泛化验证：固定配置、单一 benchmark、且该 benchmark 已被本项目用于挑选方法。视觉因子同时换了表示（像素→VLM 文字）与检索器数量（单模型→双模型融合），因此必须整条命名为 visual branch，不能简称为表示效应。

<sub>逐题结果与 manifest：`artifacts/runs/20260831T154055Z_retrieval/experiments/E30`</sub>

## E35　路由的天花板：tie-aware oracle 与匹配预算的置换对照

**状态**：跳过　（本实验没有 replay 安全的命令（其命令会重建产物））　耗时 0.0s
- **问什么**：在训练任何路由器之前——逐题挑检索动作到底有没有可学的空间？表观上界里有多少只是 tie 和动作配比造成的假象？在只花一半 CPU 预算的动作集合里，完美选择能不能打过静态 RRF？
- **怎么做**：router.actions 复用 eval_stack_v2.build（keep_scores=True）缓存逐题的 12 个动作 × recall × 成本；router.tie_audit 在每个预算子空间上报最优固定动作、tie-aware oracle、保配比的置换对照，并按文档 cluster bootstrap 给区间。
- **指标含义**：oracle 与最优固定动作之差是表观空间；与置换对照之差扣掉了动作配比带来的部分；约束下界取两者中更强的那个。预算是 (cpu pass, gpu pass) 一对上限，两种货币不相加。
- **统计单位**：document（bootstrap 按此重采样）

- **限制**：exploratory：该切分自 E9 起被反复观察并用于挑方法。配额固定为 BALANCED_QUOTA，--include-quota 可展开为检索器 × 配额的联合空间，但配额是免费的，那只是空间上界而不是预算问题。

## E37　静态提升按题型切片：增益集中在纯视觉题，且只在 k=10

**状态**：跳过　（本实验没有 replay 安全的命令（其命令会重建产物））　耗时 0.0s
- **问什么**：E27 的 +0.061 到底落在谁身上？proposal Experiment 2 要求按题型分报，那五类在 MMDocRAG 上还剩几类可评？「某一类显著、另一类不显著」能不能当成异质性证据？
- **怎么做**：复用 nested_cv 的折外选择（文档分组 5 折，全语料选一次），再把已算好的折外差值向量按三种划分切片：证据模态、gold 跨页与否、语料自带的 question_type。每个切片按文档 cluster bootstrap 求区间；16 个切片检验为一个 Holm 家族，4 个对照检验为另一个。
- **指标含义**：切片检验回答「这一类里提升还在不在」；对照检验回答「提升是否依赖这一类」——后者才是异质性问题，前者两格的显著性差异不能替代它。
- **统计单位**：document（bootstrap 按此重采样）

- **限制**：exploratory：该切分自 E9 起被反复观察并用于挑方法。**proposal Experiment 2 的五类里有两类在 MMDocRAG evaluation split 上无法评价**：pure text 只有 1 题（n=1，无区间可言），unanswerable 一题都没有（每题都带 gold 证据）。这是 benchmark 的属性，不是分析的缺口，写报告时必须照此说明而不能假装跑了五类。question_type 里 Inferential/Procedural/Causal/Application-based 四类均低于 100 题或 20 篇的阈值，只描述不检验。

## E38　RQ1b 的 R² 目标问错了：完美预测本身也只值 +0.023

**状态**：跳过　（本实验没有 replay 安全的命令（其命令会重建产物））　耗时 0.0s
- **问什么**：proposal 给 RQ1b 设了一个 R² 目标，并点名三个未试的特征源（视觉检索器分数、模型内部表示、LLM 证据充分性判断）。E23 把 R² 从 −0.155 抬到 +0.136 就停住了，只说「分配收益仍是 0~2%」。那么究竟是 R² 太低所以值得换特征源，还是 R² 到收益的映射本身就是平的？
- **怎么做**：复用 reflect_alloc 的两段式召回矩阵与真实 visual_share。对每个目标 R² 用二分法反解噪声标准差（按裁剪后的实测 R²），共同随机数生成 200 组预测，收缩系数在测试集上取最优，再按文档 cluster bootstrap 给区间。
- **指标含义**：每一行是「精度达到该 R² 的预测器最好能买到多少」，是上界不是预报：合成预测器无偏、误差与真值独立，且收缩系数在测试集上选。
- **统计单位**：document（bootstrap 按此重采样）

- **限制**：exploratory：该切分自 E9 起被反复观察并用于挑方法。合成预测器的误差与真值独立且无偏，真实 ridge 会向训练均值收缩、误差与真值相关，因此在同一 R² 下**严格更差**——这条曲线是上界不是预报。收缩系数在测试集上选，任何可部署系统都做不到，同样是为了取上界。结论只覆盖 RQ1b 的配额分配决策，不能外推到 E36 的升级决策。

---
`*` 表示 95% 置信区间不跨 0。区间下界贴近 0 时不要写「显著」。
