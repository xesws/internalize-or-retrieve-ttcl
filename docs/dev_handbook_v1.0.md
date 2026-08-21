# 开发手册 v1.1 — internalize-or-retrieve-ttcl

读者: 在本 repo 工作的 coding agent。人类负责人: JQ。
本仓库: github.com/xesws/internalize-or-retrieve-ttcl.git · 本地: /Users/tangyiq/dev/internalize-or-retrieve-ttcl
文档版本规则: docs/ 下的 campaign 文档从 1.0 起版, 依次 1.1、1.2 …; 阶段报告同规则; 禁止无版本号的散落文档。
变更记录: v1.1 (2026-08-21, JQ 裁决) — 砍掉 S3/AWS, Mac 即正本 (每个 run 结束立刻 rsync, sync_results.sh 只做 rsync); pod 仅持有 HF_TOKEN, DeepSeek/GLM 全部付费调用 (含 judge 打分) 移至 Mac 侧对回传 items.jsonl 后处理, pod 永不持有付费 key; 凭证轮换条款收窄为仅确实上过 pod 的凭证; P5 最终冻结记分卡 (summary/scorecard 级小文件) 允许入 git; 模型池定为 GLM 5.3 + DeepSeek V4 Pro/Flash, Kimi 弃用, §1 三家族约束放宽为两家族、异族规则按 proposal §5.5 硬规则执行; 文件名保持 v1.0 以维持 AGENTS.md 引用。

## 0. 事实来源优先级与任务定义

信息冲突时的优先级: (1) docs/ttcl_proposal_report.md (proposal 定稿, 科学事实来源) > (2) 本手册 (工程事实来源) > (3) 参考实现 AIEHackathon (仅供参考, hackathon 级代码, 不是规范)。

任务分两级。第一级是**验证 (Phase 2 mini-matrix)**: 用最小成本在 RunPod 真 GPU 上跑通一个 4 臂 20 条记忆的小矩阵, 判定核心主张是否成立 (判据见 §5 G2)。G2 通过 → 全情投入第二级: 完整五臂主矩阵 + 可选 utility router, 供 TTCL 投稿 (ddl 2026-08-29 AoE)。G2 不通过 → 停止并报告, 不得静默调参到通过。

## 1. 运行环境与分工

- **Mac (本地)**: agent 的工作现场。代码编写、CPU 单测、工作负载生成 (走 hosted-LLM API, 不需要 GPU)、经 SSH 调度 RunPod、收结果、出表都在本地。全部付费 API 调用 (DeepSeek/GLM, 含 judge 打分) 一律在 Mac 侧执行, 对 rsync 回来的 items.jsonl 做后处理。
- **RunPod (远端 GPU)**: A40/L40 级单卡 pod。只跑已 push 的代码 (pod 上 fresh clone / git pull, 严禁在 pod 上手改代码后不回推)。pod 存储是 ephemeral 的, 不用 network volume, 也不用 S3; 每个 run 结束后立刻 rsync 回 Mac, **Mac 即正本**。pod 上只持有 HF_TOKEN, 永不持有付费 API key。
- **长任务纪律**: pod 上一律 tmux 运行 (`tmux new -s run_<phase>`), agent 通过 SSH 轮询日志, 不在前台阻塞自己的会话。
- **秘密**: HF_TOKEN (Llama-3.1-8B-Instruct 是 gated 模型) 是唯一允许上 pod 的凭证; DeepSeek/GLM 等付费 API key 只存 Mac 侧 `.env` (gitignore), 永不上 pod、永不入 git。pod 关闭后仅轮换确实上过 pod 的凭证 (当前仅 HF_TOKEN)。
- **模型角色三分离** (写进 run manifest 的精确 model string): `GEN_MODEL` 生成工作负载; `SYS_MODEL` 系统内部 LLM (抽取/分型/planner/组稿); `JUDGE_MODEL` 评自然融入度。模型池 (JQ 2026-08-21 裁决): GLM 5.3 (Z.AI) + DeepSeek V4 Pro / V4 Flash, Kimi 弃用; 池内仅两家族, 异族约束按 proposal §5.5 硬规则执行: 生成器与 judge 异族、judge 与系统 LLM 异族。当前分配: GEN=SYS=`glm-5.3`, JUDGE=`deepseek-v4-pro`, `deepseek-v4-flash` 仅 dev 辅助。每次付费 API 调用记录 token 用量并汇总进 run manifest; DeepSeek 余额消耗过半在阶段报告报警; P3 启动前由 JQ 决定是否充值。本地被编辑的 backbone 固定 Llama-3.1-8B-Instruct。

