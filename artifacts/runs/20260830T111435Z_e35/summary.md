# 运行报告 · 20260830T111435Z_e35

- 套件：`single:E35`　离线：False　允许 API：False
- 生成时间（UTC）：2026-08-30 11:16:41
- 代码 commit：`2fd7505c6a576376b4a92aafaff6d87494765bb7`　工作区脏：True
- **source fingerprint：`50de044cce46e1dc`**（21 个源文件 + 注册表快照的哈希）　清单：`artifacts/runs/20260830T111435Z_e35/source_manifest.json`
- **source bundle：`artifacts/runs/20260830T111435Z_e35/source_bundle.zip`**（21 个文件，121515 字节，sha256 `525154fc75a3d37e3e46fd75f4d7b700327b367dedb1dc460ab84e8b11db9a26`）——**这是本次源码的最终快照**
- 工作区补丁：`artifacts/runs/20260830T111435Z_e35/source.patch`（只含 **Git 已跟踪**文件的改动；本仓库多数源码未被跟踪，因此 patch 单独**不能**还原本次运行，须叠加 bundle）
- 重建测试：**pass** 21/21 个文件哈希逐字节命中（隔离目录 `artifacts/test-runs/20260830T111435Z_e35-reconstruct/tree`）
- 复现源码：`python -m expkit.source reconstruct --run 20260830T111435Z_e35`（git archive → git apply → 解压 bundle → 重算全部哈希）
- 实验状态：已运行 1

> 本报告中的每个数字都取自本次运行落盘的 `metrics.json`，不复制 `experiments.py` 里的历史文字。标记为「已运行（仅日志）」的实验尚未接入结构化输出，其数字请看对应的 `stdout.log`，不要从这里引用。

## E35　路由的天花板：tie-aware oracle 与匹配预算的置换对照

**状态**：已运行　耗时 8.5s
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

<sub>逐题结果与 manifest：`artifacts/runs/20260830T111435Z_e35/experiments/E35/cmd2`</sub>

---
`*` 表示 95% 置信区间不跨 0。区间下界贴近 0 时不要写「显著」。
