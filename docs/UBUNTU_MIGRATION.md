# Windows → Ubuntu：恢复研究工作区（2026-09-25）

本页写给在 Ubuntu 上接手的 Codex。先读 `AGENTS.md`、`docs/HANDOFF.md`、
`REPRODUCE.md` 和 `docs/artifacts-git-policy.md`。不要把恢复操作误称为从零复现：
这里复制的是已经计算过的输入，完整 Linux 冷启动构建尚未实测。不要运行付费 API。

## 1. 包在哪里，装了什么

Windows 制包位置：`F:\MMDocRAG-ubuntu-migration-20260925\`，**在 Git 仓库外**。
制包前 F 盘可用 161,575,174,144 字节，完成后仍有约 146 GB。
源仓库提交为 `ea3dfaba874d09048132593667749c6e671144cb`；本页和跨平台修复属于后续代码提交，
Ubuntu 应 clone 包含该修复的分支。`manifest.json` 记录每个包成员的相对路径、字节数和 SHA-256；
`SHA256SUMS.txt` 记录传输文件的 SHA-256。归档写完后已逐项从归档读回并与源文件 SHA-256 比较。

| 传输文件 | 字节 | 成员 | SHA-256 | 作用 |
|---|---:|---:|---|---|
| `assets.zip` | 3,576,993,900 | 14,827 | `cb912a7a721eecee4a9cc8f5ef4b6add07e97e0a93aaf69aa6e0d361c1c490ae` | 14,826 张原图与 `data/doc_pdfs.zip` |
| `derived.zip` | 1,496,483,778 | 293 | `0e6f70fc2365827cef91b478cb12f12b9a0146652b87978092c0540580695154` | SQLite、向量、排名、路由缓存、未跟踪的逐题记录 |
| `private.7z` | 1,536,636 | 23 | `8a814f3f3e437065f8db1d781c7ae57aca07a29de8d0ee504a0fb30b602078dd` | **加密**的 `artifacts/api/` 原始流量和 E39 冻结候选输入 |
| `models.zip.part01` | 2,147,483,648 | — | `7377f308b5d7b02e3d37d912c1b545981f5456e84bf02b020ef598eb8dcdb9e8` | 模型包第 1 卷 |
| `models.zip.part02` | 2,147,483,648 | — | `4e47fd3140da2101d15c2e3e1c1245f2151aec14e1aa142b6f35393744e58462` | 第 2 卷 |
| `models.zip.part03` | 2,147,483,648 | — | `c77bb31a27bd1185754aedb8ddef492b3cd3a26a41e47f80895f278ac37cc51a` | 第 3 卷 |
| `models.zip.part04` | 2,147,483,648 | — | `dc69751c8e1b2da6b576cd0d82eef5e4534e07aea6ef3789c302841d892b4a77` | 第 4 卷 |
| `models.zip.part05` | 1,690,030,850 | — | `607ce3648a80886891e79fb9196232b3b7aa07e5c08c1bc341d3a11cf56a7740` | 第 5 卷 |

五卷按名称顺序合并后 `models.zip` 为 **10,279,965,442 字节**，
SHA-256 为 `00daf2f4fb2e03db5d98c0532c4de4ce953d68a590e5df253770d3c85b63d60a`，
内有 57 个文件。`models.zip` 原文件制包校验后已删除，只需传五卷。
传输 `manifest.json`、`SHA256SUMS.txt` 和四份 `*.files.json`；
`pack.py`、`pack.log` 是 Windows 制包工具与日志，不是恢复输入。

私密包使用 py7zr 的加密 7z 格式，文件名头也加密。口令**不在包里也不在 Git 里**，
只保存在 Windows 用户文档目录的 `MMDocRAG-ubuntu-migration-private-key-20260925.txt`。
通过独立的私密渠道把口令交给 Ubuntu 操作者；不要把口令文件和包一起上传到公开位置。
若暂时只跑缓存实验，私密包可先不解，但原始 API 证据与 E39 准备材料便不完整。

## 2. 输入盘点与迁移选择

| 路径 / 组 | 本机源大小 | Git | 可重得性 | 本次处理 |
|---|---:|---|---|---|
| `dataset/`（11 个 JSONL） | 187 MB | 已跟踪 | Git clone | 不重复打包 |
| `response/`（374 个已保存回答） | 824 MB | 已跟踪 | 新生成需付费 | Git clone 已包含；严禁批量删除 |
| `D:\Dataset\MMDocRAG\images\images\*.jpg` | 2.52 GB、14,826 张 | 无 | [官方 `images.zip`](https://huggingface.co/datasets/MMDocIR/MMDocRAG/tree/main) 可重新下载 | `assets.zip`；排除了无用的 `__MACOSX/` 副本 |
| `D:\Dataset\MMDocRAG\doc_pdfs.zip` | 1,051,966,358 字节、220 PDF | 无 | [官方 `doc_pdfs.zip`](https://huggingface.co/datasets/MMDocIR/MMDocRAG/tree/main) 可重新下载 | `assets.zip`；Ubuntu 再展开为 220 PDF |
| `canonical/*.sqlite` | 50,982,912 字节、2 文件 | 无 | 从 JSONL、PDF、OCR 重建 | `derived.zip` |
| `retrieval/` 本机派生产物 | 1,290,074,306 字节、30 文件；其中向量 671,519,879 字节、7 文件 | 无 | 长时间 CPU/GPU 重建 | `derived.zip`；含 quote/page DB、ColQwen 两种池的排名 |
| `router/` 本机派生产物 | 59,396,584 字节、36 文件 | 无 | 可计算；缓存加速复验 | `derived.zip` |
| `artifacts/runs/` 未跟踪的逐题 CSV、补丁等 | 95,970,058 字节、225 文件 | 主指标等轻量记录已跟踪 | 部分可复算 | `derived.zip`；不带 stdout/stderr 临时日志 |
| `models/` | 10,279,955,068 字节、57 文件 | 权重不跟踪；BGE 的 `fetch.json` 已跟踪 | BGE-large 有精确修订与逐文件哈希；ColQwen 本地字节仅由本包清单固定 | 模型五卷 |
| `artifacts/api/` | 2,604,500 字节、14 文件 | 不跟踪 | 付费原始请求/响应不可免费重得 | `private.7z` |
| `artifacts/e39/` | 15,661,128 字节、9 文件 | 不跟踪 | 可重新准备，但含完整文档文字和图片描述 | `private.7z` |

没有把 Windows `.venv*`、`artifacts/logs/`、`artifacts/test-runs/`、模型下载缓存、
`__MACOSX/`、PDF 已展开副本放入迁移包。它们不是恢复现有指标所必需。
`artifacts/derived/registry.json` 已在 Git 中；历史 `abs_path` 指向 Windows，
运行时代码现在用其中的仓库相对 `path` 定位，并保持原登记记录不被改写。
如果本地缓存哈希仍显示 `stale`，不要强制把旧值标为通过：先核对逐文件清单，再检查登记差异。

## 3. 传输、校验、解包

可用移动硬盘、局域网 `rsync` 或私有对象存储传输以上文件。不要把包推送到公开 GitHub。
Ubuntu 上建议至少预留 **50 GB**：包约 15.4 GB，拼接模型时再占 10.3 GB，
展开后的模型与数据约 15 GB，另需 Git clone、虚拟环境和临时空间。
若 Windows 有 WSL 和 SSH，可在 WSL 中断点续传（替换主机名与目录）：

```bash
rsync -avP --info=progress2 /mnt/f/MMDocRAG-ubuntu-migration-20260925/ \
  ubuntu@YOUR_HOST:~/MMDocRAG-ubuntu-migration-20260925/
```

双系统或移动硬盘则在 Ubuntu 挂载磁盘后将包目录复制到本机，随即运行下面的校验。
口令文件不属于上面的源目录。
先 clone 含本页修复的仓库，进入项目根目录，设定包目录：

```bash
git clone git@github.com:gouyuanshuo/MMDocRAG.git
cd MMDocRAG
MIGRATION=/path/to/MMDocRAG-ubuntu-migration-20260925
(cd "$MIGRATION" && sha256sum -c SHA256SUMS.txt)
cat "$MIGRATION"/models.zip.part0{1,2,3,4,5} > "$MIGRATION/models.zip"
echo '00daf2f4fb2e03db5d98c0532c4de4ce953d68a590e5df253770d3c85b63d60a  models.zip' \
  | (cd "$MIGRATION" && sha256sum -c -)
unzip -n "$MIGRATION/assets.zip" -d .
unzip -n "$MIGRATION/derived.zip" -d .
unzip -n "$MIGRATION/models.zip" -d .
mkdir -p data/doc_pdfs
unzip -n data/doc_pdfs.zip -d data/doc_pdfs
```

目录必须是 `images/images/<name>.jpg`、`data/doc_pdfs.zip`、
`data/doc_pdfs/doc_pdfs/<name>.pdf`，不是少一层或多一层。
相对路径按包内原样落到仓库根目录，例如 `canonical/mmdocrag.sqlite`、
`retrieval/embeddings/...npz`、`router/cache/...pkl`、`models/colqwen2-base/...`。
`data/` 和 `images/images/` 已忽略，不能 `git add -f`。

解私密包时，先在 Ubuntu 的 Python 环境中安装 `py7zr==1.1.3`，从独立渠道取得口令，
由交互式输入避免把口令写到命令历史：

```bash
python -m pip install py7zr==1.1.3
MIGRATION=/path/to/MMDocRAG-ubuntu-migration-20260925 python - <<'PY'
import getpass, os, py7zr
archive = os.path.join(os.environ['MIGRATION'], 'private.7z')
with py7zr.SevenZipFile(archive, 'r', password=getpass.getpass('private package password: ')) as z:
    z.extractall(path='.')
PY
```

上面只解包；不会启动模型或请求 API。若没有私密口令，不要猜测 E39 已可继续生成。
恢复后按 `manifest.json` 的逐文件哈希核对，而不只看文件数：

```bash
MIGRATION=/path/to/MMDocRAG-ubuntu-migration-20260925 python - <<'PY'
import hashlib, json, os
from pathlib import Path
m = json.loads((Path(os.environ['MIGRATION'])/'manifest.json').read_text())
for group in ('assets', 'derived', 'models', 'private'):
    missing = changed = 0
    for row in m['files'][group]:
        p = Path(row['path'])
        if not p.is_file(): missing += 1; continue
        h = hashlib.sha256()
        with p.open('rb') as f:
            for block in iter(lambda: f.read(4 << 20), b''): h.update(block)
        changed += p.stat().st_size != row['bytes'] or h.hexdigest() != row['sha256']
    print(group, 'files', len(m['files'][group]), 'missing', missing, 'changed', changed)
PY
```

**注意：**下一节对 ColQwen 的 `adapter_config.json` 作本机路径修正后，该单个文件的哈希
会有意变化。先做上述完整核对，再修正它；修正后保存本地新哈希，归档中的原字节仍可追溯。
`private` 未解包时，核对会明确显示 23 个缺失，而不是把它们记作无关。

再检查目录数量和 SQLite 文件完整性：

```bash
find images/images -maxdepth 1 -name '*.jpg' -type f | wc -l  # 14826
find data/doc_pdfs/doc_pdfs -maxdepth 1 -name '*.pdf' -type f | wc -l  # 220
python - <<'PY'
import sqlite3
from pathlib import Path
for name in ('canonical/mmdocrag.sqlite', 'retrieval/quotes.sqlite',
             'retrieval/colqwen_scores.sqlite', 'retrieval/colqwen_scores_fullpool.sqlite',
             'router/outcomes.sqlite'):
    p = Path(name).resolve()
    with sqlite3.connect(p.as_uri() + '?mode=ro', uri=True) as db:
        print(name, db.execute('PRAGMA quick_check').fetchone()[0])
PY
git status --short  # 不应列出权重、图片、PDF、向量或 API 原始文件
```

## 4. 模型与 Ubuntu Python 环境

项目**不依赖 Ollama**。历史笔记里 Ollama 仅是 Windows 显存占用的背景。

| 用途 | 实际输入/模型 | 恢复要求 |
|---|---|---|
| 已有回答离线复算 | Git 中的 `response/`、`dataset/` 加本次 SQLite/向量/排名 | 不加载生成模型；不需 API key |
| BGE 编码新文本 | `BAAI/bge-small-en-v1.5` 或 `models/bge-large-en-v1.5` | 旧向量已迁；新编码才需权重。BGE-large 本包包含固定 revision `d4aa6901d3a41ba39fb536a557fa166f842b0e09`，可用 `python -m retrieval.fetch_model BAAI/bge-large-en-v1.5 --check` 验证；BGE-small 权重未在本机 `models/`，旧使用版本未精确钉住，重新下载时不能宣称字节级复现旧编码 |
| 重新建立 ColQwen 视觉排名 | `models/colqwen2-v1.0` adapter + `models/colqwen2-base`，单独 `.venv-colpali`、NVIDIA GPU | 权重已迁；已有排名的离线评价无需 GPU；本包逐文件哈希固定本机字节，旧上游 revision 未完整记录 |
| 新生成回答（含 E39） | Gemini API / provider key、实际模型与计费预算 | **未调用、未授权自动调用**；E39 仅 prepared，未 generated。旧 `response/` 可直接复算指标 |

主环境以 Ubuntu 的 Python 3.12 或 3.13 建立；Windows 验证环境是 Python 3.13.7。
先确认 `nvidia-smi`、驱动与 GPU。下面为与 Windows 记录接近的 CUDA 12.4 安装命令，
PyTorch 2.6.0 的 [官方历史安装页](https://docs.pytorch.org/get-started/previous-versions/) 列出 Linux CUDA 12.4 wheel。
**这些安装命令尚未在 Ubuntu 实测**，只能在确认驱动兼容后执行：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu124
python -c 'import torch; print(torch.__version__, torch.cuda.is_available())'
```

没有 NVIDIA GPU 时，先做缓存复算和 CPU 测试；不要启动 ColQwen 构建。
如需纯 CPU 安装，必须另选 PyTorch 官方 CPU wheel 并去掉 `requirements.txt` 中
`torch==2.6.0+cu124` 那一行的冲突，记录最终版本；这不是 Windows 实验的同一环境。
若需要重建视觉排名，再建立独立环境（Windows 现有环境读到 `colpali_engine==0.3.18`、
`transformers==5.15.1`、`peft==0.20.0`、`torch==2.6.0+cu124`）：

```bash
python3.12 -m venv .venv-colpali
.venv-colpali/bin/python -m pip install --upgrade pip
.venv-colpali/bin/python -m pip install torch==2.6.0+cu124 --index-url https://download.pytorch.org/whl/cu124
.venv-colpali/bin/python -m pip install colpali_engine==0.3.18 transformers==5.15.1 peft==0.20.0
```

迁来的 `models/colqwen2-v1.0/adapter_config.json` 仍指向旧的
`D:\Playground\MMDocRAG\models\colqwen2-base`。在完成包/成员 SHA 校验后，
运行以下**只修改该本地模型配置**的步骤；不修改权重：

```bash
python - <<'PY'
import json
from pathlib import Path
p = Path('models/colqwen2-v1.0/adapter_config.json')
base = Path('models/colqwen2-base').resolve()
assert p.is_file() and base.is_dir()
cfg = json.loads(p.read_text(encoding='utf-8'))
print('previous base:', cfg['base_model_name_or_path'])
cfg['base_model_name_or_path'] = str(base)
p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('local base:', cfg['base_model_name_or_path'])
PY
```

如不重建 ColQwen，暂不需要第二个环境或上述模型配置修正。不要自动重新下载模型。

## 5. 安全的运行顺序与尚未验证的边界

先执行读操作和测试，按需执行缓存复算。**不要运行 `--allow-api` 或 `--live`**：

```bash
python experiments.py list
python reproduce.py --dry-run
python experiments.py run-suite replay --dry-run --offline
python -m tests.test_ubuntu_migration
python -m tests.test_runner --scratch-root artifacts/test-runs
python -m tests.test_source_bundle --scratch-root artifacts/test-runs
python -m tests.test_statistics
python -m tests.test_phase3
python -m tests.test_demo
```

`--dry-run` 的依赖计划应把已恢复的 SQLite/向量/排名标为 `reuse`；若有 `missing` 或
`stale`，先读原因、查 `manifest.json`，不要盲目 `--force-rebuild`。
确认后才运行 `python experiments.py run-suite replay --offline`；只做缓存指标复算，
不应发 API 请求。记录新生成的 `run_id`，验证时**总是**传
`python experiments.py verify E27 --run <该次run_id>`。
若之后启动 `full-local`，先运行同套件 `--dry-run`，准备原 PDF、图片、模型权重及 GPU；
长任务日志写入 `artifacts/logs/` 并使用内建检查点。

Windows 上已验证：本次制包的成员回读哈希、私密包解密回读、模型五卷拼接 SHA。
2026-09-25 在当前 Windows 工作树运行的测试为：

| 命令 | 实际结果 |
|---|---:|
| `python -m unittest tests.test_ubuntu_migration` | 3/3 通过 |
| `python -m tests.test_runner --scratch-root artifacts/test-runs` | 67/67 通过 |
| `python -m tests.test_source_bundle --scratch-root artifacts/test-runs` | 23/23 通过 |
| `python -m tests.test_statistics` | 30/30 通过 |
| `python -m tests.test_phase3` | 35/35 通过 |
| `python -m tests.test_demo` | 63/63 通过 |
| `python reproduce.py --dry-run` | 退出码 0，无命令执行 |
| `python experiments.py run-suite full-local --dry-run --offline --include-expensive` | 退出码 0；列出的依赖产物均为 `present/reuse`，没有构建 |

本机仓库说明里的 25/48 是旧测试数量；以上为此次运行的实际数量。
Ubuntu 上**尚未验证**：依赖安装、ColQwen 模型加载/显存、完整冷启动、历史 run 的
源码重建与所有缓存复算。旧 `run.json` / manifest 里的 Windows 绝对路径是历史证据，
不会批量改写；新运行应自行记录 Ubuntu 环境。Windows 修复了数据源默认目录、DAG 和
实验注册中的 ColPali 解释器路径，以及登记表的跨机定位；这不等于 Linux 全链路通过。