## 2. References (完整给 agent 的信息底座)

### 2.1 内部参考 (最重要)

| 资源 | 位置 | 用途 |
|---|---|---|
| Proposal report v1.0 | docs/ttcl_proposal_report.md (由 JQ 放入 repo) | 唯一科学规范: claim、C1–C4、五臂、判据、指标、污染纪律。开工前通读。 |
| 参考实现 Engram | github.com/xesws/AIEHackathon (branches: main, feature/async-shadow-serving, feature/free-scenario-planner) | 上一代原型。可移植与需重写清单见 §3.2。 |
| 本手册 | docs/dev_handbook_v1.0.md | 工程规范。 |

### 2.2 论文参考 (按用途分组; 标注 arXiv ID 的为高置信, 未标 ID 的先按标题在 arXiv 检索核实后再引用/抓取 — 所有 ID 在写入代码或论文前都要按标题复核一遍)

**机制核心 (实现要读)**
- HoReN — arXiv 2605.08143。编辑后端。codebook key/value 语义、gate 阈值、Llama3.1-8B hparams 全从它来; 我们通过 AIEHackathon 的 third_party/horen 使用它。

**editing 线 (related work + probe 格式参考)**
- ROME — arXiv 2202.05262; MEMIT — arXiv 2210.07229; GRACE ("Aging with GRACE") — arXiv 2211.11031。定位段引用, 不实现。
- "UnKE: Unstructured Knowledge Editing for Large Language Models" (按标题核实)。非结构化 payload 与 probe 风格的参照。
- "AnyEdit" / EditEverything 数据集论文 (按标题核实)。同上。
- LEME "Long-form Evaluation of Model Editing" — arXiv 2402.09394。长文评测指标的先例, 我们的 free-form 指标要与它划清: 它围绕编辑对象直接问, 我们测开放任务中的主动调用。

**in-context 编辑线 (planner 的差异化对象)**
- IKE "Can We Edit Factual Knowledge by In-Context Learning?" — arXiv 2305.12740。
- MQuAKE / MeLLo — arXiv 2305.14795。"分解-查编辑记忆-作答"的最近邻; 我们的差异: 记忆是参数化的、目标是开放写作、有归因。
- "DeepEdit" (按标题核实)。

**memory-agent 线 (related work)**
- MemGPT — arXiv 2310.08560; MemoryBank — arXiv 2305.10250; Mem0、Letta (按标题/官方文档核实)。全外存、无内化, 是 CFP 批评对象。

**学习型记忆管理 (最近邻, 必须精确差异化)**
- Memory-R1 — arXiv 2508.19828 (ACL 2026)。RL 训练的 Memory Manager 在**单一外部** memory bank 上做 ADD/UPDATE/DELETE/NOOP; 我们决策的是**跨异构存储的放置且一个目的地是权重**。它用 LOCOMO 评测 — 我们的工作负载 session 结构也参照 LOCOMO, 便于读者对齐。

**read-side 路由 (正交性声明)**
- Self-RAG — arXiv 2310.11511; Adaptive-RAG (按标题核实)。它们决定读取时是否检索 (per-query), 我们决定写入时放哪 (per-memory)。

**工作负载播种源 (数据构建要用)**
- PersonaChat "Personalizing Dialogue Agents" — arXiv 1801.07243 → belief 素材。
- MSC "Beyond Goldfish Memory" — arXiv 2107.07567; LOCOMO — arXiv 2402.17753 → 多 session 结构模板。使用前核实 license 并在 docs/ 记录。

