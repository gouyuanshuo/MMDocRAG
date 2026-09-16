# 更正：原论文确实列出了检索器 checkpoint

2026-09-05 查阅 [arXiv v2 附录 C.3、Table 14](https://arxiv.org/html/2505.16470v2)，确认以下项目：

| 检索器 | 论文列出的 Hugging Face checkpoint | 本地实际使用 |
|---|---|---|
| BGE | `BAAI/bge-large-en-v1.5` | 早期 BGE-small；E40 为 BGE-large |
| ColQwen | `vidore/colqwen2-v0.1` | `vidore/colqwen2-v1.0` |

因此，旧 `paper-baseline-audit.md`、`HANDOFF.md`、`AGENTS.md` 以及 E34 原始说明中“论文没给任何版本/HF id”的断言有误。原审计只查看正文和 Table 6，遗漏了附录的实现表。该断言明确撤回。

“本地论文式基线”的命名继续适用：本地视觉 checkpoint、语料构造、候选池和部分处理设置没有与论文全流程对齐。BGE-large 的 checkpoint 名称匹配论文，并不使完整系统自动成为论文系统；同名模型也不证明文件 revision 字节相同。

E34 的池大小实验仍成立，但“剩余差距不能解释，因为论文没给版本”不成立。视觉 checkpoint 版本现在是一个已知的待控制因素。现有差值不能单独归因给版本，仍需要在其它条件固定时比较才知道影响。

本轮没有把本地 v1.0 的缓存冒充 v0.1，也没有下载模型或重建付费输出。E27/E40/E29 的实际测量配置不变，数值应据各自运行记录引用。若下一阶段要声称与发表系统直接比较，应另建 v0.1 排名产物并复核池与处理协议；不得覆盖 v1.0 历史输入。
