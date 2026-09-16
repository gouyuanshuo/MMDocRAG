# 运行报告 · 20260905T073315Z_cached

- 套件：`cached`　离线：True　允许 API：False
- 生成时间（UTC）：2026-09-05 07:56:42
- 代码 commit：`4f8f9ddf0d9ea7b98f19356c5917ee0f7c62729b`　工作区脏：True
- **source fingerprint：`f95fef8666e8971d`**（72 个源文件 + 注册表快照的哈希）　清单：`artifacts/runs/20260905T073315Z_cached/source_manifest.json`
- **source bundle：`artifacts/runs/20260905T073315Z_cached/source_bundle.zip`**（72 个文件，343955 字节，sha256 `322fad5c2c7090f5d37e28096b313a9e02cca073485f5816ad98cfc0a616fb92`）——**这是本次源码的最终快照**
- 工作区补丁：`artifacts/runs/20260905T073315Z_cached/source.patch`（只含 **Git 已跟踪**文件的改动；本仓库多数源码未被跟踪，因此 patch 单独**不能**还原本次运行，须叠加 bundle）
- 重建测试：**pass** 72/72 个文件哈希逐字节命中（隔离目录 `artifacts/test-runs/20260905T073315Z_cached-reconstruct/tree`）
- 复现源码：`python -m expkit.source reconstruct --run 20260905T073315Z_cached`（git archive → git apply → 解压 bundle → 重算全部哈希）
- 实验状态：已运行 14，已运行（仅日志） 22

> 本报告中的每个数字都取自本次运行落盘的 `metrics.json`，不复制 `experiments.py` 里的历史文字。标记为「已运行（仅日志）」的实验尚未接入结构化输出，其数字请看对应的 `stdout.log`，不要从这里引用。

## E1　复现锚点

**状态**：已运行（仅日志）　耗时 23.5s
- **问什么**：官方评测代码是否与论文公布的数字自洽？
- **怎么做**：用仓库内已发布的 response 文件重算官方 17 项指标，不调用任何模型。
- **指标含义**：逐位命中论文公布的数字即代表本地评分口径与论文自洽。
- **统计单位**：question（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260905T073315Z_cached/experiments/E1/stdout.log`

- **限制**：这是评测复算，不是完整实验复现；没有重跑检索器，也没有重新调用模型。

## E2　评测脚本的静默截断缺陷

**状态**：已运行（仅日志）　耗时 14.1s
- **问什么**：断点续跑产生的部分结果会不会被静默地在更少样本上求均值？
- **怎么做**：按 q_id join 替换 zip()，并显式打印共同样本数。
- **指标含义**：覆盖率 < 100% 时必须报错或显式声明，而不是静默在少数样本上求均值。
- **统计单位**：question（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260905T073315Z_cached/experiments/E2/stdout.log`

- **限制**：只能说明已发布 judge artifacts 无法构造同底比较，不能推断作者内部流程。

## E3　工程可复现性

**状态**：已运行（仅日志）　耗时 0.1s
- **问什么**：仓库能否在本机复现？
- **怎么做**：检查 manifest 模块存在且可导入。
- **指标含义**：基础设施可用性检查，不产生实验数字。
- **统计单位**：question（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260905T073315Z_cached/experiments/E3/stdout.log`

- **限制**：这是工程整改，不是方法贡献。

## E4　局部 quote 标签不是身份，q_id 也不是主键

**状态**：已运行　耗时 3.7s
- **问什么**：text5 / image7 这样的局部编号能否当全局 ID？
- **怎么做**：构建 canonical evidence 数据层，用 (doc,page,layout) 生成稳定证据身份。
- **指标含义**：局部 quote 编号是位置不是身份；canonical ID 才能跨设置比较。
- **统计单位**：document（bootstrap 按此重采样）

**配置**：—

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| n_questions | 4055.0000 | — |  |
| n_documents | 223.0000 | — |  |
| n_gold_total | 21978.0000 | — |  |
| n_gold_mapped | 21978.0000 | — |  |
| n_gold_dropped | +0.0000 | — |  |
| gold_mapping_rate | 1.0000 | — |  |

**限制**：不要把 answer_interleaved 里的局部编号当成跨设置固定的答案文本。

<sub>逐题结果与 manifest：`artifacts/runs/20260905T073315Z_cached/experiments/E4`</sub>

## E5　Gate 1 — gold 全部可映射

**状态**：已运行　耗时 3.0s
- **问什么**：所有 gold quote 能否映射回 canonical evidence？
- **怎么做**：构建五张表并做往返检查。
- **指标含义**：100% 指官方两档候选可归一到统一证据层。
- **统计单位**：document（bootstrap 按此重采样）

**配置**：—

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| n_questions | 4055.0000 | — |  |
| n_documents | 223.0000 | — |  |
| n_gold_total | 21978.0000 | — |  |
| n_gold_mapped | 21978.0000 | — |  |
| n_gold_dropped | +0.0000 | — |  |
| gold_mapping_rate | 1.0000 | — |  |

**限制**：100% 是官方处理结果之间的映射，不代表能映射到任意自建 chunk。

<sub>逐题结果与 manifest：`artifacts/runs/20260905T073315Z_cached/experiments/E5`</sub>

## E6　Gate 2 — 自建 chunk 能否文本匹配回官方 gold

**状态**：已运行（仅日志）　耗时 30.7s
- **问什么**：自己切的 chunk 能不能承载官方 gold？
- **怎么做**：字符 8-gram 覆盖替代精确子串匹配。
- **指标含义**：重新切 chunk 后 gold 仍可评价的比例。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260905T073315Z_cached/experiments/E6/stdout.log`

- **限制**：未映射项必须计为 miss；阈值变化要做敏感性报告。

## E7　全语料 OCR

**状态**：已运行　耗时 1.9s
- **问什么**：没有文本层的页面能否救回？
- **怎么做**：RapidOCR 扫描低文本页（<100 字符），与原文本层拼接。
- **指标含义**：OCR 后仍无可用文本的页数，衡量文本索引的可达性。
- **统计单位**：document（bootstrap 按此重采样）

**配置**：—

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| n_pages | 14763.0000 | — |  |
| n_documents | 220.0000 | — |  |
| pages_with_zero_raw_chars_before | 1486.0000 | — |  |
| pages_with_zero_raw_chars_after | 49.0000 | — |  |
| cached_ocr_pages | 1983.0000 | — |  |

**限制**：约 93 分钟。OCR 能找出文字，不等于理解图表关系。

<sub>逐题结果与 manifest：`artifacts/runs/20260905T073315Z_cached/experiments/E7`</sub>

## E8　oracle 增益不是机会，它是测量噪声的产物

**状态**：已运行（仅日志）　耗时 0.2s
- **问什么**：逐题在两种模态间取较好者，能得到多少增益？
- **怎么做**：计算逐题 oracle，并用两个同模态不同模型的系统做参照水平。
- **指标含义**：oracle 增益必须减去同族对照才是真实可路由空间。
- **统计单位**：question（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260905T073315Z_cached/experiments/E8/stdout.log`

- **限制**：oracle 仍可作上界，但必须配排列对照并使用 regret。

## E9　模态路由不可学

**状态**：已运行（仅日志）　耗时 7.7s
- **问什么**：能否只看问题就判断这题该用图片还是文字描述？
- **怎么做**：19 个模型的成对结果上训练轻量分类器，检查 AUC、kappa 与跨模型迁移。
- **指标含义**：kappa≈0 表示不同模型对「这题该用哪种输入」几乎不一致。
- **统计单位**：question（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260905T073315Z_cached/experiments/E9/cmd0/stdout.log`

- **限制**：不能写成「该属性不存在」或「所有 Router 都不可能」。

## E10　模态选择的成本-质量表

**状态**：已运行（仅日志）　耗时 0.8s
- **问什么**：多模态输入值不值它的 token？
- **怎么做**：比较同一模型 pure-text/multimodal 的 F1、token 与 Pareto 前沿。
- **指标含义**：每换 1 分 F1 需要多付的输入 token，provider-neutral。
- **统计单位**：question（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260905T073315Z_cached/experiments/E10/stdout.log`

- **限制**：Gemini 图片 token 未计入；美元价格未核验，跨供应商成本不可直接比。

## E11　泄漏探针的一个自查 bug

**状态**：已运行（仅日志）　耗时 2.1s
- **问什么**：按 gold 模态路由（需要答案）能否胜过固定策略？
- **怎么做**：修正 evidence 类型识别后重跑泄漏探针。
- **指标含义**：原探针只识别 table，修正后覆盖全部视觉类型。
- **统计单位**：question（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260905T073315Z_cached/experiments/E11/stdout.log`

- **限制**：这是 bug 修复，结论随之改变。

## E12　我自己的 OCR 消解了我自己的立论

**状态**：已运行（仅日志）　耗时 0.2s
- **问什么**：有多少 gold 落在文本检索够不着的地方？
- **怎么做**：在补 OCR 前后分别重算 gold 证据的文本可达性。
- **指标含义**：补 OCR 后从 12.1% 降到 0.7%，原「结构性不可见」论据被消解。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260905T073315Z_cached/experiments/E12/cmd0/stdout.log`

- **限制**：OCR 后文本可达不代表视觉关系已被正确理解。

## E13　页粒度上文本检索对视觉证据没有劣势

**状态**：已运行（仅日志）　耗时 2.3s
- **问什么**：页粒度上视觉 gold 是不是更难被文本检索找到？
- **怎么做**：以整页为证据单元比较文本 gold 与视觉 gold 的召回。
- **指标含义**：页粒度上两类 gold 差距很小，因为图与周围文字捆在一起。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260905T073315Z_cached/experiments/E13/stdout.log`

- **限制**：找到正确页不等于找到图中正确区域。

## E14　模态信号是粒度依赖的

