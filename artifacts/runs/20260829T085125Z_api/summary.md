# 运行报告 · 20260829T085125Z_api

- 套件：`api`　离线：False　允许 API：True
- 生成时间（UTC）：2026-08-29 08:53:31
- 代码 commit：`2fd7505c6a576376b4a92aafaff6d87494765bb7`　工作区脏：True
- **source fingerprint：`a8dd9d2f6082cbed`**（21 个源文件 + 注册表快照的哈希）　清单：`artifacts/runs/20260829T085125Z_api/source_manifest.json`
- **source bundle：`artifacts/runs/20260829T085125Z_api/source_bundle.zip`**（21 个文件，110936 字节，sha256 `804ea24bae22f853f707b30c72fe29bfe89f19e73940ee2238586b26fd87f3a0`）——**这是本次源码的最终快照**
- 工作区补丁：`artifacts/runs/20260829T085125Z_api/source.patch`（只含 **Git 已跟踪**文件的改动；本仓库多数源码未被跟踪，因此 patch 单独**不能**还原本次运行，须叠加 bundle）
- 重建测试：**pass** 21/21 个文件哈希逐字节命中（隔离目录 `artifacts/test-runs/20260829T085125Z_api-reconstruct/tree`）
- 复现源码：`python -m expkit.source reconstruct --run 20260829T085125Z_api`（git archive → git apply → 解压 bundle → 重算全部哈希）
- 实验状态：已运行 1

> 本报告中的每个数字都取自本次运行落盘的 `metrics.json`，不复制 `experiments.py` 里的历史文字。标记为「已运行（仅日志）」的实验尚未接入结构化输出，其数字请看对应的 `stdout.log`，不要从这里引用。

## E29　端到端：检索改进能否传导到生成质量

**状态**：已运行　耗时 32.1s
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

<sub>逐题结果与 manifest：`artifacts/runs/20260829T085125Z_api/experiments/E29/cmd6`</sub>

---
`*` 表示 95% 置信区间不跨 0。区间下界贴近 0 时不要写「显著」。
