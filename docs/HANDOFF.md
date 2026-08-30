# MMDocRAG 项目交接

> 写于 2026-08-30。给下一个会话（或换回来的我自己）直接接手用。
> **先读这份，再读 `docs/lab-notebook.html`。** 前者是地图，后者是每个实验的完整叙述。
> 可执行的权威记录是 `experiments.py`——每条实验都带着产出它数字的确切命令。

---

## 0. 三十秒版本

课程项目（UTS 32933 Research Project, Spring 2026, Type I 原型研究），
proposal 标题是 *Hierarchical Query-Conditioned Routing for Efficient and
Faithful Multimodal Document RAG*。

**已经建成一条完整的因果链，每一环都有区间和口径：**

```
canonical 数据层
   → 检索配置改进        E27  nested CV 四格全显著
   → 组件归因            E30  Holm 校正后 12/12 存活
   → 答案质量            E29  +2.90 F1，CI [+1.01,+4.77]，p=0.0025
   → 基线加强后仍成立     E34  换 bge-large 后 k=10 提升不降反升
```

**proposal 标题承诺的「逐题路由」已经做完（E35/E36），但它交付的是成本结论而不是质量结论。**

```
E35 天花板   一半 CPU 预算下完美选择 − 静态 RRF = +0.040 ~ +0.052（四格全显著）
             同预算最优固定动作 − 静态 RRF     = −0.016 ~ −0.022
             → 路由器要补的缺口 ≈ 该预算内 oracle 空间的三成
E36 实测     以下为「特征组事先固定」的口径，折内选特征组的口径另列，两者不可混
             CPU 融合决策  够不到（同预算相对随机 0/4 存活 Holm，capture −0.9%~8.6%）
             GPU 升级决策  够到一部分（3/4 存活 Holm，capture 10.2%~11.8%；
                           特征组改为折内选择时降到 1/4 存活，四格点估计仍全为正）
             → 在质量差异不显著的前提下，ColQwen 调用从 100% 降到 5%~15%，
               CPU 遍历相应多付 2%~7%（两种货币不相加，只能这样并列写）
```

于是项目有**两条并列且不可互相顶替**的表述：静态配置的改进是**质量**结论
（E27 → E29 端到端 +2.90 F1）；逐题路由的结果是**成本**结论。两条都是 exploratory。

---

## 1. 环境与硬约束

