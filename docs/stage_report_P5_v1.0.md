# Stage Report P5 v1.0 — 出表与冻结 (交写作)

日期 2026-08-22 · 汇报人: coding agent · 状态: **G5 达成: 数字冻结, 表格交付, 停止等 JQ 写作**

## 结论

P5 完成。全部交付物: `docs/tables_p5_v1.0.md` (七表 + 附录) 与 `data/p5/frozen_scorecard_v1.json` (summary 级冻结记分卡, 按 handbook v1.1 入 git)。pressure-off 消融作为 P5 既定项跑完 (S1/S5 两臂 test 全量, 预算/驱逐关闭、distractor 移除、其余冻结配置不动), 结果与"内化在预算压力下产生收益"的条件句预测一致: **无压力下 S1 recall 0.631 反超 S5 0.568** (内化的 recall 优势消失), S5 的残余优势 (+0.084 composite) 全部来自 freshness 0.724 vs 0.408 (lifecycle 轴)——与 S6 否定结果的归因互相印证: 放置的价值信号住在生命周期轴上, 不在逐条 QA 轴上。

## 交付清单逐条勾对 (JQ 2026-08-22 固定清单)

| 交付项 | 状态 | 位置 |
|---|---|---|
| 七臂主表含 bootstrap CI 与分用户附注 | ✅ | 表 1 (+分用户小表) |
| type×store 失败矩阵 (含 both 列) | ✅ | 表 2 |
| supersede 归因表 (12/7/2/2) | ✅ | 表 3 |
| 错路由混淆矩阵 (单方向口径) | ✅ | 表 4 |
| 顺序一致性确认行 (75 题池脚注 + 两口径一句话调和) | ✅ | 表 1 脚注 + 表 5 |
| gate 敏感性表 (附录校准存档) | ✅ | 附录 A |
| 漂移界 (S5 run1/run2, \|Δ\|=0.025) | ✅ | 表 6 |
| pressure-off 消融行 (S1/S5, P5 既定项) | ✅ | 表 6 |
| S7 亏损分解段 (P4 裁决 2) | ✅ | 表 7 + P4 报告 v1.1 增补 |
| transient 定稿句 / 四条写作口径 | ✅ | docs/p5_checklist_v1.1.md (口径 3, 5–8) |
| summary 级冻结记分卡入 git | ✅ | data/p5/frozen_scorecard_v1.json |

## pressure-off 消融 (本报告新增数字)

| 臂 | composite | recall | freshness | locality | fact×rag |
|---|---|---|---|---|---|
| S1 off (预算/驱逐关, 无 distractor) | 0.624 | **0.631** | 0.408 | 0.833 | 0.684 |
| S5 off (同) | 0.708 | 0.568 | **0.724** | 0.830 | 0.554 |

对照压力行 (S1 0.510 / S5 0.612): S1 无压力下 recall 从 0.495 恢复到 0.631, fact×rag 从 0.527 到 0.684——检索压力是 all-RAG recall 亏损的直接来源; S5 两态都领先 (0.612/0.708), 其优势成分在压力开关两侧都是 freshness。诚实呈现: 内化的收益是条件性的 (预算压力下), 而 router 的 lifecycle 收益是无条件的——两个主张分开写, 不合并。

## 冻结与可复现性

冻结哈希链: scoring_v1 / pressure_v2.1 / gate 0.90 / planner 302afb4fdd7ec495 / judge bec5d95094013fd5 / router (S5, 188/210) / workload test_v1.1 / S6 utility_router_v1 / 扩容池 v1 (freeze v1.1) — 全部记入 data/p3/freeze_v1.1.json 与 frozen_scorecard meta。seed 42; backbone meta-llama/Llama-3.1-8B-Instruct; run manifests 在各 results/<run_id>/manifest.json (Mac 正本)。

## 异常与修复

pressure-off 首派发时一行签名/函数体粘连的语法错误随分号链误提交并上 pod (py_compile 已报错但 commit 未被 `&&` 拦住), 修复 commit c5c19c6 后清目录重派, 无数据污染; S7 的崩溃残片一行 (run_p3s7b) 在亏损分解中定位并按"取末段 run"原则处理, 全程披露 (P4 报告 v1.1 增补); 其余无异常。

## 成本与用量 (campaign 累计)

GPU (A40 pod): G0 冒烟 + P2 四臂 + P3 主矩阵 20 流 + S5 漂移 4 流 + gate 扫描/归因重放 + S7 4 流 + seqcheck 9 流 + P4 双路 + 消融 + pressure-off 8 流, 合计约 6–7 GPU 时。API: glm-5.3 累计 ~2.66M tokens (订阅内); deepseek-v4-pro 累计 ~42.4 万 tokens ≈ $1.0, **余额 $6.03** (未过半)。

## 下一步

交 JQ 写作 (proposal §6 时间线: 8/27–28 写作, 8/29 buffer 提交)。全部材料: 本报告 + tables_p5_v1.0.md + p5_checklist_v1.1.md + frozen_scorecard_v1.json + 四份阶段报告 (P0–P4)。匿名纪律提醒 (AGENTS.md §7): 投稿产物用中性代号, repo 转公开前按 handbook §6.0 脱敏。

## 待 JQ 决策清单

1. **论文主叙事的选择**: 我建议 "条件收益 + lifecycle 信号" 双主张结构 (pressure-off 与 S6 互相印证), 但这是写作层决策, 供你定夺。
2. 若写作期需要任何补充小数字 (不重跑臂、不动冻结配置), 随时提出, journal 都在 Mac 正本。
