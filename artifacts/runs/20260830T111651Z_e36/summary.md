# 运行报告 · 20260830T111651Z_e36

- 套件：`single:E36`　离线：False　允许 API：False
- 生成时间（UTC）：2026-08-30 11:25:06
- 代码 commit：`2fd7505c6a576376b4a92aafaff6d87494765bb7`　工作区脏：True
- **source fingerprint：`44b27b7363b4727f`**（21 个源文件 + 注册表快照的哈希）　清单：`artifacts/runs/20260830T111651Z_e36/source_manifest.json`
- **source bundle：`artifacts/runs/20260830T111651Z_e36/source_bundle.zip`**（21 个文件，124924 字节，sha256 `d6ec3570f9ba664455a7489b4c0e69934613ac1c78efb4a6aed323c57151cc6f`）——**这是本次源码的最终快照**
- 工作区补丁：`artifacts/runs/20260830T111651Z_e36/source.patch`（只含 **Git 已跟踪**文件的改动；本仓库多数源码未被跟踪，因此 patch 单独**不能**还原本次运行，须叠加 bundle）
- 重建测试：**pass** 21/21 个文件哈希逐字节命中（隔离目录 `artifacts/test-runs/20260830T111651Z_e36-reconstruct/tree`）
- 复现源码：`python -m expkit.source reconstruct --run 20260830T111651Z_e36`（git archive → git apply → 解压 bundle → 重算全部哈希）
- 实验状态：已运行 1

> 本报告中的每个数字都取自本次运行落盘的 `metrics.json`，不复制 `experiments.py` 里的历史文字。标记为「已运行（仅日志）」的实验尚未接入结构化输出，其数字请看对应的 `stdout.log`，不要从这里引用。

## E36　逐题路由：GPU 决策可学，CPU 融合决策不可学

**状态**：已运行　耗时 379.1s
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

**限制**：exploratory：该切分自 E9 起被反复观察并用于挑方法。oracle regret 仍然很大（+0.034 ~ +0.070），路由器只实现了可得空间的约十分之一，**不能**写成「路由有效」，只能写成「在图片侧的升级决策上存在可学的逐题信号，且它买到的是成本而不是质量」。B=0.05~0.15 这个「追平静态系统的预算」是看着曲线读出来的，属描述性数字，不是检验。端到端生成质量未测——本条全部指标是 evidence recall，要接到 F1 需要一次配对 API 运行，未做。

<sub>逐题结果与 manifest：`artifacts/runs/20260830T111651Z_e36/experiments/E36/cmd0`</sub>

---
`*` 表示 95% 置信区间不跨 0。区间下界贴近 0 时不要写「显著」。