**状态**：已运行（仅日志）　耗时 1.9s
- **问什么**：模态差距为什么在页粒度上消失？
- **怎么做**：以细粒度 quote/region 为证据单元重做同一比较。
- **指标含义**：模态效应是粒度依赖的：quote 级才显现交叉。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260905T073315Z_cached/experiments/E14/stdout.log`

- **限制**：报告任何模态结论都必须同时说明证据粒度。

## E15　「图片 quote 更好检索」是池组成的产物

**状态**：已运行（仅日志）　耗时 2.5s
- **问什么**：图片 quote 更容易被检索，是因为 VLM 描述与问题词汇对齐吗？
- **怎么做**：控制 quote 长度并分解文字/图片池规模的贡献。
- **指标含义**：+0.080 的表观优势在长度匹配后翻转为 −0.014。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260905T073315Z_cached/experiments/E15/stdout.log`

- **限制**：池级分解是描述性诊断，不替代完整对照语料实验。

## E16　检索器交叉：符号翻转，四个 k 全部一致

**状态**：已运行（仅日志）　耗时 117.4s
- **问什么**：BM25 与 dense 的相对优劣是否随证据模态变化？
- **怎么做**：同一候选池上按 gold 类型比较 BM25 与 BGE 的逐证据召回。
- **指标含义**：符号随证据类型翻转，说明存在值得融合的词法—语义互补性。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260905T073315Z_cached/experiments/E16/stdout.log`

- **限制**：证据条目层 ±0.09 的效应聚合到整题会缩小。

## E17　二元检索器路由：结论已被正确的标签推翻一半

**状态**：已运行（仅日志）　耗时 39.6s
- **问什么**：逐题在 BM25 与 dense 之间二选一，能否胜过固定策略？
- **怎么做**：以逐题 recall(Dense)−recall(BM25) 为标签和权重重新训练路由器。
- **指标含义**：对固定 +0.016（CI 跨 0），对静态 RRF −0.0279（CI 不跨 0）。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260905T073315Z_cached/experiments/E17/cmd0/stdout.log`

- **限制**：旧 E17 用 gold 模态标签写死映射，只能否证那一条人工策略。

## E18　VLM 描述 vs 裁剪 OCR：+0.42 recall

**状态**：已运行（仅日志）　耗时 229.5s
- **问什么**：图表证据用 VLM 描述还是用裁剪 OCR 来检索？
- **怎么做**：同一图片池、同一 BM25 下比较 VLM 描述与裁剪 OCR 两种文字表示。
- **指标含义**：0.791 对 0.369，差距在 OCR 成功提取的子集上仍为 +0.416。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260905T073315Z_cached/experiments/E18/cmd0/stdout.log`

- **限制**：OCR 有大量空/不完整结果；不能把全部差距断言为「视觉理解」。

## E19　自适应预算分配：上界远小于原报数字

**状态**：已运行（仅日志）　耗时 32.1s
- **问什么**：逐题分配文本/图片配额，有多少可争取的空间？
- **怎么做**：计算 21 种配额的逐题 Recall 曲线，审计并列最优，改用 oracle−best-fixed regret。
- **指标含义**：真实 regret 上界 0.069/0.074；约 79% 问题固定配额已最优。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260905T073315Z_cached/experiments/E19/cmd0/stdout.log`

- **限制**：原 +0.173~+0.179 受 argmax 恒取最小并列索引影响，已作废。

## E20　真实规模自建池上复现 E19

**状态**：已运行（仅日志）　耗时 28.0s
- **问什么**：E19 的结论是不是池偏差造成的？
- **怎么做**：重建更大的文本 chunk 池，保持同一 QA、gold 与图片侧重跑。
- **指标含义**：方向一致说明结论对文本池规模有一定稳健性。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260905T073315Z_cached/experiments/E20/stdout.log`

- **限制**：不是独立复现；视觉池仍相同且不完整。

## E21　瓶颈收敛成一个可量化目标

**状态**：已运行（仅日志）　耗时 27.9s
- **问什么**：外部报告提出的比例分配规则管用吗？
- **怎么做**：以 gold 视觉占比为目标训练回归并评价实际 Recall 增益。
- **指标含义**：R² 提升不一定转化为检索收益。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260905T073315Z_cached/experiments/E21/stdout.log`

- **限制**：visual share 是 gold 派生的诊断目标，不等同于最优行动。

## E23　高维特征一直在埋掉低维真信号

**状态**：已运行（仅日志）　耗时 60.5s
- **问什么**：二次反思能否预测该用多少视觉配额？
- **怎么做**：用首轮检索结果反射式地重新分配配额，两个池分别跑。
- **指标含义**：预测目标改善不一定转化为检索收益。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260905T073315Z_cached/experiments/E23/cmd0/stdout.log`

- **限制**：输入信号弱、样本少且目标平坦。

## E24　ColQwen2 在本项目的池规模下不值它的 GPU 成本

**状态**：已运行　耗时 3.0s
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

<sub>逐题结果与 manifest：`artifacts/runs/20260905T073315Z_cached/experiments/E24`</sub>

## E25　粒度 × 预算：两个轴给出完全相反的排序

**状态**：已运行（仅日志）　耗时 158.3s
- **问什么**：证据粒度能否改善质量与上下文成本的平衡？
- **怎么做**：按 target-chars 建多档语料，分别在固定 top-k 与固定 word-like 预算下比较。
- **指标含义**：固定 top-k 会把粗 chunk 携带的额外上下文当成免费收益。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260905T073315Z_cached/experiments/E25/cmd0/stdout.log`

- **限制**：预算单位是正则 word-like token，不是 LLM BPE；仅覆盖文本 gold 与 BM25。

## E26　small-to-big 被证伪；细粒度优势一半是预算量化损失

**状态**：已运行（仅日志）　耗时 66.7s
- **问什么**：用细 chunk 排序、返回其粗 parent，能否兼得两者？
- **怎么做**：比较 prefix-stop 与 greedy-skip 两种预算装填规则。
- **指标含义**：早期正增益约一半来自「遇到塞不下就停止」的量化损失。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260905T073315Z_cached/experiments/E26/cmd0/stdout.log`

- **限制**：仅覆盖特定档位、BM25 与文本证据，不能封闭整个 RQ3。

## E27　静态检索配置的改进

**状态**：已运行　耗时 43.2s
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
| recall_surrogate_A | +0.6462 | — | local dense surrogate, local paper-style quota |
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
| recall_surrogate_A | +0.7823 | — | local dense surrogate, local paper-style quota |
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
| recall_surrogate_A | +0.6712 | — | local dense surrogate, local paper-style quota |
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
| recall_surrogate_A | +0.8157 | — | local dense surrogate, local paper-style quota |
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

<sub>逐题结果与 manifest：`artifacts/runs/20260905T073315Z_cached/experiments/E27/cmd0`</sub>

## E28　复现性与结论边界审计

**状态**：已运行（仅日志）　耗时 4.8s
- **问什么**：已发布的结论有哪些超出了证据？
- **怎么做**：document-grouped 外层 CV，内层在训练折上重选检索器与配额，每题由未参与其配置选择的折评分。
- **指标含义**：无脚本内选择泄漏的 Recall；仍是 internal OOF，不是外部确认。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260905T073315Z_cached/experiments/E28/cmd0/stdout.log`

- **限制**：并非严格双层 inner-CV；方法空间此前已用同一 2,000 题开发，k=20 时各折选择不稳定。

## E29　端到端：检索改进能否传导到生成质量

**状态**：已运行　耗时 16.8s
- **问什么**：k=10 上 +0.054 的检索优势，能否变成 quote-selection F1 的提升？
- **怎么做**：把两种检索配置的 top-k 写成官方 schema，用同一模型同一批题配对生成；eval_e29_paired.py 复用 eval_all 的 extract_citations/get_scores 算逐题 F1，按文档聚类做配对 bootstrap（B=4000）。
- **指标含义**：未检索到的 gold 用哨兵 id 计入分母，因此 F1 对检索质量敏感。主结果是配对差 +2.90 F1，CI [+1.01,+4.77] 不跨 0；两个绝对值本身不可与论文比较。
- **统计单位**：document（bootstrap 按此重采样）

**配置**：k=10　bootstrap=4000

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| final_f1_paper | 55.2133 | — | dense text + ColQwen visual, quota 7/3 (closest local paper-style config) |
| final_f1_ours | 58.1124 | — | RRF text + RRF visual, quota 4/6 (the configuration nested CV selected) |
| delta_final_f1[ours - paper] | 2.8990 | [+1.0147, +4.7713] * | paired difference; same questions, gold, model and prompt -- only the retrieved candidate block differs |
| delta_final_f1_question_bootstrap | 2.8990 | [+0.9351, +4.9859] * | WRONG SAMPLING UNIT, recorded only as a contrast. Do not cite. On this data it is not the narrower of the two, so it is wrong for the reason that questions nest in documents -- not for being over-confident. |
| questions_better | 210.0000 | — |  |
| questions_worse | 156.0000 | — |  |
| questions_equal | 234.0000 | — |  |

**限制**：BLEU/ROUGE 在此无效不可报告。gemini-3.6-flash 不在论文模型表里，因此绝对 F1 不可与论文任何一行比较；有效的只有两臂的配对比较。成本口径：2026-08-29 已对照官方定价页核验并写入 router/prices.json（标准付费层 $0.75/Mtok 输入、$3.75/Mtok 输出，verified=true）。此前曾用 gemini-2.0-flash 的未核验价 $0.10/$0.40 代算，输入低估 7.5 倍、输出低估 9.4 倍——价格表里没有该模型时，正确做法是不报美元，而不是拿最像的一条顶上。

<sub>逐题结果与 manifest：`artifacts/runs/20260905T073315Z_cached/experiments/E29/cmd2`</sub>

## E30　归因消融：+0.054 究竟来自哪个组件

**状态**：已运行　耗时 21.5s
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

<sub>逐题结果与 manifest：`artifacts/runs/20260905T073315Z_cached/experiments/E30`</sub>

## E34　论文式基线：bge-large 文本检索器与完整图片池的 ColQwen 量级核对

