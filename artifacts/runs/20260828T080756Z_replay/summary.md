# 运行报告 · 20260828T080756Z_replay

- 套件：`replay`　离线：True　允许 API：False
- 生成时间（UTC）：2026-08-28 08:12:23
- 代码 commit：`2fd7505c6a576376b4a92aafaff6d87494765bb7`　工作区脏：True
- **source fingerprint：`cf6af3d3202e0fd8`**（25 个源文件 + 注册表快照的哈希）　清单：`artifacts/runs/20260828T080756Z_replay/source_manifest.json`
- 工作区补丁：`artifacts/runs/20260828T080756Z_replay/source.patch`（`git checkout <commit> && git apply <patch>` 可还原本次源码）
- 实验状态：已运行 3，已运行（仅日志） 4

> 本报告中的每个数字都取自本次运行落盘的 `metrics.json`，不复制 `experiments.py` 里的历史文字。标记为「已运行（仅日志）」的实验尚未接入结构化输出，其数字请看对应的 `stdout.log`，不要从这里引用。

## E1　复现锚点

**状态**：已运行（仅日志）　耗时 55.3s
- **问什么**：官方评测代码是否与论文公布的数字自洽？
- **怎么做**：用仓库内已发布的 response 文件重算官方 17 项指标，不调用任何模型。
- **指标含义**：逐位命中论文公布的数字即代表本地评分口径与论文自洽。
- **统计单位**：question（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260828T080756Z_replay/experiments/E1/stdout.log`

- **限制**：这是评测复算，不是完整实验复现；没有重跑检索器，也没有重新调用模型。

## E2　评测脚本的静默截断缺陷

**状态**：已运行（仅日志）　耗时 56.5s
- **问什么**：断点续跑产生的部分结果会不会被静默地在更少样本上求均值？
- **怎么做**：按 q_id join 替换 zip()，并显式打印共同样本数。
- **指标含义**：覆盖率 < 100% 时必须报错或显式声明，而不是静默在少数样本上求均值。
- **统计单位**：question（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260828T080756Z_replay/experiments/E2/stdout.log`

- **限制**：只能说明已发布 judge artifacts 无法构造同底比较，不能推断作者内部流程。

## E3　工程可复现性

**状态**：已运行（仅日志）　耗时 0.1s
- **问什么**：仓库能否在本机复现？
- **怎么做**：检查 manifest 模块存在且可导入。
- **指标含义**：基础设施可用性检查，不产生实验数字。
- **统计单位**：question（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260828T080756Z_replay/experiments/E3/stdout.log`

- **限制**：这是工程整改，不是方法贡献。

## E24　ColQwen2 在本项目的池规模下不值它的 GPU 成本

**状态**：已运行　耗时 2.9s
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
| ranking_coverage | 1.0000 | — | 1995/1995 questions ranked by ColQwen |
| questions_with_visual_gold | 1995.0000 | — |  |
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
| paired_delta[RRF(description) - ColQwen]@10 | +0.0269 | [+0.0127, +0.0412] * | RRF(description) - ColQwen |
| paired_delta[RRF(description) - ColQwen]@20 | +0.0111 | [-0.0010, +0.0230] | RRF(description) - ColQwen |
| paired_delta[RRF(desc+ColQwen) - ColQwen]@10 | +0.0254 | [+0.0137, +0.0368] * | RRF(desc+ColQwen) - ColQwen |
| paired_delta[RRF(desc+ColQwen) - ColQwen]@20 | +0.0142 | [+0.0050, +0.0236] * | RRF(desc+ColQwen) - ColQwen |
| questions_in_evaluation_split | 2000.0000 | — | ColQwen ranks all 2,000 |
| questions_scored_here | 1995.0000 | — | questions WITH visual gold; the other 5 cannot be scored |

**限制**：池只覆盖 13,999 张原始图片中的 6,487 张（46.34% 唯一图片）；按文档中位仅 20 个候选，k=20 已接近饱和。这是公平的池内排序比较，不是完整文档图片池上的检索比较。

<sub>逐题结果与 manifest：`artifacts/runs/20260828T080756Z_replay/experiments/E24`</sub>

## E27　静态检索配置的改进

**状态**：已运行　耗时 125.4s
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
| delta: nested-CV - paper-style (E) | +0.0608 | [+0.0468, +0.0753] * | nested-CV - paper-style (E) |
| delta: nested-CV - surrogate (A) | +0.0683 | [+0.0549, +0.0824] * | nested-CV - surrogate (A) |
| delta: paper-style (E) - surrogate (A) | +0.0075 | [-0.0045, +0.0201] | paper-style (E) - surrogate (A) |
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
| delta: nested-CV - paper-style (E) | +0.0304 | [+0.0197, +0.0412] * | nested-CV - paper-style (E) |
| delta: nested-CV - surrogate (A) | +0.0343 | [+0.0248, +0.0443] * | nested-CV - surrogate (A) |
| delta: paper-style (E) - surrogate (A) | +0.0039 | [-0.0047, +0.0129] | paper-style (E) - surrogate (A) |
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
| delta: nested-CV - paper-style (E) | +0.0541 | [+0.0395, +0.0689] * | nested-CV - paper-style (E) |
| delta: nested-CV - surrogate (A) | +0.0616 | [+0.0481, +0.0760] * | nested-CV - surrogate (A) |
| delta: paper-style (E) - surrogate (A) | +0.0075 | [-0.0045, +0.0201] | paper-style (E) - surrogate (A) |
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
| delta: nested-CV - paper-style (E) | +0.0269 | [+0.0172, +0.0364] * | nested-CV - paper-style (E) |
| delta: nested-CV - surrogate (A) | +0.0308 | [+0.0225, +0.0389] * | nested-CV - surrogate (A) |
| delta: paper-style (E) - surrogate (A) | +0.0039 | [-0.0047, +0.0129] | paper-style (E) - surrogate (A) |
| fold0_selected_quota_text | 11.0000 | — | fold 0 inner selection: rrf/rrf, 11/9 |
| fold1_selected_quota_text | 10.0000 | — | fold 1 inner selection: rrf/rrf, 10/10 |
| fold2_selected_quota_text | 11.0000 | — | fold 2 inner selection: rrf/rrf, 11/9 |
| fold3_selected_quota_text | 11.0000 | — | fold 3 inner selection: rrf/rrf, 11/9 |
| fold4_selected_quota_text | 10.0000 | — | fold 4 inner selection: rrf/rrf, 10/10 |

**限制**：单切分结果为 exploratory；泛化性只由 E28 的 nested CV 支持。

<sub>逐题结果与 manifest：`artifacts/runs/20260828T080756Z_replay/experiments/E27/cmd0`</sub>

## E28　复现性与结论边界审计

**状态**：已运行（仅日志）　耗时 4.7s
- **问什么**：已发布的结论有哪些超出了证据？
- **怎么做**：document-grouped 外层 CV，内层在训练折上重选检索器与配额，每题由未参与其配置选择的折评分。
- **指标含义**：无脚本内选择泄漏的 Recall；仍是 internal OOF，不是外部确认。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260828T080756Z_replay/experiments/E28/cmd0/stdout.log`

- **限制**：并非严格双层 inner-CV；方法空间此前已用同一 2,000 题开发，k=20 时各折选择不稳定。

## E30　归因消融：+0.054 究竟来自哪个组件

**状态**：已运行　耗时 21.2s
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

<sub>逐题结果与 manifest：`artifacts/runs/20260828T080756Z_replay/experiments/E30`</sub>

---
`*` 表示 95% 置信区间不跨 0。区间下界贴近 0 时不要写「显著」。
