# artifacts/ 的 Git 策略

**原则：本地保存全部，Git 只收轻量且可引用的部分。**

两件事必须同时成立，而它们互相拉扯：

- 每次运行的完整证据（日志、逐题结果、原始 API 响应）必须留在本地，否则结果不可追溯；
- Git 仓库不应该变成一个几百 MB、每次运行都增长、且可能含敏感内容的二进制堆。

因此 `artifacts/` **不整体忽略**，而是按「这个文件是否值得被引用和 diff」分类。

## 提交（轻量、可 diff、值得被引用）

| 路径 | 是什么 | 为什么收 |
|---|---|---|
| `artifacts/runs/*/run.json` | 运行元数据 | 几 KB；说明这次跑了什么 |
| `artifacts/runs/*/source_manifest.json` | 源码指纹 + 注册表快照 + bundle 成员哈希 | 判定源码是否相同的依据 |
| `artifacts/runs/*/source_bundle.zip` | **全部源文件的字节**（约 100 KB） | **唯一能真正还原源码的东西**，见下 |
| `artifacts/runs/*/summary.{json,md,html}` | 人读与机读报告 | 报告要能被引用和 diff |
| `artifacts/runs/*/metrics.jsonl` | 全部指标（一行一条） | 结果的机读主干 |
| `artifacts/runs/*/experiments/**/metrics.json` | 每实验结构化结果 | 小；是数字的来源 |
| `artifacts/runs/*/experiments/**/{status,command,manifest}.json` | 状态、argv、环境与哈希 | 小；复现所需 |
| `artifacts/verify/*.json` | 断言结果 | 口径是否漂移的证据 |
| `artifacts/derived/registry.json` | 产物登记表（含哈希与元数据） | 不含产物本身，只含身份 |

## 不提交（体积大、可重生成、或可能敏感）

| 路径 | 为什么不收 |
|---|---|
| `artifacts/runs/*/experiments/**/stdout.log`、`stderr.log` | 每次运行数 MB；内容已被 metrics.json 结构化 |
| `artifacts/runs/*/experiments/**/per_question.csv` | 单文件可达数百 KB×N；可由同一 commit + 数据重生成 |
| `artifacts/runs/*/summary.csv` | 是 metrics.jsonl 的展开视图，冗余 |
| `artifacts/runs/*/source.patch` | 可能很大；且工作区补丁通常不宜进仓库历史。**注意它只覆盖 Git 已跟踪的文件**，单独不足以还原一次运行 |
| `artifacts/api/**` | ⚠️ **原始请求与响应，按敏感内容对待**（见下） |
| `artifacts/derived/embeddings/**`、`indexes/**` | 向量与索引，数十至数百 MB |
| `artifacts/model_cache/**` | 真正的缓存，可从 hub 重新下载 |
| `artifacts/test-runs/**` | 测试产物，不是实验记录 |

## 为什么二进制的 source_bundle.zip 反而要提交

一般规则是「二进制、不可 diff 的东西不进 Git」，`source_bundle.zip` 是本策略里
唯一的例外，理由是把它排除掉会让**已提交的 manifest 变成半个记录**。

`source_manifest.json` 记的是每个源文件的 SHA-256。它能**判定**源码是否与某次运行
相同，但**产生不出**那份源码。补 patch 也不行：`git diff HEAD` 只看得见 Git 已跟踪
的文件，而本仓库 25 个被指纹覆盖的源文件里有 **18 个从未提交**——`experiments.py`、
整个 `expkit/`、`retrieval/nested_cv.py`、`retrieval/ablation.py` 等等。对基准 run
实测：`commit + patch` 只还原 **7/25**，其余 18 个文件缺失。

因此 bundle 是这条链上唯一承重的一环。提交 manifest 而忽略 bundle，等于把
「能验证但不能重建」这个缺陷原样搬到 Git 层。它每次运行约 100 KB。

**还原协议**（`git checkout` 绝对不要用在这个长期脏的工作区上）：