**状态**：已运行　耗时 3.4s
- **问什么**：本项目的「论文式对照」臂，与论文实际发布的系统差在哪几项？把差得最多的那一项补上之后，先前的提升还剩多少？
- **怎么做**：fetch_model 把 bge-large 落成平铺目录并记下 revision 与逐文件 SHA-256；colqwen_index --image-source fulldisk 改从磁盘枚举文档的全部图片（13,999，63.6/篇）而非官方候选并集（6,548，29.8/篇），已在池中的图保留原 evidence_id，池外的记为 unpooled: 前缀；eval_fullpool 只算 ColQwen 的绝对图片 recall，按文档聚类 bootstrap。
- **指标含义**：核对的是**量级**而非数值相等。候选池上本项目测得 Recall@10=0.820，论文为 0.708，差距的自然解释是池小一半；把池补到论文规模后该数应当**下降**并逼近 0.708。CI 覆盖论文值只说明本地实现通过量级核查，不说明复现了论文系统。
- **统计单位**：document（bootstrap 按此重采样）

**配置**：pool=full document image pool (all images on disk)　bootstrap=4000

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| n_evaluation_questions | 2000.0000 | — |  |
| n_documents_indexed | 220.0000 | — | documents this index covers; recall is estimated on these only. With --doc-order random they are a simple random sample, so the estimate is unbiased and the CI reflects the sample size. |
| n_documents_total | 220.0000 | — |  |
| document_coverage | 1.0000 | — | 1.0 means the whole evaluation corpus was indexed |
| n_visual_gold_questions | 1995.0000 | — | questions with at least one visual gold quote |
| n_questions_without_visual_gold | 5.0000 | — | no denominator for visual recall; outside the population |
| n_visual_gold_questions_ranked | 1995.0000 | — |  |
| pool_mean_per_document | 63.9091 | — |  |
| pool_median_per_document | 31.0000 | — |  |
| n_unpooled_ranked_entries | 78396.0000 | — | ranked images that the official candidate pool never contained; their presence is what makes this index comparable to the paper and incomparable to the description-side retrievers |
| paired_full_minus_candidate_recall_at_10 | -0.0374 | [-0.0509, -0.0265] * | same documents, same gold denominator, same retriever; only the ranked pool differs. This is the effect of pool size with the document sample held fixed, and it is the reason the full-pool index was built. |
| paired_full_minus_candidate_recall_at_15 | -0.0334 | [-0.0493, -0.0218] * | same documents, same gold denominator, same retriever; only the ranked pool differs. This is the effect of pool size with the document sample held fixed, and it is the reason the full-pool index was built. |
| paired_full_minus_candidate_recall_at_20 | -0.0359 | [-0.0542, -0.0225] * | same documents, same gold denominator, same retriever; only the ranked pool differs. This is the effect of pool size with the document sample held fixed, and it is the reason the full-pool index was built. |
| recall@10_colqwen_fullpool | +0.7824 | [+0.7466, +0.8170] * | gold image quotes retrieved in the top k of the full document image pool; gold the index never ranked counts as a miss |
| recall@10_colqwen_fullpool_quota | +0.5695 | — | alternative reading: only the 3 visual slots the paper allots at total budget 10. Reported because the paper states the quota for hybrid retrieval only, leaving the single-retriever columns ambiguous. |
| recall@15_colqwen_fullpool | +0.8558 | [+0.8233, +0.8851] * | gold image quotes retrieved in the top k of the full document image pool; gold the index never ranked counts as a miss |
| recall@15_colqwen_fullpool_quota | +0.6617 | — | alternative reading: only the 5 visual slots the paper allots at total budget 15. Reported because the paper states the quota for hybrid retrieval only, leaving the single-retriever columns ambiguous. |
| recall@20_colqwen_fullpool | +0.8935 | [+0.8635, +0.9193] * | gold image quotes retrieved in the top k of the full document image pool; gold the index never ranked counts as a miss |
| recall@20_colqwen_fullpool_quota | +0.7499 | — | alternative reading: only the 8 visual slots the paper allots at total budget 20. Reported because the paper states the quota for hybrid retrieval only, leaving the single-retriever columns ambiguous. |

**限制**：**当前限制**：全池索引已完成，但它只让 ColQwen 的**图片** recall 与论文可比。论文从未说明视觉检索器如何排文本 quote，其 text 列（28.5/33.7/36.0）不可复现，任何数字都不应与之并列。**仍然不能写「优于论文配置」**——可写的是「相对最接近论文的本地对照」，即配额、模态分工、检索器族名对齐，而版本与解析流水线不可确定；本次结果恰恰把这条纪律从告诫变成了实测：池规模只解释了 33% 的差距，剩下的差异**无法从发表物里定位**。描述分支上全池仍未做，需为 8,943 张图补 VLM 描述，属付费项，未批准。

**以下为已作废的历史记录，保留以说明这条结论是怎么来的，其中每一句「未验证 / 受阻」都已不再成立**：**（历史）ColQwen 全池索引未完成：只索引了 5/220 篇文档**（2026-08-31 复核仍是 5/220，39 题、124 图，其中 96 条 unpooled；阻塞原因是 GPU 被用户自己的 Ollama 占用 6832/8188 MiB 且不能停，ColQwen2 的 4.49 GB 放不下。另发现 colqwen_scores_fullpool.ckpt 是空目录而非检查点文件，续跑粒度只到文档级，文档内被打断需整篇重跑），因此 eval_fullpool.py 尚无可报告的结果，「补齐池后 Recall@10 应从 0.820 降向论文的 0.708」这一预测当时未验证（**已于 2026-09-01 验证并证伪**：降了，但只降了三分之一）。受阻于资源而非正确性：ColQwen2 权重需 4.49 GB，而本机 8.19 GB 显存中 Ollama 的 llama-server.exe 持有 3.26 GB，余下的放不下大图激活；全量实测需 5–9 小时 GPU。机制已就绪且可无人值守续跑：--doc-order random 使任何停止点都是文档的简单随机样本，文档内检查点让 660 张图的文档也能跨窗口续跑，eval_fullpool 只在已索引文档上估计而不把未索引文档的 gold 计为 miss。即使全部完成也**不能**写「优于论文配置」。可写的是「相对最接近论文的本地对照」，即配额、模态分工、检索器族名对齐，而版本与解析流水线不可确定。若全池 recall 的 CI 覆盖论文值，只能声明**本地实现通过量级核查**，这是实现验证，不是复现论文系统。要让描述分支也上全池，需为 8,943 张图补 VLM 描述，属付费项，未批准。

<sub>逐题结果与 manifest：`artifacts/runs/20260905T073315Z_cached/experiments/E34/cmd1`</sub>

## E35　路由的天花板：tie-aware oracle 与匹配预算的置换对照

**状态**：已运行　耗时 17.2s
- **问什么**：在训练任何路由器之前——逐题挑检索动作到底有没有可学的空间？表观上界里有多少只是 tie 和动作配比造成的假象？在只花一半 CPU 预算的动作集合里，完美选择能不能打过静态 RRF？
- **怎么做**：router.actions 复用 eval_stack_v2.build（keep_scores=True）缓存逐题的 12 个动作 × recall × 成本；router.tie_audit 在每个预算子空间上报最优固定动作、tie-aware oracle、保配比的置换对照，并按文档 cluster bootstrap 给区间。
- **指标含义**：oracle 与最优固定动作之差是表观空间；与置换对照之差扣掉了动作配比带来的部分；约束下界取两者中更强的那个。预算是 (cpu pass, gpu pass) 一对上限，两种货币不相加。
- **统计单位**：document（bootstrap 按此重采样）

**配置**：pool=selfbuilt　k=10　seed=20260825　bootstrap=4000　quota=5/5

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| recall_best_fixed | +0.7101 | — |  |
| recall_static_rrf | +0.7101 | — |  |
| recall_oracle | +0.7962 | — |  |
| recall_permuted_tieaware | +0.6844 | — |  |
| recall_permuted_argmax | +0.6756 | — |  |
| frac_all_actions_identical | +0.4785 | — |  |
| frac_all_actions_recall1 | +0.3340 | — |  |
| frac_fixed_already_optimal | +0.7695 | — |  |
| mean_tied_optima | 8.5710 | — |  |
| cpu_passes_cheapest_optimal_cpu_only | 2.0615 | — |  |
| cpu_passes_static_rrf | 4.0000 | — |  |
| recall_oracle__cpule2_no_gpu | +0.7603 | — |  |
| recall_best_fixed__cpule2_no_gpu | +0.6880 | — |  |
| recall_permuted__cpule2_no_gpu | +0.6737 | — |  |
| oracle_minus_fixed__cpule2_no_gpu | +0.0722 | [+0.0642, +0.0804] * |  |
| recall_oracle__cpule3_no_gpu | +0.7764 | — |  |
| recall_best_fixed__cpule3_no_gpu | +0.7010 | — |  |
| recall_permuted__cpule3_no_gpu | +0.6828 | — |  |
| oracle_minus_fixed__cpule3_no_gpu | +0.0754 | [+0.0670, +0.0837] * |  |
| recall_oracle__cpule4_no_gpu | +0.7765 | — |  |
| recall_best_fixed__cpule4_no_gpu | +0.7101 | — |  |
| recall_permuted__cpule4_no_gpu | +0.6859 | — |  |
| oracle_minus_fixed__cpule4_no_gpu | +0.0664 | [+0.0579, +0.0754] * |  |
| recall_oracle__gpu=1_(colqwen_visual) | +0.7233 | — |  |
| recall_best_fixed__gpu=1_(colqwen_visual) | +0.6927 | — |  |
| recall_permuted__gpu=1_(colqwen_visual) | +0.6798 | — |  |
| oracle_minus_fixed__gpu=1_(colqwen_visual) | +0.0307 | [+0.0256, +0.0358] * |  |
| recall_oracle__unrestricted | +0.7962 | — |  |
| recall_best_fixed__unrestricted | +0.7101 | — |  |
| recall_permuted__unrestricted | +0.6844 | — |  |
| oracle_minus_fixed__unrestricted | +0.0861 | [+0.0766, +0.0962] * |  |
| oracle_minus_fixed | +0.0861 | [+0.0766, +0.0962] * |  |
| oracle_minus_permuted_argmax | +0.1205 | [+0.1013, +0.1410] * |  |
| oracle_minus_permuted_tieaware | +0.1118 | [+0.0926, +0.1320] * |  |
| fixed_minus_permuted_tieaware | +0.0257 | [+0.0021, +0.0501] * |  |
| oracle_cpule2_minus_static_rrf | +0.0502 | [+0.0413, +0.0594] * |  |
| fixed_cpule2_minus_static_rrf | -0.0220 | [-0.0317, -0.0130] * |  |
| oracle_cpule3_minus_static_rrf | +0.0663 | [+0.0578, +0.0751] * |  |
| fixed_cpule3_minus_static_rrf | -0.0091 | [-0.0171, -0.0015] * |  |
| oracle_gpu=1_minus_static_rrf | +0.0133 | [+0.0015, +0.0250] * |  |
| fixed_gpu=1_minus_static_rrf | -0.0174 | [-0.0278, -0.0062] * |  |