| 项 | 值 |
|---|---|
| 代码 | `D:\Playground\MMDocRAG` |
| 数据 | `D:\Dataset\MMDocRAG`（图片在 `images\images\`，注意是两层） |
| proposal | `E:\Courses\2026 Spring 32933 Research Project\Research_Project_Proposal.docx` |
| GPU | RTX 4060 Laptop **8 GB**——ColQwen2 权重就占 4.49 GB |
| 磁盘 | D 盘常年只剩几十 GB，且与 Ollama 模型、其他工程共享 |
| Python | 3.13.7，torch 2.6.0+cu124 |
| 第二个 venv | `.venv-colpali`（colpali-engine 要 transformers≥5，主环境锁在 4.57.3） |
| HF 缓存 | `D:\AI\HuggingFace`（`HF_HOME` 已设） |

**跑不了**：`inference_checkpoint.py`（7B+ 推理）、`train_swift_qwen.py`（ms-swift 微调）。
**生成侧走 API**（Gemini 付费层），检索与 router 侧本地跑。

### 会话执行模型（吃过大亏，务必先读）

- **后台任务活不过回合边界。** 观察到被杀的间隔从 9 分钟到 48 分钟不等，
  且我的回合一结束就必被杀。
- **前台 Bash 单次最长 600 秒。**
- 结论：**任何超过 8 分钟的任务都必须自带检查点并可续跑**，然后用多次前台调用推进。
  没有检查点的长任务在这个环境里等于必然全损——本会话为此损失过 2h13m + 33min。

---

## 2. 已完成（E1–E36）

完整叙述见 `docs/lab-notebook.html`。这里只给状态与最要紧的数字。

### 数据层（E1–E7）
- **E1** 复现锚点：`gemini-2.0-flash` C20 multimodal 全 17 项指标与论文逐位一致。
- **E4** 关键结构发现：quote 的局部编号（`text5`/`image7`）**不是全局 ID**，
  同题 gold 在 15 档/20 档下局部 ID 仅 4.6% 相同、canonical 身份 100% 相同。
  `q_id` 也不是主键（dev/eval 各自从 0 编号），主键必须是 `(split, q_id)`。
- **E5** Gate 1：21,978 条 gold **100%** 可映射到 `(doc,page,layout)`。
- **E6** Gate 2：自建 chunk 能匹配回官方 gold text 的比例 **98.63%**。
  精确子串只能到 82%（MinerU 会往 gold 里塞幻觉字形），**必须用字符 8-gram 重叠**。
- **E7** 全语料 OCR：14,763 页，补 OCR 后无文本页从 1,748 降到 357。

### 生成输入层的模态路由（E8–E12）—— **负结果，已结案**
- **E9**：证据已给定时，逐题选「真图喂 VLM」还是「文字描述喂 LLM」**不可预测**。
  决定性证据是**跨模型 Cohen's kappa 均值 0.038，171 个模型对中 0/171 超过 0.2**。
- **E8** 是必须带走的方法学纪律：**per-question oracle 增益大 ≠ 有可路由的空间**。
  选两个含噪声测量的较大者本身就产生正增益。**任何 adaptive 工作报 oracle 上界时都要跑对照。**
- **E10** 正面产出：模态选择的成本-质量表。多模态在大多数模型上不值得买，
  13 个 token 可信模型里 **6 个被纯文本严格支配**。
- **E12**：我自己跑的 OCR **消解了我自己的立论**（「28~30 篇文档对文本检索完全不可见」
  在补 OCR 后变成 0 篇）。立论方式因此从「结构性」改为「实证性」。

### 检索层（E13–E27, E30）
- **E14** 模态信号是**粒度依赖**的：页粒度上文本检索对视觉 gold 没有劣势
  （R@10 差 +0.015），quote 粒度上才出现论文 Table 6 的双向交叉。
- **E15**：「图片 quote 更好检索」**不是**可路由信号，是**池组成的产物**
  （k≥10 处贡献几乎全部来自池大小）。
- **E19/E23** 两次自我推翻：oracle 上界被高估；高维特征一直在埋掉低维真信号。
- **E27 主结果**：nested CV 选出的配置相对最接近论文的本地对照，
  k=10 为 **+0.061 / +0.054**（两个池），k=20 为 +0.030 / +0.027，四格全显著。
  选出的配额是 **{10:(4,6), 15:(7,8), 20:(9,11)}**——注意**不是**通用的 5/5。
- **E30** 归因消融：Holm 校正后 12/12 比较存活。

### 逐题路由（E35–E36）—— **一半正向，且是成本而非质量**
- **E35 先做天花板，不先写 router**（这是 §4① 当时定下的顺序，照做了）。
  12 个动作（文本检索器 3 × 图片侧 4），固定配额，两种货币分开记：
  `cpu_passes`（对分支候选池的单检索器遍历，RRF 记 2）与 `gpu_passes`（ColQwen 后交互）。
  **本项目没有测过两者的兑换率，所以预算是一对上限而不是一个标量。**
- **tie 与配比这两种高估被分别量化**：97.5% 的题有多个最优动作，
  **47.9% 的题 12 个动作完全同分**（33.4% 全对、1.9% 全错），
  最优固定动作对 77.0% 的题已经最优。E19 式 argmax 破 tie 让表观空间虚高 +0.009~+0.013。
- **约束下界这次是最优固定动作，不是置换对照**（0.7101 vs 0.6844），
  与 E19 方向相反 —— 说明 oracle 的优势确实是逐题的，不是动作配比带来的。
- **E36 主对照是同预算下的随机分配**，不是「比不升级好」。八格一个 Holm 家族。
  GPU 级联 3/4 存活（特征组事先固定时），CPU 级联 0/4。
- **把特征组也放进折内选择后只剩 1/8 存活**，GPU 四格点估计仍全为正。
  原因是内层目标在 1,200~1,600 样本上选不稳特征组（40 个 fold 换了 5 种组合，
  6 次选中含句向量的组）。**两种口径都必须报。**
- **Policy A（检索前就选检索器）是干净的负结果**：四种特征组全部输给折内最优固定动作，
  与 E17 一致。

### 端到端（E29）—— **正向**
600 题配对生成，两臂同模型、同 prompt、同 gold，只有候选块不同：

| 臂 | 配置 | final_f1 |
|---|---|---|
| paper | dense 文本 + ColQwen 视觉，配额 7/3 | 55.21 |
| ours | RRF 文本 + RRF 视觉，配额 **4/6** | **58.11** |

**Δ = +2.90 F1，document-cluster 95% CI [+1.01, +4.77]，p = 0.0025**，
220 篇文档 / 600 题，210 胜 / 156 负 / 234 平。增益几乎全在图片侧（img_f1 +5.0）。
实际花费 **12.09 AUD / 1,225 次调用**。

### 论文式基线（E34）—— **正向，但有一半未完成**
- **核对推翻两条我自己的说法**：论文**没有给出任何检索器的版本**（Table 6 只列族名）；
  ColQwen2-v1.0 **早已在本地且真跑像素**，从来不需要下载。
- 真正的主缺口是**图片池规模**：论文 63 图/篇，此前只有 29.8（官方候选并集，
  被问题条件化 → recall 乐观偏置）。
- **k=10 的头条提升没被更强基线吃掉，反而变大**：
  G−E 在 selfbuilt 池 +0.0473\* → **+0.0605\***。
  机制：对照臂自己也用 dense 检索器，两臂一起变强；而我方用 RRF，融合受益更多。
- **必须撤回一条**：「ColQwen 读像素优于图片描述检索」在 k=20 的显著性
  （+0.0220\* → +0.0086，跨 0）**是文本检索器太弱造成的**。
- **未完成**：ColQwen 全池索引只做了 **5/220 篇**，见 §4。

---

## 3. 基础设施（E31–E33）

### 可复现运行系统 `expkit/`
```bash
python experiments.py list                    # 一行一个实验
python experiments.py show E27                # 详情、命令、限制
python experiments.py run-suite replay --offline
python experiments.py verify E24              # 断言有争议的数字
python experiments.py report latest
python experiments.py corrections             # 每一个被推翻的旧数字
```
每次 run 写到 `artifacts/runs/<run_id>/`：完整 stdout/stderr、每个实验的
`status.json`、机器可读 metrics、per-question CSV、四种 summary。**不覆盖任何旧 run。**

### source bundle（E33）
`source_manifest.json` 只能**判定**源码是否相同，**产生不出**源码——
`git diff HEAD` 只看得见已跟踪文件，而 25 个被指纹覆盖的源文件里 **18 个从未提交**。
实测 `commit + patch` 只还原 7/25。所以每个 run 额外写 `source_bundle.zip`
（tracked + untracked 一视同仁），并当场重建一棵树重算全部哈希，结果写进 `run.json`。

**重建树是中间物，不是证据**——通过即删（`tree_kept: false`），失败才保留。
这条是被 36.6 GB 的教训换来的，见 §5。

### 测试
```bash
python -m tests.test_runner --scratch-root artifacts/test-runs     # 64 项
python -m tests.test_source_bundle --scratch-root artifacts/test-runs  # 21 项
python -m tests.test_phase3                                        # 33 项
```
**当前全绿：测试 64/0 + 33/0，verify E24 68/0，verify E27 61/0。**

`tests/test_phase3.py` 断言的是 Phase 3 数字成立所依赖的性质，而不是代码长什么样：
动作缓存截断到 top-32 后每个 recall 逐位不变；级联特征只读它真的跑过的那个检索器
（把另一个检索器的分数改成 −99 倍，特征必须一位不动）；升级成本按增量计费；
随机对照确实是它自称的那个精确期望；折外预测真的在折外
（纯文档效应的目标在折内可学、折外不可学）。

---

## 4. 剩余工作（按建议优先级）

### ① 把 E36 的 GPU 级联接到端到端生成 ← **建议下一步**
Phase 3 现在全部指标是 **evidence recall**。「同质量下 ColQwen 调用降到 5%~15%」
这句话**在 F1 上尚未验证**。需要一次配对 API 运行，照 E29 的做法：
同模型、同 prompt、同 gold，只有候选块不同，两臂是

- 静态臂：`rrf text + colqwen visual`（每题都调 ColQwen）
- 路由臂：`router/phase3_cells.py` 在 B≈0.15 处的升级决策（逐题落盘在 per_question.csv）

预算参照 E29：600 题、1,225 次调用、12.09 AUD。**开跑前先定死 thinking 开关**（§5.3-12）。
若 F1 差值的 CI 包含 0 而 ColQwen 调用少了 85%，那就是本项目最干净的成本结论。

### ② 补完 ColQwen 全池索引
机制全部就绪且测试通过，只差 GPU 时间（**5–9 小时**）。显存空闲时：
```bash
.venv-colpali/Scripts/python.exe -m retrieval.colqwen_index \
    --image-source fulldisk --doc-order random \
    --out retrieval/colqwen_scores_fullpool.sqlite