## 3. 仓库脚手架与移植清单

### 3.1 目标目录结构

```
docs/                    # proposal report, 本手册, 阶段报告 (1.x 版号)
prompts/                 # 全部 prompt 逐字落盘, 文件名带版本, 冻结后不改
configs/                 # 冻结的 YAML (含 config 哈希); HoReN hparams 原样锁定
src/workload/            # 生成器: schema、persona 播种、probe 套件、压力注入、dev/test 切分、污染 lint
src/stores/              # rag_store (含预算/eviction/distractor), horen_adapter (编辑后端封装)
src/router/              # v0 LLM 分型路由; v1 utility router (Phase 4)
src/readpath/            # 任务形态判定、planner、gate、参数化引出、组稿、attribution
src/arms/                # S1–S6 runner, 统一接口 run_arm(arm, workload, config) -> results/<run_id>/
src/evalx/               # 指标: recall/locality/freshness/cost/attribution, judge, scorecard, 漂移
scripts/                 # pod_setup.sh, dispatch.sh, sync_results.sh
spikes/                  # GPU 冒烟与一次性验证脚本 (与单测分离)
tests/                   # CPU 单测, 不碰 GPU
data/workloads/          # 冻结的工作负载 JSON — 允许入 git (小文本)
results/                 # gitignore; run_id 目录; run 结束立刻 rsync 回 Mac (正本)
third_party/horen/       # 从 AIEHackathon 移植并打修复补丁 (§4.1)
```

Git 纪律: 代码与小型冻结数据入 git; checkpoint、adapter、日志、生成文本一律不入 git; P5 的最终冻结记分卡 (summary/scorecard 级小文件) 允许入 git, 其原始生成与日志仍不入。conventional commits, 阶段边界必 push, 禁 force-push, 未经指示不用 git worktree。

### 3.2 从 AIEHackathon 移植 vs 重写

**直接移植 (小改)**: third_party/horen (连同 llama3.1-8b hparams yaml, 但必须打 §4.1 补丁); keying.py 的 query-span key 与 gate; serving/model_host.py 的常驻模型 + edit-module 开关; shadow_editing/async_editor 的影子训练与热切换 (Phase 3 才需要, 优先级低)。
**升级重写**: spike_v27 的三处 — lexical planner → LLM planner (词表版留作消融); notes 取存储原文 → rag_off 下对被编辑权重逐探针生成答案 (参数化引出, 主变体); 3 个手写场景 → src/workload 自动生成。
**全新**: 工作负载生成器与 probe 套件、压力机制 (预算/eviction/distractor/top-k)、五臂 runner、记分卡、utility router。
**不要带过来**: 前端、demo fixtures、Engram 品牌素材 (投稿产物需匿名, 代号 [SYSTEM])。

## 4. 工程红线 (从上一战役移植的教训, 违反任一条 = 结果作废)

### 4.1 Llama pad/eos 掩码补丁 (最高优先级)

上游 HoReN (以及 AIEHackathon 内的 vendored 副本) 存在一个已确诊缺陷: Llama-3.1 tokenizer 无独立 pad 符号, 代码将 pad 别名为 eos, 随后的损失掩码把训练目标末尾**真正的终止符也一并掩掉**, 同时 prompt 长度计数偏差 1, 导致所有 Llama 编辑臂在没有停止信号的条件下训练 — 表现为生成失控撞解码上限、长度中位数暴涨。移植 third_party/horen 后的第一件事是打补丁: 在掩码工具处改用 attention_mask 识别 padding, 保证答案末端 eos 受监督。验收三查 (在 10 条编辑冒烟上): (a) gold 边界处 p(eos) 从 ~0 恢复到与未编辑基线同量级; (b) 512 token 解码上限命中率 ≤ 10% 且生成长度中位数 < 150; (c) 训练步数分布与补丁前基本不变。三查任一不过, 停下报告。