**配置**：pool=selfbuilt　k=20　seed=20260825　bootstrap=4000　quota=10/10

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| recall_best_fixed | +0.8192 | — |  |
| recall_static_rrf | +0.8192 | — |  |
| recall_oracle | +0.8790 | — |  |
| recall_permuted_tieaware | +0.7979 | — |  |
| recall_permuted_argmax | +0.7877 | — |  |
| frac_all_actions_identical | +0.5755 | — |  |
| frac_all_actions_recall1 | +0.4590 | — |  |
| frac_fixed_already_optimal | +0.8190 | — |  |
| mean_tied_optima | 9.2855 | — |  |
| cpu_passes_cheapest_optimal_cpu_only | 2.0320 | — |  |
| cpu_passes_static_rrf | 4.0000 | — |  |
| recall_oracle__cpule2_no_gpu | +0.8597 | — |  |
| recall_best_fixed__cpule2_no_gpu | +0.7996 | — |  |
| recall_permuted__cpule2_no_gpu | +0.7897 | — |  |
| oracle_minus_fixed__cpule2_no_gpu | +0.0601 | [+0.0521, +0.0690] * |  |
| recall_oracle__cpule3_no_gpu | +0.8673 | — |  |
| recall_best_fixed__cpule3_no_gpu | +0.8118 | — |  |
| recall_permuted__cpule3_no_gpu | +0.7973 | — |  |
| oracle_minus_fixed__cpule3_no_gpu | +0.0555 | [+0.0472, +0.0643] * |  |
| recall_oracle__cpule4_no_gpu | +0.8673 | — |  |
| recall_best_fixed__cpule4_no_gpu | +0.8192 | — |  |
| recall_permuted__cpule4_no_gpu | +0.8001 | — |  |
| oracle_minus_fixed__cpule4_no_gpu | +0.0481 | [+0.0408, +0.0553] * |  |
| recall_oracle__gpu=1_(colqwen_visual) | +0.8311 | — |  |
| recall_best_fixed__gpu=1_(colqwen_visual) | +0.8067 | — |  |
| recall_permuted__gpu=1_(colqwen_visual) | +0.7945 | — |  |
| oracle_minus_fixed__gpu=1_(colqwen_visual) | +0.0244 | [+0.0199, +0.0292] * |  |
| recall_oracle__unrestricted | +0.8790 | — |  |
| recall_best_fixed__unrestricted | +0.8192 | — |  |
| recall_permuted__unrestricted | +0.7981 | — |  |
| oracle_minus_fixed__unrestricted | +0.0598 | [+0.0514, +0.0679] * |  |
| oracle_minus_fixed | +0.0598 | [+0.0516, +0.0678] * |  |
| oracle_minus_permuted_argmax | +0.0913 | [+0.0767, +0.1060] * |  |
| oracle_minus_permuted_tieaware | +0.0810 | [+0.0665, +0.0955] * |  |
| fixed_minus_permuted_tieaware | +0.0213 | [+0.0021, +0.0406] * |  |
| oracle_cpule2_minus_static_rrf | +0.0405 | [+0.0334, +0.0478] * |  |
| fixed_cpule2_minus_static_rrf | -0.0196 | [-0.0276, -0.0115] * |  |
| oracle_cpule3_minus_static_rrf | +0.0481 | [+0.0412, +0.0555] * |  |
| fixed_cpule3_minus_static_rrf | -0.0074 | [-0.0136, -0.0013] * |  |
| oracle_gpu=1_minus_static_rrf | +0.0119 | [+0.0038, +0.0202] * |  |
| fixed_gpu=1_minus_static_rrf | -0.0125 | [-0.0200, -0.0049] * |  |

**配置**：pool=canonical　k=10　seed=20260825　bootstrap=4000　quota=5/5

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| recall_best_fixed | +0.7309 | — |  |
| recall_static_rrf | +0.7309 | — |  |
| recall_oracle | +0.8181 | — |  |
| recall_permuted_tieaware | +0.7052 | — |  |
| recall_permuted_argmax | +0.6938 | — |  |
| frac_all_actions_identical | +0.4675 | — |  |
| frac_all_actions_recall1 | +0.3480 | — |  |
| frac_fixed_already_optimal | +0.7720 | — |  |
| mean_tied_optima | 8.5160 | — |  |
| cpu_passes_cheapest_optimal_cpu_only | 2.0610 | — |  |
| cpu_passes_static_rrf | 4.0000 | — |  |
| recall_oracle__cpule2_no_gpu | +0.7829 | — |  |
| recall_best_fixed__cpule2_no_gpu | +0.7122 | — |  |
| recall_permuted__cpule2_no_gpu | +0.6935 | — |  |
| oracle_minus_fixed__cpule2_no_gpu | +0.0707 | [+0.0635, +0.0783] * |  |
| recall_oracle__cpule3_no_gpu | +0.7985 | — |  |
| recall_best_fixed__cpule3_no_gpu | +0.7218 | — |  |
| recall_permuted__cpule3_no_gpu | +0.7035 | — |  |
| oracle_minus_fixed__cpule3_no_gpu | +0.0767 | [+0.0680, +0.0849] * |  |
| recall_oracle__cpule4_no_gpu | +0.7985 | — |  |
| recall_best_fixed__cpule4_no_gpu | +0.7309 | — |  |
| recall_permuted__cpule4_no_gpu | +0.7065 | — |  |
| oracle_minus_fixed__cpule4_no_gpu | +0.0676 | [+0.0590, +0.0764] * |  |
| recall_oracle__gpu=1_(colqwen_visual) | +0.7453 | — |  |
| recall_best_fixed__gpu=1_(colqwen_visual) | +0.7135 | — |  |
| recall_permuted__gpu=1_(colqwen_visual) | +0.7005 | — |  |
| oracle_minus_fixed__gpu=1_(colqwen_visual) | +0.0318 | [+0.0267, +0.0373] * |  |
| recall_oracle__unrestricted | +0.8181 | — |  |
| recall_best_fixed__unrestricted | +0.7309 | — |  |
| recall_permuted__unrestricted | +0.7045 | — |  |
| oracle_minus_fixed__unrestricted | +0.0872 | [+0.0776, +0.0973] * |  |
| oracle_minus_fixed | +0.0872 | [+0.0776, +0.0970] * |  |
| oracle_minus_permuted_argmax | +0.1243 | [+0.1042, +0.1450] * |  |
| oracle_minus_permuted_tieaware | +0.1130 | [+0.0937, +0.1338] * |  |
| fixed_minus_permuted_tieaware | +0.0258 | [+0.0015, +0.0503] * |  |
| oracle_cpule2_minus_static_rrf | +0.0520 | [+0.0429, +0.0614] * |  |
| fixed_cpule2_minus_static_rrf | -0.0187 | [-0.0283, -0.0094] * |  |
| oracle_cpule3_minus_static_rrf | +0.0676 | [+0.0591, +0.0765] * |  |
| fixed_cpule3_minus_static_rrf | -0.0091 | [-0.0171, -0.0015] * |  |
| oracle_gpu=1_minus_static_rrf | +0.0144 | [+0.0024, +0.0268] * |  |
| fixed_gpu=1_minus_static_rrf | -0.0174 | [-0.0278, -0.0062] * |  |

**配置**：pool=canonical　k=20　seed=20260825　bootstrap=4000　quota=10/10

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| recall_best_fixed | +0.8482 | — |  |
| recall_static_rrf | +0.8482 | — |  |
| recall_oracle | +0.9079 | — |  |
| recall_permuted_tieaware | +0.8271 | — |  |
| recall_permuted_argmax | +0.8138 | — |  |
| frac_all_actions_identical | +0.5765 | — |  |
| frac_all_actions_recall1 | +0.4995 | — |  |
| frac_fixed_already_optimal | +0.8185 | — |  |
| mean_tied_optima | 9.2905 | — |  |
| cpu_passes_cheapest_optimal_cpu_only | 2.0345 | — |  |
| cpu_passes_static_rrf | 4.0000 | — |  |
| recall_oracle__cpule2_no_gpu | +0.8881 | — |  |
| recall_best_fixed__cpule2_no_gpu | +0.8318 | — |  |
| recall_permuted__cpule2_no_gpu | +0.8188 | — |  |
| oracle_minus_fixed__cpule2_no_gpu | +0.0563 | [+0.0482, +0.0651] * |  |
| recall_oracle__cpule3_no_gpu | +0.8962 | — |  |
| recall_best_fixed__cpule3_no_gpu | +0.8408 | — |  |
| recall_permuted__cpule3_no_gpu | +0.8266 | — |  |
| oracle_minus_fixed__cpule3_no_gpu | +0.0554 | [+0.0469, +0.0643] * |  |
| recall_oracle__cpule4_no_gpu | +0.8962 | — |  |
| recall_best_fixed__cpule4_no_gpu | +0.8482 | — |  |
| recall_permuted__cpule4_no_gpu | +0.8286 | — |  |
| oracle_minus_fixed__cpule4_no_gpu | +0.0479 | [+0.0408, +0.0553] * |  |
| recall_oracle__gpu=1_(colqwen_visual) | +0.8600 | — |  |
| recall_best_fixed__gpu=1_(colqwen_visual) | +0.8357 | — |  |
| recall_permuted__gpu=1_(colqwen_visual) | +0.8231 | — |  |
| oracle_minus_fixed__gpu=1_(colqwen_visual) | +0.0243 | [+0.0199, +0.0287] * |  |
| recall_oracle__unrestricted | +0.9079 | — |  |
| recall_best_fixed__unrestricted | +0.8482 | — |  |
| recall_permuted__unrestricted | +0.8271 | — |  |
| oracle_minus_fixed__unrestricted | +0.0596 | [+0.0516, +0.0679] * |  |
| oracle_minus_fixed | +0.0596 | [+0.0515, +0.0679] * |  |
| oracle_minus_permuted_argmax | +0.0940 | [+0.0815, +0.1073] * |  |
| oracle_minus_permuted_tieaware | +0.0808 | [+0.0684, +0.0936] * |  |
| fixed_minus_permuted_tieaware | +0.0211 | [+0.0022, +0.0401] * |  |
| oracle_cpule2_minus_static_rrf | +0.0399 | [+0.0327, +0.0476] * |  |
| fixed_cpule2_minus_static_rrf | -0.0164 | [-0.0244, -0.0084] * |  |
| oracle_cpule3_minus_static_rrf | +0.0479 | [+0.0408, +0.0552] * |  |
| fixed_cpule3_minus_static_rrf | -0.0074 | [-0.0136, -0.0013] * |  |
| oracle_gpu=1_minus_static_rrf | +0.0118 | [+0.0034, +0.0202] * |  |
| fixed_gpu=1_minus_static_rrf | -0.0125 | [-0.0200, -0.0049] * |  |