python -m retrieval.eval_fullpool
```
- `--doc-order random` 让**任何停止点都是文档的简单随机样本**，部分索引也可报告。
- 文档内检查点：660 张图的文档也能跨窗口续跑。
- **待验证的预测**：候选池上本项目 Recall@10 = 0.820，论文 0.708；
  补齐池后应当**下降并逼近 0.708**。不降就说明差距从来不是池造成的。
- **前提**：Ollama 的 `llama-server.exe` 不能占着 GPU（它会拿 3.26 GB，
  剩下的放不下大图激活，表现是模型能加载但一片都写不出来）。

### ③ 写报告
材料已经够了。写的时候注意 Phase 3 的两条口径必须并列出现（特征组事先固定 vs 折内选择），
以及 §5.1-4：这条切分自 E9 起被反复观察，**Phase 3 的结论同样只能标 exploratory**。

### 已明确不做
- 让描述分支也上全池 —— 需为 8,943 张图补 VLM 描述，付费，未批准。
- Phase 4 粒度 / Phase 5 dynamic top-k —— proposal §16 属「最好完成」与「扩展」，可裁。

---

## 5. 踩过的坑（**这一节最值钱**）

### 5.1 统计与口径
1. **重采样单位必须与真实抽样单位一致。** 396 题只来自约 55 篇文档，
   按题 bootstrap 会低估区间。用 **document-cluster bootstrap**。
   但注意一个反直觉观察：**聚类不必然放宽区间**——E29 里按题
   [+0.94,+4.99] 反而略宽于按文档 [+1.01,+4.77]。用它的理由是**单位匹配**，
   不是「它更保守」。
2. **分母不能被静默改变。** 无法评价的 gold 默认计为 miss 进 unconditional recall，
   另行报映射覆盖率。要报子集口径就必须单独命名 conditional-on-mapped。
   每次评测都打印 QA 数 / gold 数 / mapped 数 / dropped 数。
3. **CI 下界贴 0 不能写「显著」**；多 k 多系统比较要说明多重比较。
4. **被反复观察并用于挑方法的切分不再是干净确认集**——只能标 exploratory。
5. **oracle 上界大 ≠ 有可路由空间**（E8）。报上界必须带对照。

### 5.2 基线身份
6. **只有当基线真的复现了被比较论文的系统，才能说「优于已发表配置」。**
   否则命名为 *local surrogate baseline* / *closest local paper-style baseline*。
7. **不要把自己的推断说成论文原文。** MMDocRAG 论文**没有给出任何检索器的版本**，
   我却一度把「bge-large-en-v1.5 / ColQwen2-v0.1」当成论文配置写进代码与记录。
8. **术语纪律**：在 VLM 描述上跑 BM25/稠密检索叫 **image-description retrieval**，
   **不能**叫 visual retrieval——它根本没看像素。

### 5.3 成本
9. **价格表里没有该模型本身、已核验的条目时，不报美元，只报 token。**
   曾用 gemini-2.0-flash 的价算 gemini-3.6-flash，输入低估 7.5×、输出低估 9.4×。
10. **预算按 `total_tok`，不是 `in_tok + out_tok`。** thinking token 按**输出价**计费，
    占计费输出的 **81%**。
11. **provider 的计费面板是地面真值**，早期就要对一次账，差超一成说明计费模型漏了东西。
12. **thinking 开关属于开跑前的决定**——配对比较中途改开关等于把已花的钱作废。

### 5.4 执行工程（本会话新增，代价最惨重）
13. **绝不把长任务的输出接进 `tail`/`grep`/`head` 管道。**
    tqdm 高频写 stderr，管道缓冲写满后**进程阻塞在写操作上**，吞吐从 50/s 掉到个位数，
    而且整整两小时看不到一行进度。**一律 `> log 2>&1`，要看进度就另外去读文件。**
14. **长任务必须自带检查点**（见 §1 会话执行模型）。写分片要
    先写临时文件再 `os.replace`，载入时**校验行数/跨度**——被截断的分片若被当成完好的，
    任务会「成功」结束却带着错误数据。
15. **`np.save` 会给不以 `.npy` 结尾的路径自动追加 `.npy`**，
    所以 `np.save(p + ".tmp", a)` 实际写的是 `p.tmp.npy`，随后的原子改名必然
    `FileNotFoundError`。要传**已打开的文件句柄**。
16. **`os.path.relpath` 跨 Windows 盘符抛 `ValueError`**——为了打印好看的相对路径
    而崩掉整个任务不值得，用 try/except 兜住。
17. **检查点的键必须包含批大小。** 分片 `0` 在 batch=2 下是图 0–1、batch=4 下是图 0–3；
    只按偏移命名会让改批大小后的重跑命中旧分片却只拿到一半图片。
    实际后果：某文档「成功」完成但 **192 张图只排了 106 张**，不报任何错。
18. **每个 `encode()` 都重建模型会让吞吐掉 3 倍。** 分片化之后同一语料
    要付 23 次模型构造。已改为进程内缓存。
19. **凡是每次运行都产出目录的机制，都要把体积写进它自己的记录。**
    38 棵重建树吃掉 **36.6 GB**（`git archive` 无 pathspec，把整个仓库含数据集
    解进每棵树），直到 D 盘只剩 0.8 GB 才被发现。测试全绿、指纹全对——
    它们只在**没人量过体积**时才能存活。
20. **`--scratch-root` 决定的是放哪，不是留不留。** 中间物只在失败时值得保留。
21. **`git apply` 会向上找仓库。** 往仓库内的目录打补丁时它会认到本仓库、
    打印 `Skipped patch` 并**退出 0**。必须设 `GIT_CEILING_DIRECTORIES` 并检查输出，
    不能只看退出码。
22. **Windows 无开发者模式时 `huggingface_hub` 建不了符号链接缓存**（WinError 1314），
    且 xet 传输后端会挂起。用 `retrieval/fetch_model.py` 落成平铺目录。
23. **删目录树前先查 junction/符号链接**，`rm -rf` 会跟进去删到目标。
24. **批量删除前先确认不碰付费 API 产物**（`response/`、`artifacts/api/`）——
    它们花了真金白银且不可再生。
25. **这个 shell 的 heredoc 会被单双引号打断。** `cat > f <<'EOF'` 里只要出现
    `'` 或 `"`，就会报 `unexpected EOF while looking for matching`，而且**文件不会被创建**。
    写含引号的 Python/文本一律用 Write 工具，或先把补丁脚本写到 scratchpad 再执行。

