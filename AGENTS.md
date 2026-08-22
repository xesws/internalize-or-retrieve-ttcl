# AGENTS.md — internalize-or-retrieve-ttcl

本文件是所有 coding agent 的默认上下文。保持简短; 细则全部在 docs/ 里, 冲突时以下述优先级为准。

## 0. 项目与目标

为 NeurIPS 2026 TTCL Workshop (投稿 ddl 2026-08-29 AoE) 构建并验证 "Internalize or Retrieve" 系统: 在线决定每条记忆进权重 (HoReN 编辑)、进 RAG、还是丢弃, 并让内化知识在开放任务中可用、可归因。当前工作按 Phase 推进, 阶段定义与验收门在 dev handbook §5。

## 1. 必读与事实优先级

开工前通读两份文档, 之后按需回查:

1. `docs/ttcl_proposal_report.md` — 科学规范 (claim、对照臂、判据、指标、污染纪律)。最高优先级。
2. `docs/dev_handbook_v1.0.md` — 工程规范 (环境、references、脚手架、红线、Phase 计划、RunPod 操作)。次优先级。
3. 本文件 — 日常行为规范。与上两者冲突时服从上两者。

规范未覆盖、或涉及花钱/砍范围/改判据的决定: 不要自行猜测, 写进阶段报告的"待 JQ 决策清单"并停在安全点。

## 2. 环境速览

- 本地 = JQ 的 Mac, 仓库路径 `/Users/tangyiq/dev/internalize-or-retrieve-ttcl`。CPU 单测、工作负载生成 (hosted-LLM API)、出表都在本地。
- GPU = 专用 RunPod pod, 统一 `ssh internalize-or-retrieve` 访问 (连接细节与故障排查: handbook §6.0, 不要在本文件或其他文件里复制 IP/端口)。
- pod 长任务一律 tmux; 结果先离机 (S3 正本 + rsync 副本) 再谈其他。
- 一切密钥走环境变量, 永不入 git。

## 3. 硬红线 (违反 = 结果作废; 细则见 handbook §4)

- 移植 HoReN 后第一件事打 Llama pad/eos 掩码补丁并过三查 (§4.1), 否则所有 Llama 编辑臂无效。
- seed=42; run manifest 记 GPU 型号 / commit sha / config 哈希 / 三个 model string。
- max_new_tokens=512, 逐生成记录 cap-hit 与 length_ratio。
- probe 文本严禁含目标词 (target-free lint 必须过)。
- 四组 prompt 与系统参数只在 dev 上调, 测试集生成前冻结; HoReN 编辑超参一律不动。
- G2 是 go/no-go 闸门: 通过前禁止启动 P3 大规模开销; 触发停止条件就停下报告, 严禁静默调参到通过。

## 4. Git 规范

- Conventional commits, 小步提交; Phase 边界与任何 pod 正式 run 前必须 push。
- 禁 force-push; 未经 JQ 明确指示不用 git worktree。
- git 只放代码与小型冻结数据 (`data/workloads/*.json` 允许); checkpoint、adapter、日志、生成文本、`results/` 一律不入 git。
- pod 上禁止产生未回推的代码改动; 正式 run 前工作区必须干净 (`git status --porcelain` 为空且在最新 commit)。

## 5. 文档与汇报规范

- campaign 文档全部放 `docs/`, 文件名带版本, 从 1.0 起版, 更新依次 1.1、1.2…; 禁止无版本号的散落文档。
- 每个 Gate 交 `docs/stage_report_<phase>_v1.x.md`: 完整段落陈述、结论先行、验收逐条勾对、异常与修复、"待 JQ 决策清单"集中一处列全。
- 每次向 JQ 汇报时必须一并输出报告的完整路径 (如 `docs/stage_report_P3_v1.0.md`), 不让 JQ 找文件。
- G2 报告额外附三条判据原始数字、压力参数终值与再标定记录 (若发生)、go/no-go 建议。

## 6. 代码与测试规范

- 代码、注释、commit message 用英文; 给 JQ 的阶段报告用中文完整段落。
- 改动相关的 `pytest -q tests` 在每次 push 前必须绿; GPU 验证脚本放 `spikes/`, 与单测严格分离, CI 不跑。
- 评测代码必须幂等可续跑: 逐条 items.jsonl journal, 重跑跳过已完成条目。
- 不引入规范之外的新外部服务依赖; 网络失败重试三次后报告, 不静默降级。

## 7. 匿名纪律

投稿产物 (论文、匿名 repo、补充材料) 中系统用中性代号, 不出现 Engram、xesws、GitHub 句柄或真实 pod 坐标; 本仓库转公开前按 handbook §6.0 的标记脱敏。