**限制**：exploratory：该切分自 E9 起被反复观察并用于挑方法。配额固定为 BALANCED_QUOTA，--include-quota 可展开为检索器 × 配额的联合空间，但配额是免费的，那只是空间上界而不是预算问题。

<sub>逐题结果与 manifest：`artifacts/runs/20260905T073315Z_cached/experiments/E35/cmd0`</sub>

## E36　逐题路由：GPU 决策可学，CPU 融合决策不可学

**状态**：已运行　耗时 339.8s
- **问什么**：静态 RRF 对每个 query 都付两个检索器。路由器能否用更少的检索代价达到同样的质量？
- **怎么做**：折外预测（文档分组 5 折，折内再 4 折选模型族，--features search 时连特征组一起在折内选）；按预测增益排序买升级；对照是同预算的随机分配（逐题期望精确计算而非抽样）、同预算 oracle、两个端点；8 格一个 Holm 家族。每格结果落盘可续跑。
- **指标含义**：主指标不是「比不升级好」——升级本身就多做检索。唯一能证明路由器懂 query 的是它在**同样预算**下胜过随机挑哪些 query 升级。capture = (路由器 AUC − 随机 AUC) / (oracle AUC − 随机 AUC)。
- **统计单位**：document（bootstrap 按此重采样）

**配置**：pool=both　k=0　seed=20260825　bootstrap=4000

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| recall_router [cpu/selfbuilt/k=10] | +0.6907 | — |  |
| router_minus_random [cpu/selfbuilt/k=10] | -0.0016 | [-0.0060, +0.0031] |  |
| router_minus_always_escalate [cpu/selfbuilt/k=10] | -0.0194 | [-0.0254, -0.0134] * |  |
| oracle_regret [cpu/selfbuilt/k=10] | +0.0504 | [+0.0444, +0.0568] * |  |
| budget_to_match_static [cpu/selfbuilt/k=10] | 1.0000 | — |  |
| recall_router [cpu/selfbuilt/k=20] | +0.8020 | — |  |
| router_minus_random [cpu/selfbuilt/k=20] | -0.0004 | [-0.0044, +0.0038] |  |
| router_minus_always_escalate [cpu/selfbuilt/k=20] | -0.0172 | [-0.0221, -0.0124] * |  |
| oracle_regret [cpu/selfbuilt/k=20] | +0.0387 | [+0.0326, +0.0450] * |  |
| budget_to_match_static [cpu/selfbuilt/k=20] | 1.0000 | — |  |
| recall_router [cpu/canonical/k=10] | +0.7148 | — |  |
| router_minus_random [cpu/canonical/k=10] | +0.0037 | [-0.0011, +0.0086] |  |
| router_minus_always_escalate [cpu/canonical/k=10] | -0.0162 | [-0.0219, -0.0103] * |  |
| oracle_regret [cpu/canonical/k=10] | +0.0463 | [+0.0404, +0.0527] * |  |
| budget_to_match_static [cpu/canonical/k=10] | — | — |  |
| recall_router [cpu/canonical/k=20] | +0.8337 | — |  |
| router_minus_random [cpu/canonical/k=20] | +0.0043 | [-0.0002, +0.0090] |  |
| router_minus_always_escalate [cpu/canonical/k=20] | -0.0145 | [-0.0197, -0.0093] * |  |
| oracle_regret [cpu/canonical/k=20] | +0.0339 | [+0.0283, +0.0397] * |  |
| budget_to_match_static [cpu/canonical/k=20] | 1.0000 | — |  |
| recall_router [gpu/selfbuilt/k=10] | +0.7006 | — |  |
| router_minus_random [gpu/selfbuilt/k=10] | +0.0102 | [+0.0029, +0.0176] * |  |
| router_minus_always_escalate [gpu/selfbuilt/k=10] | +0.0079 | [-0.0021, +0.0177] |  |
| oracle_regret [gpu/selfbuilt/k=10] | +0.0605 | [+0.0524, +0.0691] * |  |
| budget_to_match_static [gpu/selfbuilt/k=10] | +0.1500 | — |  |
| recall_router [gpu/selfbuilt/k=20] | +0.8105 | — |  |
| router_minus_random [gpu/selfbuilt/k=20] | +0.0073 | [+0.0022, +0.0123] * |  |
| router_minus_always_escalate [gpu/selfbuilt/k=20] | +0.0038 | [-0.0031, +0.0107] |  |
| oracle_regret [gpu/selfbuilt/k=20] | +0.0419 | [+0.0356, +0.0484] * |  |
| budget_to_match_static [gpu/selfbuilt/k=20] | +0.1000 | — |  |
| recall_router [gpu/canonical/k=10] | +0.7143 | — |  |
| router_minus_random [gpu/canonical/k=10] | +0.0015 | [-0.0053, +0.0081] |  |
| router_minus_always_escalate [gpu/canonical/k=10] | +0.0008 | [-0.0089, +0.0105] |  |
| oracle_regret [gpu/canonical/k=10] | +0.0701 | [+0.0616, +0.0785] * |  |
| budget_to_match_static [gpu/canonical/k=10] | +0.1500 | — |  |
| recall_router [gpu/canonical/k=20] | +0.8390 | — |  |
| router_minus_random [gpu/canonical/k=20] | +0.0053 | [+0.0005, +0.0100] * |  |
| router_minus_always_escalate [gpu/canonical/k=20] | +0.0033 | [-0.0034, +0.0102] |  |
| oracle_regret [gpu/canonical/k=20] | +0.0444 | [+0.0382, +0.0506] * |  |
| budget_to_match_static [gpu/canonical/k=20] | +0.1500 | — |  |
| n_significant_holm_primary | 1.0000 | — | router beats random allocation at matched budget |
| n_significant_holm_secondary | 4.0000 | — | router matches or beats always-escalate |

**配置**：pool=both　k=0　seed=20260825　bootstrap=4000

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| recall_router [cpu/selfbuilt/k=10] | +0.6966 | — |  |
| router_minus_random [cpu/selfbuilt/k=10] | +0.0044 | [-0.0004, +0.0091] |  |
| router_minus_always_escalate [cpu/selfbuilt/k=10] | -0.0134 | [-0.0198, -0.0070] * |  |
| oracle_regret [cpu/selfbuilt/k=10] | +0.0444 | [+0.0388, +0.0504] * |  |
| budget_to_match_static [cpu/selfbuilt/k=10] | — | — |  |
| recall_router [cpu/selfbuilt/k=20] | +0.8029 | — |  |
| router_minus_random [cpu/selfbuilt/k=20] | +0.0005 | [-0.0039, +0.0049] |  |
| router_minus_always_escalate [cpu/selfbuilt/k=20] | -0.0163 | [-0.0205, -0.0118] * |  |
| oracle_regret [cpu/selfbuilt/k=20] | +0.0378 | [+0.0319, +0.0438] * |  |
| budget_to_match_static [cpu/selfbuilt/k=20] | 1.0000 | — |  |
| recall_router [cpu/canonical/k=10] | +0.7141 | — |  |
| router_minus_random [cpu/canonical/k=10] | +0.0030 | [-0.0018, +0.0079] |  |
| router_minus_always_escalate [cpu/canonical/k=10] | -0.0169 | [-0.0230, -0.0109] * |  |
| oracle_regret [cpu/canonical/k=10] | +0.0470 | [+0.0409, +0.0535] * |  |
| budget_to_match_static [cpu/canonical/k=10] | — | — |  |
| recall_router [cpu/canonical/k=20] | +0.8340 | — |  |
| router_minus_random [cpu/canonical/k=20] | +0.0046 | [+0.0002, +0.0090] * |  |
| router_minus_always_escalate [cpu/canonical/k=20] | -0.0143 | [-0.0194, -0.0094] * |  |
| oracle_regret [cpu/canonical/k=20] | +0.0337 | [+0.0282, +0.0394] * |  |
| budget_to_match_static [cpu/canonical/k=20] | 1.0000 | — |  |
| recall_router [gpu/selfbuilt/k=10] | +0.6996 | — |  |
| router_minus_random [gpu/selfbuilt/k=10] | +0.0093 | [+0.0020, +0.0164] * |  |
| router_minus_always_escalate [gpu/selfbuilt/k=10] | +0.0070 | [-0.0031, +0.0170] |  |
| oracle_regret [gpu/selfbuilt/k=10] | +0.0615 | [+0.0535, +0.0700] * |  |
| budget_to_match_static [gpu/selfbuilt/k=10] | +0.1500 | — |  |
| recall_router [gpu/selfbuilt/k=20] | +0.8111 | — |  |
| router_minus_random [gpu/selfbuilt/k=20] | +0.0079 | [+0.0029, +0.0128] * |  |
| router_minus_always_escalate [gpu/selfbuilt/k=20] | +0.0044 | [-0.0035, +0.0116] |  |
| oracle_regret [gpu/selfbuilt/k=20] | +0.0413 | [+0.0350, +0.0482] * |  |
| budget_to_match_static [gpu/selfbuilt/k=20] | +0.1500 | — |  |
| recall_router [gpu/canonical/k=10] | +0.7239 | — |  |
| router_minus_random [gpu/canonical/k=10] | +0.0111 | [+0.0047, +0.0175] * |  |
| router_minus_always_escalate [gpu/canonical/k=10] | +0.0104 | [+0.0011, +0.0198] * |  |
| oracle_regret [gpu/canonical/k=10] | +0.0605 | [+0.0527, +0.0692] * |  |
| budget_to_match_static [gpu/canonical/k=10] | +0.0500 | — |  |
| recall_router [gpu/canonical/k=20] | +0.8402 | — |  |
| router_minus_random [gpu/canonical/k=20] | +0.0064 | [+0.0017, +0.0109] * |  |
| router_minus_always_escalate [gpu/canonical/k=20] | +0.0045 | [-0.0024, +0.0113] |  |
| oracle_regret [gpu/canonical/k=20] | +0.0433 | [+0.0372, +0.0495] * |  |
| budget_to_match_static [gpu/canonical/k=20] | +0.0500 | — |  |
| n_significant_holm_primary | 3.0000 | — | router beats random allocation at matched budget |
| n_significant_holm_secondary | 4.0000 | — | router matches or beats always-escalate |

