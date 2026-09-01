# 运行报告 · 20260831T143227Z_e37

- 套件：`single:E37`　离线：True　允许 API：False
- 生成时间（UTC）：2026-08-31 14:35:08
- 代码 commit：`fae74579f5e455ec6a321cb552df3664cd58f282`　工作区脏：True
- **source fingerprint：`34ffab89fd913e9f`**（20 个源文件 + 注册表快照的哈希）　清单：`artifacts/runs/20260831T143227Z_e37/source_manifest.json`
- **source bundle：`artifacts/runs/20260831T143227Z_e37/source_bundle.zip`**（20 个文件，121809 字节，sha256 `b131151ab8ea930a55cec1c5d28a46f0d62147ef30ef8cfeb8a7c90a9235384c`）——**这是本次源码的最终快照**
- 工作区补丁：`artifacts/runs/20260831T143227Z_e37/source.patch`（只含 **Git 已跟踪**文件的改动；本仓库多数源码未被跟踪，因此 patch 单独**不能**还原本次运行，须叠加 bundle）
- 重建测试：**pass** 20/20 个文件哈希逐字节命中（隔离目录 `artifacts/test-runs/20260831T143227Z_e37-reconstruct/tree`）
- 复现源码：`python -m expkit.source reconstruct --run 20260831T143227Z_e37`（git archive → git apply → 解压 bundle → 重算全部哈希）
- 实验状态：已运行 1

> 本报告中的每个数字都取自本次运行落盘的 `metrics.json`，不复制 `experiments.py` 里的历史文字。标记为「已运行（仅日志）」的实验尚未接入结构化输出，其数字请看对应的 `stdout.log`，不要从这里引用。

## E37　静态提升按题型切片：增益集中在纯视觉题，且只在 k=10

**状态**：已运行　耗时 41.5s
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

<sub>逐题结果与 manifest：`artifacts/runs/20260831T143227Z_e37/experiments/E37/cmd0`</sub>

---
`*` 表示 95% 置信区间不跨 0。区间下界贴近 0 时不要写「显著」。
