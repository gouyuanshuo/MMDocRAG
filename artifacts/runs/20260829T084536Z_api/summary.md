# 运行报告 · 20260829T084536Z_api

- 套件：`api`　离线：False　允许 API：True
- 生成时间（UTC）：2026-08-29 08:50:10
- 代码 commit：`2fd7505c6a576376b4a92aafaff6d87494765bb7`　工作区脏：True
- **source fingerprint：`3b8b74f748f59ef3`**（20 个源文件 + 注册表快照的哈希）　清单：`artifacts/runs/20260829T084536Z_api/source_manifest.json`
- **source bundle：`artifacts/runs/20260829T084536Z_api/source_bundle.zip`**（20 个文件，105892 字节，sha256 `1bec0c3342e277986b272c12063e73bdb1dc254805d859b7f7c678fd6cd97900`）——**这是本次源码的最终快照**
- 工作区补丁：`artifacts/runs/20260829T084536Z_api/source.patch`（只含 **Git 已跟踪**文件的改动；本仓库多数源码未被跟踪，因此 patch 单独**不能**还原本次运行，须叠加 bundle）
- 重建测试：**pass** 20/20 个文件哈希逐字节命中（隔离目录 `artifacts/test-runs/20260829T084536Z_api-reconstruct/tree`）
- 复现源码：`python -m expkit.source reconstruct --run 20260829T084536Z_api`（git archive → git apply → 解压 bundle → 重算全部哈希）
- 实验状态：已运行（仅日志） 1

> 本报告中的每个数字都取自本次运行落盘的 `metrics.json`，不复制 `experiments.py` 里的历史文字。标记为「已运行（仅日志）」的实验尚未接入结构化输出，其数字请看对应的 `stdout.log`，不要从这里引用。

## E29　端到端：检索改进能否传导到生成质量

**状态**：已运行（仅日志）　耗时 81.4s
- **问什么**：k=10 上 +0.054 的检索优势，能否变成 quote-selection F1 的提升？
- **怎么做**：把两种检索配置的 top-k 写成官方 schema，用同一模型同一批题配对生成。
- **指标含义**：未检索到的 gold 用哨兵 id 计入分母，因此 F1 对检索质量敏感。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260829T084536Z_api/experiments/E29/cmd0/stdout.log`

- **限制**：BLEU/ROUGE 在此无效不可报告。gemini-3.6-flash 不在论文模型表里，因此绝对 F1 不可与论文任何一行比较；有效的只有两臂的配对比较。成本口径：2026-08-29 已对照官方定价页核验并写入 router/prices.json（标准付费层 $0.75/Mtok 输入、$3.75/Mtok 输出，verified=true）。此前曾用 gemini-2.0-flash 的未核验价 $0.10/$0.40 代算，输入低估 7.5 倍、输出低估 9.4 倍——价格表里没有该模型时，正确做法是不报美元，而不是拿最像的一条顶上。

---
`*` 表示 95% 置信区间不跨 0。区间下界贴近 0 时不要写「显著」。