### 4.2 其余红线

- 解码预算 max_new_tokens=512, 并对每次生成记录 cap-hit 与 length_ratio; 任何臂 cap-hit 异常升高都要在阶段报告里解释。
- seed=42 全局固定; 不开启 deterministic algorithms; run manifest 记录 GPU 型号、commit sha、config 哈希、三个 model string、付费 API token 用量汇总; 指标不报四位小数, 主表附一次同配置重跑的漂移界。
- gate 阈值 (hopfield_key_match_threshold) 是最危险旋钮: Llama 家族从 repo 默认 0.85 起, 在 dev 上扫 {0.75, 0.80, 0.85, 0.90} 定一次并冻结; 若日后加 Qwen backbone, 必须按家族重推, 不得沿用。
- 污染纪律: probe 文本严禁出现目标词 (沿用 spike_v27 的 target-free 检查并扩展到全 probe 套件, lint 进 CI); 四组 prompt (生成器/router/planner/组稿) 在测试集生成前冻结并记录版本哈希; HoReN 编辑超参不得调; 系统参数只在 dev 上调。
- 评测幂等: 每臂逐条写 items.jsonl 日志 (journal), 重跑自动跳过已完成条目; 任何 run 中断后可续跑而不重算。
- 除非 JQ 明确要求, 不引入新的外部服务依赖; 网络失败重试三次后报告, 不静默降级。

## 5. 阶段计划 (phases · 并行度 · 验收 · 停止条件)

| Phase | 内容 | 跑在哪 | 验收 (Gate) | 停止条件 |
|---|---|---|---|---|
| P0 环境与后端冒烟 | pod_setup.sh; 装依赖; 下载 backbone; 移植 horen + §4.1 补丁; 5 条编辑 + gate 往返 | RunPod | **G0**: 5/5 编辑写入成功、gate 命中自身 key、§4.1 三查通过 | 连续两次环境/加载失败 → 停, 报环境细节 |
| P1 工作负载与 probe 套件 | schema、生成器、压力注入、dev/test 切分 (persona 不相交)、冻结 v1 | Mac (纯 API/CPU) | **G1**: schema 校验 100%; target-free lint 100%; probe 计数达标; 人抽查 10 条通过 (JQ 抽) | target 泄漏率修复一轮后仍 >2% → 停 |
| P2 验证小矩阵 (**go/no-go**) | N=20 条、4 臂 (S1/S2/S4/S5)、压力开启、单 pod | RunPod | **G2** (预注册): ① S2 在 unrelated/near-miss 上出现可测退化且 S1 不出现; ② 压力下 S1 在被 evict 条目上召回坍塌且 S2 不坍塌; ③ 综合分 S5 ≥ max(S1,S2) 且 S5 达到 S4 的 80% 以上 | 允许**一轮**压力参数再标定 (披露记录); 再标定后 ①② 仍不成立 → **停, 这是 no-go 信号**, 不得继续调 |
| P3 主矩阵 | N=80 条 / 400–500 probe、五臂 S1–S5 | RunPod (臂可分 pod 并行) | **G3**: 全臂 journal 完整; 记分卡与失败矩阵产出; 漂移界已测 | 单臂重跑两次仍崩 → 报告后按其余臂出表 |
| P4 utility router (可选) | dev 30–40 条双路对照 → utility 标签 → 小模型 → held-out 上作 S6 | RunPod | **G4**: S6 ≥ S5 或给出否定结果分析 (两者都可写) | 时间触及 8/27 → 砍 P4 |
| P5 出表与冻结 | 主表、失败矩阵、pressure-off 消融行、图 | Mac | **G5**: 数字冻结, 交 JQ 写作 | — |

并行度: P1 与 P0 并行 (不同机器); P3 各臂独立可分 pod; P4 依赖 P3 的 dev 侧产物。日程挂靠 proposal report §6 (8/22–23 P0+P1, 8/24–25 P2+P3, 8/26 P4, 8/27–28 写作)。**G2 是 JQ 定义的"验证成功→全情投入"闸门: 通过前不得启动 P3 的大规模开销。**