**配置**：pool=selfbuilt　k=10　seed=20260825　bootstrap=4000　quota=5/5

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| recall_router | +0.6817 | — |  |
| recall_fold_wise_best_fixed | +0.6880 | — |  |
| recall_oracle_four_actions | +0.7603 | — |  |
| recall_static_rrf | +0.7101 | — |  |
| policyA_router_minus_fixed | -0.0064 | [-0.0142, +0.0019] |  |
| policyA_router_minus_static_rrf | -0.0284 | [-0.0380, -0.0184] * |  |
| policyA_oracle_regret | +0.0786 | [+0.0702, +0.0869] * |  |

**配置**：pool=selfbuilt　k=10　seed=20260825　bootstrap=4000　quota=5/5

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| recall_first_pass_only | +0.6744 | — |  |
| recall_always_escalate | +0.7101 | — |  |
| auc_router | +0.6957 | — |  |
| auc_random | +0.6922 | — |  |
| auc_oracle | +0.7331 | — |  |
| budget_to_match_static_rrf | — | — |  |
| recall_router_B000 | +0.6744 | — |  |
| recall_random_B000 | +0.6744 | — |  |
| recall_oracle_B000 | +0.6744 | — |  |
| recall_router_B005 | +0.6777 | — |  |
| recall_random_B005 | +0.6762 | — |  |
| recall_oracle_B005 | +0.7049 | — |  |
| recall_router_B010 | +0.6828 | — |  |
| recall_random_B010 | +0.6780 | — |  |
| recall_oracle_B010 | +0.7224 | — |  |
| recall_router_B015 | +0.6845 | — |  |
| recall_random_B015 | +0.6798 | — |  |
| recall_oracle_B015 | +0.7341 | — |  |
| recall_router_B020 | +0.6858 | — |  |
| recall_random_B020 | +0.6816 | — |  |
| recall_oracle_B020 | +0.7411 | — |  |
| recall_router_B025 | +0.6871 | — |  |
| recall_random_B025 | +0.6833 | — |  |
| recall_oracle_B025 | +0.7411 | — |  |
| recall_router_B030 | +0.6904 | — |  |
| recall_random_B030 | +0.6851 | — |  |
| recall_oracle_B030 | +0.7411 | — |  |
| recall_router_B035 | +0.6910 | — |  |
| recall_random_B035 | +0.6869 | — |  |
| recall_oracle_B035 | +0.7411 | — |  |
| recall_router_B040 | +0.6931 | — |  |
| recall_random_B040 | +0.6887 | — |  |
| recall_oracle_B040 | +0.7411 | — |  |
| recall_router_B045 | +0.6968 | — |  |
| recall_random_B045 | +0.6905 | — |  |
| recall_oracle_B045 | +0.7411 | — |  |
| recall_router_B050 | +0.6966 | — |  |
| recall_random_B050 | +0.6922 | — |  |
| recall_oracle_B050 | +0.7411 | — |  |
| recall_router_B055 | +0.6981 | — |  |
| recall_random_B055 | +0.6940 | — |  |
| recall_oracle_B055 | +0.7411 | — |  |
| recall_router_B060 | +0.6993 | — |  |
| recall_random_B060 | +0.6958 | — |  |
| recall_oracle_B060 | +0.7411 | — |  |
| recall_router_B065 | +0.7009 | — |  |
| recall_random_B065 | +0.6976 | — |  |
| recall_oracle_B065 | +0.7411 | — |  |
| recall_router_B070 | +0.7036 | — |  |
| recall_random_B070 | +0.6994 | — |  |
| recall_oracle_B070 | +0.7411 | — |  |
| recall_router_B075 | +0.7043 | — |  |
| recall_random_B075 | +0.7012 | — |  |
| recall_oracle_B075 | +0.7411 | — |  |
| recall_router_B080 | +0.7071 | — |  |
| recall_random_B080 | +0.7029 | — |  |
| recall_oracle_B080 | +0.7411 | — |  |
| recall_router_B085 | +0.7088 | — |  |
| recall_random_B085 | +0.7047 | — |  |
| recall_oracle_B085 | +0.7411 | — |  |
| recall_router_B090 | +0.7085 | — |  |
| recall_random_B090 | +0.7065 | — |  |
| recall_oracle_B090 | +0.7411 | — |  |
| recall_router_B095 | +0.7097 | — |  |
| recall_random_B095 | +0.7083 | — |  |
| recall_oracle_B095 | +0.7341 | — |  |
| recall_router_B100 | +0.7101 | — |  |
| recall_random_B100 | +0.7101 | — |  |
| recall_oracle_B100 | +0.7101 | — |  |
| router_minus_random_B25 | +0.0038 | [-0.0006, +0.0085] |  |
| router_minus_always_escalate_B25 | -0.0229 | [-0.0306, -0.0155] * |  |
| oracle_regret_B25 | +0.0539 | [+0.0473, +0.0607] * |  |
| router_minus_random_B50 | +0.0044 | [-0.0005, +0.0093] |  |
| router_minus_always_escalate_B50 | -0.0134 | [-0.0198, -0.0068] * |  |
| oracle_regret_B50 | +0.0444 | [+0.0387, +0.0505] * |  |
| router_minus_random_B75 | +0.0032 | [-0.0009, +0.0073] |  |
| router_minus_always_escalate_B75 | -0.0057 | [-0.0106, -0.0009] * |  |
| oracle_regret_B75 | +0.0367 | [+0.0315, +0.0421] * |  |

**限制**：exploratory：该切分自 E9 起被反复观察并用于挑方法。oracle regret 仍然很大（事先固定口径 +0.0337 ~ +0.0615，折内选口径 +0.0339 ~ +0.0701），路由器只实现了可得空间的约十分之一，**不能**写成「路由有效」，只能写成「在图片侧的升级决策上存在可学的逐题信号，且它买到的是成本而不是质量」。B=0.05~0.15 这个「追平静态系统的预算」是看着曲线读出来的，属描述性数字，不是检验。端到端生成质量未测——本条全部指标是 evidence recall，要接到 F1 需要一次配对 API 运行，未做。

<sub>逐题结果与 manifest：`artifacts/runs/20260905T073315Z_cached/experiments/E36/cmd0`</sub>

## E37　静态提升按题型切片：增益集中在纯视觉题，且只在 k=10

**状态**：已运行　耗时 15.0s
- **问什么**：E27 的 +0.061 到底落在谁身上？proposal Experiment 2 要求按题型分报，那五类在 MMDocRAG 上还剩几类可评？「某一类显著、另一类不显著」能不能当成异质性证据？
- **怎么做**：复用 nested_cv 的折外选择（文档分组 5 折，全语料选一次），再把已算好的折外差值向量按三种划分切片：证据模态、gold 跨页与否、语料自带的 question_type。每个切片按文档 cluster bootstrap 求区间；16 个切片检验为一个 Holm 家族，4 个对照检验为另一个。
- **指标含义**：切片检验回答「这一类里提升还在不在」；对照检验回答「提升是否依赖这一类」——后者才是异质性问题，前者两格的显著性差异不能替代它。
- **统计单位**：document（bootstrap 按此重采样）

