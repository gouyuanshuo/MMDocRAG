# 运行报告 · 20260831T142910Z_e38

- 套件：`single:E38`　离线：True　允许 API：False
- 生成时间（UTC）：2026-08-31 14:32:20
- 代码 commit：`fae74579f5e455ec6a321cb552df3664cd58f282`　工作区脏：True
- **source fingerprint：`9e24b02245d40b59`**（20 个源文件 + 注册表快照的哈希）　清单：`artifacts/runs/20260831T142910Z_e38/source_manifest.json`
- **source bundle：`artifacts/runs/20260831T142910Z_e38/source_bundle.zip`**（20 个文件，120858 字节，sha256 `84a8d37894c81212046f1ec87978bf916e741f5855f673a50f1de7c48e91b469`）——**这是本次源码的最终快照**
- 工作区补丁：`artifacts/runs/20260831T142910Z_e38/source.patch`（只含 **Git 已跟踪**文件的改动；本仓库多数源码未被跟踪，因此 patch 单独**不能**还原本次运行，须叠加 bundle）
- 重建测试：**pass** 20/20 个文件哈希逐字节命中（隔离目录 `artifacts/test-runs/20260831T142910Z_e38-reconstruct/tree`）
- 复现源码：`python -m expkit.source reconstruct --run 20260831T142910Z_e38`（git archive → git apply → 解压 bundle → 重算全部哈希）
- 实验状态：已运行 1

> 本报告中的每个数字都取自本次运行落盘的 `metrics.json`，不复制 `experiments.py` 里的历史文字。标记为「已运行（仅日志）」的实验尚未接入结构化输出，其数字请看对应的 `stdout.log`，不要从这里引用。

## E38　RQ1b 的 R² 目标问错了：完美预测本身也只值 +0.023

**状态**：已运行　耗时 51.2s
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
| delta_at_r2_0_000 | +0.0071 | [-0.0012, +0.0159] | ceiling: unbiased predictor at this R^2, shrinkage chosen on test |
| delta_at_r2_0_136 | +0.0089 | [+0.0009, +0.0185] * | ceiling: unbiased predictor at this R^2, shrinkage chosen on test |
| delta_at_r2_0_200 | +0.0090 | [+0.0008, +0.0181] * | ceiling: unbiased predictor at this R^2, shrinkage chosen on test |
| delta_at_r2_0_300 | +0.0120 | [+0.0027, +0.0221] * | ceiling: unbiased predictor at this R^2, shrinkage chosen on test |
| delta_at_r2_0_400 | +0.0134 | [+0.0039, +0.0236] * | ceiling: unbiased predictor at this R^2, shrinkage chosen on test |
| delta_at_r2_0_500 | +0.0147 | [+0.0054, +0.0248] * | ceiling: unbiased predictor at this R^2, shrinkage chosen on test |
| delta_at_r2_0_600 | +0.0166 | [+0.0069, +0.0267] * | ceiling: unbiased predictor at this R^2, shrinkage chosen on test |
| delta_at_r2_0_700 | +0.0182 | [+0.0089, +0.0286] * | ceiling: unbiased predictor at this R^2, shrinkage chosen on test |
| delta_at_r2_0_800 | +0.0195 | [+0.0102, +0.0298] * | ceiling: unbiased predictor at this R^2, shrinkage chosen on test |
| delta_at_r2_0_900 | +0.0213 | [+0.0118, +0.0320] * | ceiling: unbiased predictor at this R^2, shrinkage chosen on test |
| delta_at_r2_0_950 | +0.0223 | [+0.0121, +0.0337] * | ceiling: unbiased predictor at this R^2, shrinkage chosen on test |
| delta_at_r2_1_000 | +0.0229 | [+0.0122, +0.0350] * | ceiling: unbiased predictor at this R^2, shrinkage chosen on test |

**配置**：pool=selfbuilt　bootstrap=4000

| 指标 | 值 | 95% CI（文档聚类） | 说明 |
|---|---|---|---|
| recall_best_fixed_split | +0.8066 | — |  |
| recall_oracle_split | +0.8682 | — |  |
| headroom | +0.0615 | — | oracle split minus best fixed split; everything the allocation decision could ever address |
| delta_from_true_mix | +0.0275 | [+0.0140, +0.0423] * | E21's finding re-derived: what allocating from the true modality mix buys |
| delta_at_r2_0_000 | +0.0099 | [+0.0000, +0.0209] * | ceiling: unbiased predictor at this R^2, shrinkage chosen on test |
| delta_at_r2_0_136 | +0.0124 | [+0.0028, +0.0241] * | ceiling: unbiased predictor at this R^2, shrinkage chosen on test |
| delta_at_r2_0_200 | +0.0125 | [+0.0025, +0.0237] * | ceiling: unbiased predictor at this R^2, shrinkage chosen on test |
| delta_at_r2_0_300 | +0.0147 | [+0.0048, +0.0261] * | ceiling: unbiased predictor at this R^2, shrinkage chosen on test |
| delta_at_r2_0_400 | +0.0159 | [+0.0058, +0.0275] * | ceiling: unbiased predictor at this R^2, shrinkage chosen on test |
| delta_at_r2_0_500 | +0.0173 | [+0.0071, +0.0293] * | ceiling: unbiased predictor at this R^2, shrinkage chosen on test |
| delta_at_r2_0_600 | +0.0194 | [+0.0087, +0.0316] * | ceiling: unbiased predictor at this R^2, shrinkage chosen on test |
| delta_at_r2_0_700 | +0.0208 | [+0.0105, +0.0332] * | ceiling: unbiased predictor at this R^2, shrinkage chosen on test |
| delta_at_r2_0_800 | +0.0224 | [+0.0116, +0.0351] * | ceiling: unbiased predictor at this R^2, shrinkage chosen on test |
| delta_at_r2_0_900 | +0.0243 | [+0.0132, +0.0374] * | ceiling: unbiased predictor at this R^2, shrinkage chosen on test |
| delta_at_r2_0_950 | +0.0256 | [+0.0135, +0.0396] * | ceiling: unbiased predictor at this R^2, shrinkage chosen on test |
| delta_at_r2_1_000 | +0.0275 | [+0.0143, +0.0424] * | ceiling: unbiased predictor at this R^2, shrinkage chosen on test |

**限制**：exploratory：该切分自 E9 起被反复观察并用于挑方法。合成预测器的误差与真值独立且无偏，真实 ridge 会向训练均值收缩、误差与真值相关，因此在同一 R² 下**严格更差**——这条曲线是上界不是预报。收缩系数在测试集上选，任何可部署系统都做不到，同样是为了取上界。结论只覆盖 RQ1b 的配额分配决策，不能外推到 E36 的升级决策。

<sub>逐题结果与 manifest：`artifacts/runs/20260831T142910Z_e38/experiments/E38/cmd0`</sub>

---
`*` 表示 95% 置信区间不跨 0。区间下界贴近 0 时不要写「显著」。