## 6. RunPod 操作手册 (agent 执行规范)

### 6.0 专用 pod (已配置, 直接使用)

本项目的专用 RunPod session 已由 JQ 配置完毕, Mac 的 `~/.ssh/config` 中已有如下条目:

```
Host internalize-or-retrieve
    HostName 69.30.85.213
    Port 22113
    User root
    IdentityFile ~/.ssh/id_ed25519
    ControlMaster auto
    ControlPath ~/.ssh/cm-%r@%h:%p
    ControlPersist 10m
    ServerAliveInterval 30
```

因此本手册中所有对 pod 的操作一律写作 `ssh internalize-or-retrieve '<command>'`, 不要再拼 IP/端口。ControlMaster 复用连接, 高频轮询开销可忽略。开工第一条命令是连通与硬件确认 (GPU 型号写入 run manifest, §4.2 要求):

```
ssh internalize-or-retrieve 'nvidia-smi --query-gpu=name,memory.total --format=csv,noheader && df -h /workspace | tail -1'
```

故障排查顺序 (有前科的坑): `ssh internalize-or-retrieve` 被拒时, 先查 RunPod 控制台当前的 TCP 映射是否还是 69.30.85.213:22113 — pod 重启后 IP/端口会变, 变了就更新 `~/.ssh/config` 并在阶段报告里记一笔; 映射没变才排查 pod 内 sshd/key 层。不要一上来就换密钥。注意: 本节含活动 pod 的连接坐标, repo 转公开前必须把本节脱敏。

### 6.1 操作步骤

1. P0–P2 与 P3 主干直接使用 §6.0 的专用 pod, 不另开; 仅当 P3 需要多臂并行时按原流程增开 pod (A40/L40, 单卡, ≥48GB 磁盘), 新 pod 的连接信息写进本地 `.env.local` (gitignore) 并沿用同一套操作规范。
2. pod 内: `git clone https://github.com/xesws/internalize-or-retrieve-ttcl.git && cd internalize-or-retrieve-ttcl && bash scripts/pod_setup.sh` — 脚本内容: pip 依赖 (torch 用镜像自带)、`huggingface-cli login` (env token)、下载 Llama-3.1-8B-Instruct、跑 `pytest -q tests` 与 `python spikes/spike_gpu_smoke.py`。
3. 调度: 一律 `tmux new -s <run_id>` 内启动; agent 从 Mac 轮询 `ssh internalize-or-retrieve 'tail -n 50 ~/internalize-or-retrieve-ttcl/results/<run_id>/logs/run.log'`; 完成后立刻 `bash scripts/sync_results.sh <run_id>` — 该脚本只做 rsync 回 Mac, Mac 即正本; judge 等付费 API 后处理在 Mac 侧对回传的 items.jsonl 进行, pod 永不发起付费调用。
4. pod 生命周期: 专用 pod 贯穿 P0–P3 主干, 不因换 Phase 关闭, 但每个正式 run 前跑一次 `git pull` + 干净性检查 (`git status --porcelain` 为空); 增开的并行 pod 一臂一 pod, 结果确认离机后才允许关; pod 关闭后仅轮换确实上过 pod 的凭证 (本项目当前仅 HF_TOKEN)。
5. 严禁: 在 pod 上产生未回推的代码改动; 在 pod 本地存放唯一副本的结果; 在工作区不干净 (未 pull 到最新 commit 或有本地改动) 的状态下启动正式 run (冒烟可以)。

## 7. 汇报制度

每个 Gate 产出一份 docs/stage_report_<phase>_v1.x.md: 做了什么、验收逐条勾对、异常与修复、下一步阻塞项、待 JQ 决策清单 (集中一处列全, 不散落)。G2 报告额外包含: 三条判据的原始数字、压力参数最终值与再标定记录 (若发生)、go/no-go 建议。所有报告用完整段落陈述, 结论先行。