**配置**：pool=selfbuilt　bootstrap=4000

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| n_questions | 2000.0000 | — | out-of-fold nested-CV selection - paper-style E |
| n_documents | 220.0000 | — | out-of-fold nested-CV selection - paper-style E |
| delta_k10_evidence_modality_cross-modal | +0.0346 | [+0.0207, +0.0491] * | out-of-fold nested-CV selection - paper-style E |
| delta_k10_evidence_modality_pure_visual | +0.1037 | [+0.0774, +0.1290] * | out-of-fold nested-CV selection - paper-style E |
| delta_k10_gold_page_span_cross-page | +0.0586 | [+0.0411, +0.0764] * | out-of-fold nested-CV selection - paper-style E |
| delta_k10_gold_page_span_single-page | +0.0634 | [+0.0437, +0.0843] * | out-of-fold nested-CV selection - paper-style E |
| delta_k10_question_type_Comparative | +0.0536 | [+0.0300, +0.0780] * | out-of-fold nested-CV selection - paper-style E |
| delta_k10_question_type_Descriptive | +0.0680 | [+0.0450, +0.0921] * | out-of-fold nested-CV selection - paper-style E |
| delta_k10_question_type_Interpretative | +0.0469 | [+0.0228, +0.0687] * | out-of-fold nested-CV selection - paper-style E |
| delta_k10_question_type_Analytical | +0.0675 | [+0.0281, +0.1078] * | out-of-fold nested-CV selection - paper-style E |
| delta_k20_evidence_modality_cross-modal | +0.0334 | [+0.0195, +0.0474] * | out-of-fold nested-CV selection - paper-style E |
| delta_k20_evidence_modality_pure_visual | +0.0256 | [+0.0087, +0.0416] * | out-of-fold nested-CV selection - paper-style E |
| delta_k20_gold_page_span_cross-page | +0.0321 | [+0.0175, +0.0472] * | out-of-fold nested-CV selection - paper-style E |
| delta_k20_gold_page_span_single-page | +0.0285 | [+0.0143, +0.0423] * | out-of-fold nested-CV selection - paper-style E |
| delta_k20_question_type_Comparative | +0.0219 | [+0.0034, +0.0408] * | out-of-fold nested-CV selection - paper-style E |
| delta_k20_question_type_Descriptive | +0.0328 | [+0.0154, +0.0502] * | out-of-fold nested-CV selection - paper-style E |
| delta_k20_question_type_Interpretative | +0.0499 | [+0.0334, +0.0668] * | out-of-fold nested-CV selection - paper-style E |
| delta_k20_question_type_Analytical | +0.0130 | [-0.0251, +0.0470] | out-of-fold nested-CV selection - paper-style E |
| contrast_k10_evidence_modality | -0.0691 | [-0.0967, -0.0420] * | out-of-fold nested-CV selection - paper-style E |
| contrast_k10_gold_page_span | -0.0048 | [-0.0304, +0.0203] | out-of-fold nested-CV selection - paper-style E |
| contrast_k20_evidence_modality | +0.0078 | [-0.0142, +0.0293] | out-of-fold nested-CV selection - paper-style E |
| contrast_k20_gold_page_span | +0.0036 | [-0.0155, +0.0226] | out-of-fold nested-CV selection - paper-style E |

**配置**：pool=canonical　bootstrap=4000

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| n_questions | 2000.0000 | — | out-of-fold nested-CV selection - paper-style E |
| n_documents | 220.0000 | — | out-of-fold nested-CV selection - paper-style E |
| delta_k10_evidence_modality_cross-modal | +0.0239 | [+0.0094, +0.0387] * | out-of-fold nested-CV selection - paper-style E |
| delta_k10_evidence_modality_pure_visual | +0.1037 | [+0.0774, +0.1290] * | out-of-fold nested-CV selection - paper-style E |
| delta_k10_gold_page_span_cross-page | +0.0532 | [+0.0347, +0.0717] * | out-of-fold nested-CV selection - paper-style E |
| delta_k10_gold_page_span_single-page | +0.0553 | [+0.0355, +0.0755] * | out-of-fold nested-CV selection - paper-style E |
| delta_k10_question_type_Comparative | +0.0462 | [+0.0228, +0.0709] * | out-of-fold nested-CV selection - paper-style E |
| delta_k10_question_type_Descriptive | +0.0677 | [+0.0439, +0.0933] * | out-of-fold nested-CV selection - paper-style E |
| delta_k10_question_type_Interpretative | +0.0314 | [+0.0073, +0.0537] * | out-of-fold nested-CV selection - paper-style E |
| delta_k10_question_type_Analytical | +0.0516 | [+0.0134, +0.0880] * | out-of-fold nested-CV selection - paper-style E |
| delta_k20_evidence_modality_cross-modal | +0.0330 | [+0.0212, +0.0451] * | out-of-fold nested-CV selection - paper-style E |
| delta_k20_evidence_modality_pure_visual | +0.0168 | [+0.0004, +0.0329] * | out-of-fold nested-CV selection - paper-style E |
| delta_k20_gold_page_span_cross-page | +0.0333 | [+0.0200, +0.0470] * | out-of-fold nested-CV selection - paper-style E |
| delta_k20_gold_page_span_single-page | +0.0193 | [+0.0053, +0.0325] * | out-of-fold nested-CV selection - paper-style E |
| delta_k20_question_type_Comparative | +0.0226 | [+0.0054, +0.0402] * | out-of-fold nested-CV selection - paper-style E |
| delta_k20_question_type_Descriptive | +0.0288 | [+0.0108, +0.0469] * | out-of-fold nested-CV selection - paper-style E |
| delta_k20_question_type_Interpretative | +0.0316 | [+0.0144, +0.0493] * | out-of-fold nested-CV selection - paper-style E |
| delta_k20_question_type_Analytical | +0.0230 | [-0.0131, +0.0567] | out-of-fold nested-CV selection - paper-style E |
| contrast_k10_evidence_modality | -0.0798 | [-0.1077, -0.0534] * | out-of-fold nested-CV selection - paper-style E |
| contrast_k10_gold_page_span | -0.0021 | [-0.0264, +0.0221] | out-of-fold nested-CV selection - paper-style E |
| contrast_k20_evidence_modality | +0.0162 | [-0.0044, +0.0366] | out-of-fold nested-CV selection - paper-style E |
| contrast_k20_gold_page_span | +0.0140 | [-0.0050, +0.0328] | out-of-fold nested-CV selection - paper-style E |

**限制**：exploratory：该切分自 E9 起被反复观察并用于挑方法。**proposal Experiment 2 的五类里有两类在 MMDocRAG evaluation split 上无法评价**：pure text 只有 1 题（n=1，无区间可言），unanswerable 一题都没有（每题都带 gold 证据）。这是 benchmark 的属性，不是分析的缺口，写报告时必须照此说明而不能假装跑了五类。question_type 里 Inferential/Procedural/Causal/Application-based 四类均低于 100 题或 20 篇的阈值，只描述不检验。

<sub>逐题结果与 manifest：`artifacts/runs/20260905T073315Z_cached/experiments/E37/cmd0`</sub>

## E38　RQ1b 的 R² 目标问错了：完美预测本身也只值 +0.023

**状态**：已运行　耗时 8.9s
- **问什么**：proposal 给 RQ1b 设了一个 R² 目标，并点名三个未试的特征源（视觉检索器分数、模型内部表示、LLM 证据充分性判断）。E23 把 R² 从 −0.155 抬到 +0.136 就停住了，只说「分配收益仍是 0~2%」。那么究竟是 R² 太低所以值得换特征源，还是 R² 到收益的映射本身就是平的？
- **怎么做**：复用 reflect_alloc 的两段式召回矩阵与真实 visual_share。对每个目标 R² 用二分法反解噪声标准差（按裁剪后的实测 R²），共同随机数生成 200 组预测，收缩系数在测试集上取最优，再按文档 cluster bootstrap 给区间。
- **指标含义**：每一行是「精度达到该 R² 的预测器最好能买到多少」，是上界不是预报：合成预测器无偏、误差与真值独立，且收缩系数在测试集上选。
- **统计单位**：document（bootstrap 按此重采样）

**配置**：pool=canonical　bootstrap=4000

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| recall_best_fixed_split | +0.8200 | — |  |
| recall_oracle_split | +0.8819 | — |  |
| headroom | +0.0618 | — | oracle split minus best fixed split; everything the allocation decision could ever address |
| delta_from_true_mix | +0.0229 | [+0.0121, +0.0351] * | E21's finding re-derived: what allocating from the true modality mix buys |
| delta_at_r2_0_000 | +0.0071 | [-0.0012, +0.0159] | synthetic sensitivity, shrinkage selected on test; pointwise CI conditional on this selection |
| delta_at_r2_0_136 | +0.0089 | [+0.0009, +0.0185] * | synthetic sensitivity, shrinkage selected on test; pointwise CI conditional on this selection |
| delta_at_r2_0_200 | +0.0090 | [+0.0008, +0.0181] * | synthetic sensitivity, shrinkage selected on test; pointwise CI conditional on this selection |
| delta_at_r2_0_300 | +0.0120 | [+0.0027, +0.0221] * | synthetic sensitivity, shrinkage selected on test; pointwise CI conditional on this selection |
| delta_at_r2_0_400 | +0.0134 | [+0.0039, +0.0236] * | synthetic sensitivity, shrinkage selected on test; pointwise CI conditional on this selection |
| delta_at_r2_0_500 | +0.0147 | [+0.0054, +0.0248] * | synthetic sensitivity, shrinkage selected on test; pointwise CI conditional on this selection |
| delta_at_r2_0_600 | +0.0166 | [+0.0069, +0.0267] * | synthetic sensitivity, shrinkage selected on test; pointwise CI conditional on this selection |
| delta_at_r2_0_700 | +0.0182 | [+0.0089, +0.0286] * | synthetic sensitivity, shrinkage selected on test; pointwise CI conditional on this selection |
| delta_at_r2_0_800 | +0.0195 | [+0.0102, +0.0298] * | synthetic sensitivity, shrinkage selected on test; pointwise CI conditional on this selection |
| delta_at_r2_0_900 | +0.0213 | [+0.0118, +0.0320] * | synthetic sensitivity, shrinkage selected on test; pointwise CI conditional on this selection |
| delta_at_r2_0_950 | +0.0223 | [+0.0121, +0.0337] * | synthetic sensitivity, shrinkage selected on test; pointwise CI conditional on this selection |
| delta_at_r2_1_000 | +0.0229 | [+0.0122, +0.0350] * | synthetic sensitivity, shrinkage selected on test; pointwise CI conditional on this selection |