### 5.6 Phase 3 新增的纪律
26. **约束下界是「最优固定策略」与「保配比置换对照」中更强的那个**，
    而哪个更强必须从数据读出来。E19 里置换对照更高，E35 里反过来。两个都要报。
27. **预算实验的主对照是同预算的随机分配。**「比不升级好」是废话——
    升级本身就多做了检索。只有在同样预算下胜过随机挑谁升级，才说明路由器懂 query。
28. **级联的升级成本按增量算，首轮做了而升级用不上的那一遍是沉没成本、不退款。**
    用「从零跑两个动作的成本之差」当增量会让级联显得更便宜：GPU 级联在 B=1 时是
    3 cpu + 1 gpu，比直接跑静态系统（2 cpu + 1 gpu）**更贵**。成本参照系是静态系统。
29. **对照的期望能算就不要抽样。** 均匀随机升级 m/n 时第 i 题的期望恰是
    `base_i + (m/n)·gain_i`。用几百次抽样去估它等于给唯一承载主张的对照加一层
    蒙特卡洛噪声——本实验里那点噪声足以让 Holm 校正后的 p 跨过 0.05。
30. **每格结果各自播种。** 八格共用一条 RNG 流时，「跑全部八格」与
    「用四格缓存再跑四格」会消耗掉不同数量的随机数，同一条命令因此打印不同的数字。
    按格的身份（crc32，不是 `hash()`，后者每进程加盐）派生种子。
