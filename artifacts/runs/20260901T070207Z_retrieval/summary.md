# 运行报告 · 20260901T070207Z_retrieval

- 套件：`retrieval`　离线：True　允许 API：False
- 生成时间（UTC）：2026-09-01 07:03:24
- 代码 commit：`a42cda468120916bbb0170416212a4505f89f6ea`　工作区脏：True
- **source fingerprint：`9d6402baa005761b`**（20 个源文件 + 注册表快照的哈希）　清单：`artifacts/runs/20260901T070207Z_retrieval/source_manifest.json`
- **source bundle：`artifacts/runs/20260901T070207Z_retrieval/source_bundle.zip`**（20 个文件，124528 字节，sha256 `555f92de2e280abcab93edeaf68f30c72e1b927fca3ab3008795ccea47639969`）——**这是本次源码的最终快照**
- 工作区补丁：`artifacts/runs/20260901T070207Z_retrieval/source.patch`（只含 **Git 已跟踪**文件的改动；本仓库多数源码未被跟踪，因此 patch 单独**不能**还原本次运行，须叠加 bundle）
- 重建测试：**pass** 20/20 个文件哈希逐字节命中（隔离目录 `artifacts/test-runs/20260901T070207Z_retrieval-reconstruct/tree`）
- 复现源码：`python -m expkit.source reconstruct --run 20260901T070207Z_retrieval`（git archive → git apply → 解压 bundle → 重算全部哈希）
- 实验状态：已运行 1

> 本报告中的每个数字都取自本次运行落盘的 `metrics.json`，不复制 `experiments.py` 里的历史文字。标记为「已运行（仅日志）」的实验尚未接入结构化输出，其数字请看对应的 `stdout.log`，不要从这里引用。

## E40　E27 头条在 bge-large 上复核：提升不是弱编码器的产物

**状态**：已运行　耗时 46.4s
- **问什么**：E27 的 +0.061 是真实的配置提升，还是 bge-small 太弱制造出来的？换成本项目唯一字节可证、且更接近论文规模的文本检索器之后，四格还剩几格？
- **怎么做**：与 E27 完全相同的 document-grouped 5 折折外协议，只把 dense 文本臂换成 models/bge-large-en-v1.5。
- **统计单位**：document（bootstrap 按此重采样）

**配置**：pool=selfbuilt　k=10　seed=20260825　bootstrap=4000

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| recall_surrogate_A | +0.6547 | — | local BGE-small surrogate, official quota |
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
| recall_surrogate_A | +0.7994 | — | local BGE-small surrogate, official quota |
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
| recall_surrogate_A | +0.6888 | — | local BGE-small surrogate, official quota |
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
| recall_surrogate_A | +0.8312 | — | local BGE-small surrogate, official quota |
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

<sub>逐题结果与 manifest：`artifacts/runs/20260901T070207Z_retrieval/experiments/E40/cmd0`</sub>

---
`*` 表示 95% 置信区间不跨 0。区间下界贴近 0 时不要写「显著」。
