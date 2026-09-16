# 运行报告 · 20260905T080029Z_cached

- 套件：`cached`　离线：True　允许 API：False
- 生成时间（UTC）：2026-09-05 08:02:32
- 代码 commit：`4f8f9ddf0d9ea7b98f19356c5917ee0f7c62729b`　工作区脏：True
- **source fingerprint：`32f30e4e81dd6daf`**（72 个源文件 + 注册表快照的哈希）　清单：`artifacts/runs/20260905T080029Z_cached/source_manifest.json`
- **source bundle：`artifacts/runs/20260905T080029Z_cached/source_bundle.zip`**（72 个文件，344651 字节，sha256 `26721dd8f5d294fd9e90c3a460e4ae43c4a40cb75ce01ff66405b9c82644a81d`）——**这是本次源码的最终快照**
- 工作区补丁：`artifacts/runs/20260905T080029Z_cached/source.patch`（只含 **Git 已跟踪**文件的改动；本仓库多数源码未被跟踪，因此 patch 单独**不能**还原本次运行，须叠加 bundle）
- 重建测试：**pass** 72/72 个文件哈希逐字节命中（隔离目录 `artifacts/test-runs/20260905T080029Z_cached-reconstruct/tree`）
- 复现源码：`python -m expkit.source reconstruct --run 20260905T080029Z_cached`（git archive → git apply → 解压 bundle → 重算全部哈希）
- 实验状态：已运行 2，已运行（仅日志） 2

> 本报告中的每个数字都取自本次运行落盘的 `metrics.json`，不复制 `experiments.py` 里的历史文字。标记为「已运行（仅日志）」的实验尚未接入结构化输出，其数字请看对应的 `stdout.log`，不要从这里引用。

## E19　自适应预算分配：上界远小于原报数字

**状态**：已运行（仅日志）　耗时 33.0s
- **问什么**：逐题分配文本/图片配额，有多少可争取的空间？
- **怎么做**：计算 21 种配额的逐题 Recall 曲线，审计并列最优，改用 oracle−best-fixed regret。
- **指标含义**：真实 regret 上界 0.069/0.074；约 79% 问题固定配额已最优。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260905T080029Z_cached/experiments/E19/cmd0/stdout.log`

- **限制**：原 +0.173~+0.179 受 argmax 恒取最小并列索引影响，已作废。

## E20　真实规模自建池上复现 E19

**状态**：已运行（仅日志）　耗时 28.7s
- **问什么**：E19 的结论是不是池偏差造成的？
- **怎么做**：重建更大的文本 chunk 池，保持同一 QA、gold 与图片侧重跑。
- **指标含义**：方向一致说明结论对文本池规模有一定稳健性。
- **统计单位**：document（bootstrap 按此重采样）
- **数字**：本实验尚未接入 metrics.json，见日志 `artifacts/runs/20260905T080029Z_cached/experiments/E20/stdout.log`

- **限制**：不是独立复现；视觉池仍相同且不完整。

## E29　端到端：检索改进能否传导到生成质量

**状态**：已运行　耗时 19.0s
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

<sub>逐题结果与 manifest：`artifacts/runs/20260905T080029Z_cached/experiments/E29/cmd2`</sub>

## E34　论文式基线：bge-large 文本检索器与完整图片池的 ColQwen 量级核对

**状态**：已运行　耗时 4.0s
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

<sub>逐题结果与 manifest：`artifacts/runs/20260905T080029Z_cached/experiments/E34/cmd1`</sub>

---
`*` 表示 95% 置信区间不跨 0。区间下界贴近 0 时不要写「显著」。