31. **E23 的教训要上升一层**：不只是「别把 384 维句向量拼进低维特征」，
    而是「在这个样本量下，连**该不该拼进去**都选不准」——
    折内选择在 40 个 fold 里换了 5 种特征组，主家族存活数从 3/8 掉到 1/8。

### 5.5 我犯过的具体错误类型（用于自查）
- **行数 vs 实体数**：把 30 行文件当成 30 条完成记录（实际只有 15 条有响应）；
  把 6,548 条 evidence row 除以 13,999 张唯一图片得到「46.8%」，单位不一致。
- **按题加权 vs 按文档**：「每篇文档中位 29 个图片候选」是按题加权的数，
  按文档中位数是 20。
- **同一个 cursor 既做外层迭代又做内层查询**，会把游标冲掉、静默漏掉后续行。
- **同时改两个变量却归因给一个**：`RRF(描述) − ColQwen` 同时改了表示与检索架构，
  不能叫「隔离了表示」。
- **把展示标签当成规范键**：注册表的 `status` 规范键是 `"pos"`，其中文标签才是「正向」。
  我一度直接写 `status="正向"`，`experiments.py show` 于是对 E29/E34 抛 `KeyError`——
  而 `list` 和 `run-suite` 都不碰这张表，所以缺陷藏了整整两个实验才暴露。
  **改了注册表字段之后，把每一条都渲染一遍**：
  `for id in $(python -c "import experiments as E; print(' '.join(x['id'] for x in E.E))"); do python experiments.py show $id >/dev/null || echo FAIL $id; done`