**配置**：pool=selfbuilt　bootstrap=4000

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| recall_best_fixed_split | +0.8066 | — |  |
| recall_oracle_split | +0.8682 | — |  |
| headroom | +0.0615 | — | oracle split minus best fixed split; everything the allocation decision could ever address |
| delta_from_true_mix | +0.0275 | [+0.0140, +0.0423] * | E21's finding re-derived: what allocating from the true modality mix buys |
| delta_at_r2_0_000 | +0.0099 | [+0.0000, +0.0209] * | synthetic sensitivity, shrinkage selected on test; pointwise CI conditional on this selection |
| delta_at_r2_0_136 | +0.0124 | [+0.0028, +0.0241] * | synthetic sensitivity, shrinkage selected on test; pointwise CI conditional on this selection |
| delta_at_r2_0_200 | +0.0125 | [+0.0025, +0.0237] * | synthetic sensitivity, shrinkage selected on test; pointwise CI conditional on this selection |
| delta_at_r2_0_300 | +0.0147 | [+0.0048, +0.0261] * | synthetic sensitivity, shrinkage selected on test; pointwise CI conditional on this selection |
| delta_at_r2_0_400 | +0.0159 | [+0.0058, +0.0275] * | synthetic sensitivity, shrinkage selected on test; pointwise CI conditional on this selection |
| delta_at_r2_0_500 | +0.0173 | [+0.0071, +0.0293] * | synthetic sensitivity, shrinkage selected on test; pointwise CI conditional on this selection |
| delta_at_r2_0_600 | +0.0194 | [+0.0087, +0.0316] * | synthetic sensitivity, shrinkage selected on test; pointwise CI conditional on this selection |
| delta_at_r2_0_700 | +0.0208 | [+0.0105, +0.0332] * | synthetic sensitivity, shrinkage selected on test; pointwise CI conditional on this selection |
| delta_at_r2_0_800 | +0.0224 | [+0.0116, +0.0351] * | synthetic sensitivity, shrinkage selected on test; pointwise CI conditional on this selection |
| delta_at_r2_0_900 | +0.0243 | [+0.0132, +0.0374] * | synthetic sensitivity, shrinkage selected on test; pointwise CI conditional on this selection |
| delta_at_r2_0_950 | +0.0256 | [+0.0135, +0.0396] * | synthetic sensitivity, shrinkage selected on test; pointwise CI conditional on this selection |
| delta_at_r2_1_000 | +0.0275 | [+0.0143, +0.0424] * | synthetic sensitivity, shrinkage selected on test; pointwise CI conditional on this selection |

**限制**：exploratory：该切分自 E9 起被反复观察并用于挑方法。合成预测器的误差与真值独立且无偏，真实 ridge 会向训练均值收缩、误差与真值相关，因此在同一 R² 下**严格更差**——这条曲线是上界不是预报。收缩系数在测试集上选，任何可部署系统都做不到，同样是为了取上界。结论只覆盖 RQ1b 的配额分配决策，不能外推到 E36 的升级决策。

<sub>逐题结果与 manifest：`artifacts/runs/20260905T073315Z_cached/experiments/E38/cmd0`</sub>

## E40　E27 头条在 bge-large 上复核：提升不是弱编码器的产物

**状态**：已运行　耗时 33.2s
- **问什么**：E27 的 +0.061 是真实的配置提升，还是 bge-small 太弱制造出来的？换成本项目唯一字节可证、且更接近论文规模的文本检索器之后，四格还剩几格？
- **怎么做**：与 E27 完全相同的 document-grouped 5 折折外协议，只把 dense 文本臂换成 models/bge-large-en-v1.5。
- **统计单位**：document（bootstrap 按此重采样）

**配置**：pool=selfbuilt　k=10　seed=20260825　bootstrap=4000

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| recall_surrogate_A | +0.6547 | — | local dense surrogate, local paper-style quota |
| recall_paper_style_E | +0.6568 | — | closest local paper-style hybrid (dense text + ColQwen) |
| recall_nested_cv_oof | +0.7173 | — | out-of-fold, configuration chosen without the question |
| delta: nested-CV - paper-style (E) | +0.0605 | [+0.0466, +0.0752] * | nested-CV - paper-style (E) |
| delta: nested-CV - surrogate (A) | +0.0626 | [+0.0486, +0.0767] * | nested-CV - surrogate (A) |
| delta: paper-style (E) - surrogate (A) | +0.0021 | [-0.0093, +0.0145] | paper-style (E) - surrogate (A) |
| fold0_selected_quota_text | 4.0000 | — | fold 0 inner selection: rrf/rrf, 4/6 |
| fold1_selected_quota_text | 4.0000 | — | fold 1 inner selection: rrf/rrf, 4/6 |
| fold2_selected_quota_text | 4.0000 | — | fold 2 inner selection: rrf/rrf, 4/6 |
| fold3_selected_quota_text | 4.0000 | — | fold 3 inner selection: rrf/rrf, 4/6 |
| fold4_selected_quota_text | 4.0000 | — | fold 4 inner selection: rrf/rrf, 4/6 |

**配置**：pool=selfbuilt　k=20　seed=20260825　bootstrap=4000

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| recall_surrogate_A | +0.7994 | — | local dense surrogate, local paper-style quota |
| recall_paper_style_E | +0.7956 | — | closest local paper-style hybrid (dense text + ColQwen) |
| recall_nested_cv_oof | +0.8285 | — | out-of-fold, configuration chosen without the question |
| delta: nested-CV - paper-style (E) | +0.0329 | [+0.0232, +0.0428] * | nested-CV - paper-style (E) |
| delta: nested-CV - surrogate (A) | +0.0291 | [+0.0202, +0.0381] * | nested-CV - surrogate (A) |
| delta: paper-style (E) - surrogate (A) | -0.0038 | [-0.0124, +0.0051] | paper-style (E) - surrogate (A) |
| fold0_selected_quota_text | 10.0000 | — | fold 0 inner selection: rrf/rrf, 10/10 |
| fold1_selected_quota_text | 10.0000 | — | fold 1 inner selection: rrf/rrf, 10/10 |
| fold2_selected_quota_text | 10.0000 | — | fold 2 inner selection: rrf/rrf, 10/10 |
| fold3_selected_quota_text | 10.0000 | — | fold 3 inner selection: rrf/rrf, 10/10 |
| fold4_selected_quota_text | 10.0000 | — | fold 4 inner selection: rrf/rrf, 10/10 |

**配置**：pool=canonical　k=10　seed=20260825　bootstrap=4000

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| recall_surrogate_A | +0.6888 | — | local dense surrogate, local paper-style quota |
| recall_paper_style_E | +0.6909 | — | closest local paper-style hybrid (dense text + ColQwen) |
| recall_nested_cv_oof | +0.7433 | — | out-of-fold, configuration chosen without the question |
| delta: nested-CV - paper-style (E) | +0.0525 | [+0.0379, +0.0672] * | nested-CV - paper-style (E) |
| delta: nested-CV - surrogate (A) | +0.0546 | [+0.0402, +0.0691] * | nested-CV - surrogate (A) |
| delta: paper-style (E) - surrogate (A) | +0.0021 | [-0.0093, +0.0145] | paper-style (E) - surrogate (A) |
| fold0_selected_quota_text | 4.0000 | — | fold 0 inner selection: rrf/rrf, 4/6 |
| fold1_selected_quota_text | 4.0000 | — | fold 1 inner selection: rrf/rrf, 4/6 |
| fold2_selected_quota_text | 4.0000 | — | fold 2 inner selection: rrf/rrf, 4/6 |
| fold3_selected_quota_text | 4.0000 | — | fold 3 inner selection: rrf/rrf, 4/6 |
| fold4_selected_quota_text | 4.0000 | — | fold 4 inner selection: rrf/rrf, 4/6 |

**配置**：pool=canonical　k=20　seed=20260825　bootstrap=4000

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| recall_surrogate_A | +0.8312 | — | local dense surrogate, local paper-style quota |
| recall_paper_style_E | +0.8274 | — | closest local paper-style hybrid (dense text + ColQwen) |
| recall_nested_cv_oof | +0.8541 | — | out-of-fold, configuration chosen without the question |
| delta: nested-CV - paper-style (E) | +0.0267 | [+0.0173, +0.0361] * | nested-CV - paper-style (E) |
| delta: nested-CV - surrogate (A) | +0.0229 | [+0.0140, +0.0320] * | nested-CV - surrogate (A) |
| delta: paper-style (E) - surrogate (A) | -0.0038 | [-0.0124, +0.0051] | paper-style (E) - surrogate (A) |
| fold0_selected_quota_text | 10.0000 | — | fold 0 inner selection: rrf/rrf, 10/10 |
| fold1_selected_quota_text | 11.0000 | — | fold 1 inner selection: rrf/rrf, 11/9 |
| fold2_selected_quota_text | 10.0000 | — | fold 2 inner selection: rrf/rrf, 10/10 |
| fold3_selected_quota_text | 10.0000 | — | fold 3 inner selection: rrf/rrf, 10/10 |
| fold4_selected_quota_text | 10.0000 | — | fold 4 inner selection: rrf/rrf, 10/10 |

**限制**：本条只搬了 E27。其余 14 个依赖 bge-small-vlm 的实验仍是 bge-small 的结果，作为历史记录保留；其中 E35/E36/E37 的增益是两臂同时换编码器的相对量，对编码器不敏感，但**尚未实测**，不应写成已复核。同样地，这条切分自 E9 起被反复观察，本结果与 E27 一样只能标 exploratory。

<sub>逐题结果与 manifest：`artifacts/runs/20260905T073315Z_cached/experiments/E40/cmd0`</sub>

## E41　八组 OOF 比较的多重检验复核

**状态**：已运行　耗时 3.7s
- **问什么**：把 E27/E40 的两种模型、两个候选池、两个 k 合为八项比较后，结论是否仍然成立？
- **统计单位**：document（bootstrap 按此重采样）

**配置**：bootstrap=10000　seed=20260905

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| delta:E27:canonical:10 | +0.0541 | [+0.0390, +0.0687] * |  |
| delta:E27:canonical:20 | +0.0269 | [+0.0172, +0.0364] * |  |
| delta:E27:selfbuilt:10 | +0.0608 | [+0.0467, +0.0749] * |  |
| delta:E27:selfbuilt:20 | +0.0304 | [+0.0198, +0.0409] * |  |
| delta:E40:canonical:10 | +0.0525 | [+0.0375, +0.0672] * |  |
| delta:E40:canonical:20 | +0.0267 | [+0.0172, +0.0357] * |  |
| delta:E40:selfbuilt:10 | +0.0605 | [+0.0458, +0.0748] * |  |
| delta:E40:selfbuilt:20 | +0.0329 | [+0.0235, +0.0423] * |  |

**限制**：比较族在看到历史结果后才汇总，因此这是探索性的多重比较敏感性分析，不能追溯称为预注册。

<sub>逐题结果与 manifest：`artifacts/runs/20260905T073315Z_cached/experiments/E41`</sub>

---
`*` 表示 95% 置信区间不跨 0。区间下界贴近 0 时不要写「显著」。
