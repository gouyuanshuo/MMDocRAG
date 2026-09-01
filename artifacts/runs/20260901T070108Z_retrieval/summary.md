# 运行报告 · 20260901T070108Z_retrieval

- 套件：`retrieval`　离线：True　允许 API：False
- 生成时间（UTC）：2026-09-01 07:01:43
- 代码 commit：`a42cda468120916bbb0170416212a4505f89f6ea`　工作区脏：True
- **source fingerprint：`4b4afc9e7821262a`**（18 个源文件 + 注册表快照的哈希）　清单：`artifacts/runs/20260901T070108Z_retrieval/source_manifest.json`
- **source bundle：`artifacts/runs/20260901T070108Z_retrieval/source_bundle.zip`**（18 个文件，119682 字节，sha256 `764f45ffb3b359377e27bc2e40f483ad0287f9e9b8e04f8f108f9ea16d5b721e`）——**这是本次源码的最终快照**
- 工作区补丁：`artifacts/runs/20260901T070108Z_retrieval/source.patch`（只含 **Git 已跟踪**文件的改动；本仓库多数源码未被跟踪，因此 patch 单独**不能**还原本次运行，须叠加 bundle）
- 重建测试：**pass** 18/18 个文件哈希逐字节命中（隔离目录 `artifacts/test-runs/20260901T070108Z_retrieval-reconstruct/tree`）
- 复现源码：`python -m expkit.source reconstruct --run 20260901T070108Z_retrieval`（git archive → git apply → 解压 bundle → 重算全部哈希）
- 实验状态：跳过 1

> 本报告中的每个数字都取自本次运行落盘的 `metrics.json`，不复制 `experiments.py` 里的历史文字。标记为「已运行（仅日志）」的实验尚未接入结构化输出，其数字请看对应的 `stdout.log`，不要从这里引用。

## E40　E27 头条在 bge-large 上复核：提升不是弱编码器的产物

**状态**：跳过　（本实验没有 replay 安全的命令（其命令会重建产物））　耗时 0.0s
- **问什么**：E27 的 +0.061 是真实的配置提升，还是 bge-small 太弱制造出来的？换成本项目唯一字节可证、且更接近论文规模的文本检索器之后，四格还剩几格？
- **怎么做**：与 E27 完全相同的 document-grouped 5 折折外协议，只把 dense 文本臂换成 models/bge-large-en-v1.5。
- **统计单位**：document（bootstrap 按此重采样）

- **限制**：本条只搬了 E27。其余 14 个依赖 bge-small-vlm 的实验仍是 bge-small 的结果，作为历史记录保留；其中 E35/E36/E37 的增益是两臂同时换编码器的相对量，对编码器不敏感，但**尚未实测**，不应写成已复核。同样地，这条切分自 E9 起被反复观察，本结果与 E27 一样只能标 exploratory。

---
`*` 表示 95% 置信区间不跨 0。区间下界贴近 0 时不要写「显著」。