---

## 6. 文件地图

### 必须复用、不要重写
| 文件 | 为什么 |
|---|---|
| `eval_all.py:extract_citations` / `get_scores` | 官方口径的引用抽取与 P/R/F1。任何 F1 都必须走这条路径，否则与论文和项目内其它数字不可比 |
| `data_utils.py` | `load_jsonl` / `save_jsonl` / `encode_image` |
| `prompt_bank/*.txt` | 三个官方 prompt，Phase 2 起固定不变 |

### 数据层
| 路径 | 内容 |
|---|---|
| `canonical/mmdocrag.sqlite` | 48M。`questions` 4,055、`canonical_evidence` 25,716、`question_candidates` 141,480、`question_gold_evidence` 21,978、`question_settings` 8,110 |
| `retrieval/quotes.sqlite` | 57M。自建 chunk 92,752（421/篇）+ `gold_map` 3,151 |
| `retrieval/pages.sqlite` | 50M。页级语料 14,763 页 |
| `retrieval/colqwen_scores.sqlite` | 8.6M。**候选池** ColQwen 排名，69,842 行、6,548 张图 |
| `retrieval/colqwen_scores_fullpool.sqlite` | 168K。**全池**索引，只有 5/220 篇 |
| `manifests/split_doc_disjoint.json` | 冻结的 document-disjoint 切分 |
| `manifests/e29_subset.json` | E29 的 600 题子集 |

### 模型（本地，勿重下）
- `models/colqwen2-v1.0`（86M LoRA）+ `models/colqwen2-base`（8.3G）
- `models/bge-large-en-v1.5`（1.3G）——**本项目唯一字节可证的模型**，
  `fetch.json` 记录 revision `d4aa6901d3a41ba39fb536a557fa166f842b0e09` 与逐文件
  SHA-256，`python -m retrieval.fetch_model BAAI/bge-large-en-v1.5 --check` 可复验。