```bash
git archive --format=zip <commit> -o head.zip      # 只读，不动工作区
unzip head.zip -d tree
cd tree && git apply <run>/source.patch            # 已跟踪文件的工作区改动
unzip -o <run>/source_bundle.zip -d tree           # 权威：覆盖为真正跑过的字节
```

一条命令做完上面全部并重算每个文件的哈希：

```bash
python -m expkit.source reconstruct --run <run_id>
python -m tests.test_source_bundle --scratch-root artifacts/test-runs
```

两者在任何一个文件缺失或被改动时 **exit 1**。每次 `run-suite` 也会自动跑一遍，
结果写在 `run.json` 的 `reconstruction_test` 字段与 summary 里。

**bundle 里只有源码**：成员来自 manifest 的 `source_files`，写入时再按路径二次
排除数据集、模型、向量、索引、API 日志、response 与任何凭据形状的路径。

### 重建树是中间物，不是证据

还原协议的第一步 `git archive <commit>` 一度**不带 pathspec**，把仓库全部 419 个
已跟踪文件（**1.0 GB**，其中五个 dataset jsonl 就占了绝大部分）解进每一棵重建树，
而真正被校验的只有 25 个源文件、约 138 KB——**每棵树 99.99% 是死重**。

放大路径有两条，都在 2026-08-30 修掉：

1. `expkit/source.py` 的 `_wanted_in_tree()` 现在对 archive 成员施加与 bundle
   **同一套**排除规则。`needed`（manifest 的 `source_files` ∪ patch 的
   `diff --git` 目标）是白名单，永远解出，因此过滤**不可能**把 `git apply` 或
   `verify_tree` 变成假失败。跳过量如实记进 `run.json` 的
   `steps[0].skipped_bytes`，不是悄悄砍掉。单棵树 **965 MB → 2.3 MB**。
2. `tests/test_runner.py` 曾在给了 `--scratch-root` 时一律 `keep = True`，
   而验收命令正是 `--scratch-root artifacts/test-runs`。
   **`--scratch-root` 决定的是放哪，不是留不留。** 委托运行的 bundle 测试现在
   自己清理，只在**失败**时保留树——失败才是唯一需要看字节的场合。
   单次验收 **3.8 GB → 79 KB**。

同理，`run-suite` 的 `_reconstruction_test` 通过后删树，`run.json` 记
`tree_kept: false` 与重生成命令。**证据是那张哈希表，不是树本身。**

教训：这两处都不是逻辑错误，测试全程 50/50 通过，指纹每次都对。
它们只在**没人量过体积**时才能存活——38 棵树、36.6 GB，直到磁盘只剩 0.8 GB
才被发现。**凡是每次运行都产出目录的机制，都该把体积记进它自己的记录。**

## ⚠️ API 原始内容按敏感处理

`artifacts/api/**/requests.jsonl` 含**完整的 prompt 与模型原始响应**。即使 `redact()`
已过滤 key、Authorization、bearer/access token 等字段，这些文件仍可能包含：

- 文档正文与图片描述（数据集本身的许可条款可能限制再分发）；
- 模型输出的逐字内容；
- provider 侧的 request id 与配额信息。

**默认不进 Git，也不要在未审阅的情况下分享。** 需要保留某次运行的 API 证据时，
单独评估后用 `git add -f` 显式添加，并在 commit message 里说明已审阅。

## 发布某次 release run

想把某一次运行的完整证据固定进仓库（例如论文提交时），用：

```bash
git add -f artifacts/runs/<run_id>/
git commit -m "release run <run_id>: full evidence"
```

`-f` 是必须的，且必须显式点名某个 `run_id`——不允许 `git add -f artifacts/`
把所有历史运行一起塞进去。建议同时在 `docs/lab-notebook.html` 记录该 run_id
与它的 `source_fingerprint`。

## 检查当前会提交什么

```bash
git status --porcelain artifacts/ | head -50
git check-ignore -v artifacts/runs/<run_id>/experiments/E30/stdout.log
```