### 关键脚本
| 文件 | 作用 |
|---|---|
| `experiments.py` | 实验注册表 + 运行器。**权威可执行记录** |
| `expkit/` | run 系统：`runner` `results` `report` `source` `verify` `apilog` `artifacts` `paths` |
| `retrieval/eval_stack_v2.py` | **E27 的报告脚本**（`eval_stack.py` 保留但已过时）。`--pool {selfbuilt,canonical}` `--k` `--dense-model` |
| `retrieval/nested_cv.py` | nested CV 选配置 |
| `retrieval/ablation.py` | E30 归因消融 |
| `retrieval/colqwen_index.py` | ColQwen 索引。`--image-source {canonical,fulldisk}` `--doc-order random`，**在 `.venv-colpali` 里跑** |
| `retrieval/eval_colqwen.py` | 候选池上的配对比较。**检测到 `unpooled:` 会 exit 1** |
| `retrieval/eval_fullpool.py` | 全池 ColQwen 绝对 recall，对标论文 Table 6。**候选池索引会 exit 1** |
| `eval_e29_paired.py` | E29 配对分析。**算任何区间前先断言均值复现 `eval_all` 的打印值** |
| `router/` | Phase 1A.5 的模态路由（负结果）+ `cost_quality.py` 成本表 |
| `router/actions.py` | **Phase 3 底座**。复用 `eval_stack_v2.build(keep_scores=True)` 缓存逐题 12 动作 × recall × 成本；`cost` / `incremental_cost` / `cascade_cost` 两种货币分开 |
| `router/tie_audit.py` | **E35**。tie-aware oracle、保配比置换对照、按预算子空间的天花板 |
| `router/features_p3.py` | Phase 3 特征，按**何时可得**分组：shape / qtext / emb / firstpass |
| `router/budget_router.py` | **E36 单格**。Policy A（检索前选）与 Policy B（级联），折外 + 折内选模型 |
| `router/phase3_cells.py` | **E36 主表**。八格一个 Holm 家族，每格落盘可续跑（`router/cache/cells/`） |
| `router/cache/` | Phase 3 缓存，**9.8 MB**（两张 ~5 MB 动作表 + 16 个小 JSON）。已 gitignore：可再生且不是证据，权威记录是 run 的 metrics.json |
| `tests/test_phase3.py` | 33 项。截断无损、特征不越权、增量计费、随机对照精确、折外真在折外 |

### 文档
- `docs/lab-notebook.html` —— 叙述性主记录，每个实验一条
- `docs/paper-baseline-audit.md` —— 论文式基线逐项核对（E34）
- `docs/artifacts-git-policy.md` —— 什么进 Git、什么不进、为什么 bundle 要进
- `docs/audit-e27.html` —— E27 审计

### 一条已查清并修好的报告路径缺陷（2026-08-30，发现于 Phase 3 的回归核对）
做 Phase 3 时顺手核对 E27 有没有被我的改动碰坏，发现**打印出来的 CI 与
metrics.json 里记的 CI 不一样**：selfbuilt k=10 打印 [+0.0471,+0.0748]，
记录 [+0.0468,+0.0753]。

原因不是我的改动，而是 `nested_cv.py` **对同一个比较调了两次 `cluster_ci`**，
一次给打印的表格、一次给 metrics 块，两次从**同一条前进中的随机流**里抽了
不同的 bootstrap 样本。点估计一直是同一个数（`0.06081109307359307` 逐位不变），
只有区间端点在第三位小数上分叉。因为 metrics.json 才是权威记录，
**错的是打印出来的那张表**。

已修：算一次、两处共用。记录值随之变成 [+0.0471,+0.0748]，四格符号与显著性不变。
已在 E27 的 `note` 里写清楚。同时确认：为 Phase 3 给 `eval_stack_v2.build` 加的
`keep_scores` / `top_keep` 在默认关闭时是死代码，E27 四个点估计逐位复现。

**可复用的检查**：凡是既打印又落盘同一个 bootstrap 量的脚本，
都要确认它只抽了一次。已逐个查过 `eval_stack_v2.py`、`ablation.py`、
`tie_audit.py`、`phase3_cells.py`、`budget_router.py`——只有 `nested_cv.py` 有这个毛病。

---

## 7. 接手第一步建议

```bash
cd D:\Playground\MMDocRAG
python experiments.py list                 # 看全景
python experiments.py show E36             # 看最近一条（Phase 3 路由）
python experiments.py show E35             # 它的天花板前提
python -m tests.test_runner --scratch-root artifacts/test-runs   # 确认 64/0
python -m tests.test_phase3                                      # 确认 33/0
python experiments.py run-suite replay --offline                 # 确认全链可复算
```

**Phase 3 已经做完（E35/E36），§4① 现在是另一件事**：把 E36 的 GPU 级联接到
端到端生成，因为 Phase 3 全部指标还是 evidence recall，「同质量下少调 85% 的
ColQwen」这句话在 F1 上尚未验证。那是唯一需要花钱的一步，开跑前先读 §5.3。

要重看 Phase 3 的结论，直接跑这两条（都有缓存，秒级到分钟级）：

```bash
python -m router.tie_audit --pool selfbuilt --k 10      # 天花板与两个对照
python -m router.phase3_cells --features shape+firstpass  # 八格 + Holm
python -m router.phase3_cells --features search            # 特征组也折内选的口径
```

**两种口径必须并列读**，不能只引强的那个：见 §2「逐题路由」与 §5.6-31。
