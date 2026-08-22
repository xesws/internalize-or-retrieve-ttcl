# Stage Report P2 v1.0 — 验证小矩阵 (G2, go/no-go)

日期 2026-08-21 · 汇报人: coding agent · 状态: **G2 三判据全部通过, 建议 GO** · 已停, 等 JQ 裁决

## 结论

P2 mini-matrix (N=20, dev split, 4 臂 S1/S2/S4/S5, 压力开启, 单 A40 pod, seed=42) 跑完并评分: **三条预注册判据全部成立**。① 局部性: S2 在 unrelated 池上出现可测退化 (漂移 0.133, 13/15 vs 基线 15/15) 且 S1 无退化 (漂移 0.0); ② 持久性: 压力下 S1 在被 evict 条目上召回坍塌 (0.167) 而存活条目 0.722 (差距 0.555), S2 无此机制性悬崖; ③ 综合分: S5 = 0.733 ≥ max(S1 0.588, S2 0.629), 且 S5 达到 S4 (0.677) 的 108% — **S5 超过了 oracle 上限** (解释见下文"数字解读")。建议: **GO — 启动 P3 主矩阵**。本轮动用了 G2 允许的**一轮**压力参数再标定 (v2→v2.1, 记录见下), 未触发任何停止条件。

## 实验设置

选取: dev_v1.1 的 u01 单用户流, 分层 N=20 (belief 8 / fact 10 / transient 2, belief ≥ 6 满足), 含 1 条完整 supersede 链 (Tandem Coffee → Coffee by Design, m000→m012) 与 1 对 near-miss 孪生 (备用车钥匙 m023 vs 备用公寓钥匙 m007)。S5 路由: glm-5.3 (prompts/router_v1.md, 哈希入 data/p2/router_s5_v1.json), 与隐藏标签一致率 17/20。检索: 本地 BM25 (pod 不持付费 key), distractor = 同 split 另一用户 (u02) 的 33 条 fact, 常驻不入预算。探针按时间位求值 (immediate 写入当 session、delayed 隔 k session、场景与链流末)。计分严格走冻结矩阵 configs/scoring_v1.yaml (G1 前置一)。每臂 fresh 模型加载, items.jsonl journal 幂等。run manifest: GPU A40 46068MiB, commit 293981a, 模型串 GEN=SYS=glm-5.3 / JUDGE=deepseek-v4-pro。

## 三条判据原始数字

| 判据 | 数字 | 结论 |
|---|---|---|
| ① S2 unrelated/near-miss 退化且 S1 不退化 | unrelated 命中: BASE 1.0, S1 1.0 (漂移 0.0), S2 0.867 (漂移 0.133); near-miss (n=1): S1 1.0, S2 1.0 | **通过** (退化由 unrelated 承载; near-miss 单对无功效, P3 需 18 对) |
| ② S1 evicted 召回坍塌且 S2 不坍塌 | S1 evicted 0.167 vs live 0.722 (坍塌 0.555); S2 无 store 无 evict, recall 0.387 无悬崖 | **通过** |
| ③ S5 ≥ max(S1,S2) 且 S5 ≥ 0.8×S4 | S5 0.733, S4 0.677, S2 0.629, S1 0.588 | **通过** (S5/S4 = 1.08) |

分轴: recall S1 0.597 / S2 0.387 / S4 0.532 / S5 0.532; freshness S1 0.167 / S2 0.5 / S4 0.5 / S5 0.667; locality (near-miss) 全 1.0。旧值残留: S5 1.0 (单链轶事, 见解读), 其余 0。transient 反转计分 (freshness): 全部 1.0 (无臂断言陈旧状态 — 各臂都不留 transient, v0 语义下合理)。session-scoped transient 单报: immediate 0.0 / paraphrase 0.0 (剔除项, 见解读)。

## 压力参数终值与再标定记录 (G2 要求)

- **v2 (初值)**: top_k=3, budget=0.7×(RAG 条目+distractor 数), distractor 同龄可逐出。缺陷: distractor 先入 store 即最旧, 14 次驱逐全部落在 distractor 上, 真实记忆零驱逐 — 判据 ② 的压力机制根本未生效 (首轮评分 evicted_recall=1.0 反常暴露)。
- **v2.1 (再标定, 本轮唯一一次)**: budget 只作用于真实 RAG 条目 (0.7×20=14 活), distractor 标记 pin 常驻 (纯检索竞争)。变更后 S1 真实驱逐 6 条最旧记忆, 判据 ② 如上成立。
- 披露: 该轮属于 R1/G2 明文允许的"一轮压力参数再标定", 变更全部在 configs/pressure_v2.yaml 注释与 git 历史中; 未动判据、未动计分矩阵、未动 HoReN 超参。

## 异常与修复 (按发生顺序)

1. **读路径移植缺陷 (最重)**: 首轮 S2 全部探针回答同一值 ("early morning") — 诊断为我移植 runner 时漏掉原型的 chat 解码读键隔离 (adapter.query_span 按用户轮 token span 提取), 走了 legacy 的"整 prompt 末 60% 池化", 脚手架行混入读取键, codebook 增大后 gate 系统性误配同一 slot。修复 = 补上 query_span (commit 498aa59), 属移植正确性而非参数调整; 首轮数据作废清除。
2. **评分器 BASE 行污染**: BASE 参照行写在 p2_S1 的 journal 里被混入 S1 聚合与 unrelated 命中率, 首轮 unrelated 漂移全为负值。修复 = 评分器按 arm 字段剥离 BASE (commit 293981a)。
3. 压力 v2 缺陷与再标定 (见上节)。

## 数字解读 (诚实边界)

- **S5 > S4 的解释**: S4 把全部 belief 编辑、全部 fact 入 RAG; S5 的 3 条路由分歧中恰有把个别 fact 也编辑或个别 belief 入 RAG 的情形, 且 S5 freshness 更高 (0.667 vs 0.5)。N=20 下这不是"S5 优于 oracle"的可靠结论, 而是 oracle 上限在 mini-matrix 规模下未被咬紧 — P3 (N=80) 才有分辨力。报告如实呈现, 不作主张。
- **自由场景是 v0 读路径的短板**: judge 自然度 (DeepSeek V4 Pro, 0-2 分) S1 0.50 / S2 0.38 / S4 0.25 / S5 0.38, 全臂偏低 — v0 读路径没有 probe–elicit–compose planner (C2, proposal §4.3), 开放任务里记忆很少被主动调用。这是 P3 前最大的已知升级项, 不影响 G2 判据 (全臂同一读路径, 对比公平)。
- **S5 旧值残留 1.0**: 唯一 supersede 链在 S5 的 new 值回答同时含旧值词 (n=1, 轶事级; P3 的 23 条链才有统计意义)。
- **eos 观察项 (JQ 指示)**: 全臂 cap-hit 0%, 生成长度中位数 9–13, 无异常截断 — §4.1 eos 监督未引入可观测的早停倾向。P3 继续监控。
- **transient session-scoped 0.0**: 各臂 immediate transient 探针全错 — 无会话缓冲的架构本来答不出"你今早状态如何", 与计分语义 (剔除) 一致, 单列不为失败。

## 成本与用量

GPU: 4 臂 × ~100–250s 纯计算 + 4 次模型加载 (A40, pod 专用)。API: glm-5.3 累计 993 调用 / 2.43M tokens (订阅); deepseek-v4-pro 32 调用 / 26K tokens ≈ $0.03, 余额 $7.28 (JQ 已充值) — 未过半, 无需报警。

## 下一步 (等 JQ 裁决)

GO 则 P3: test_v1.1 上 N≈80 五臂主矩阵 (S6 视余量), 读路径升级 probe–elicit–compose planner 前置 (否则自由场景使用率撑不起论文主张), gate 阈值 dev 扫 {0.75–0.90} 一次后冻结。

## 待 JQ 决策清单

1. **GO/no-go**: 三判据过, 建议 GO。若 GO, P3 是否直接含 S6 (utility router) 或按 handbook 排程先五臂。
2. **P3 读路径升级优先级**: judge 显示 v0 读路径在开放任务上几乎不调用记忆 — probe–elicit–compose (C2) 是否作为 P3 的前置必做 (我判断是, 但它改变 S1 的 planner 共享方式, 需你确认范围)。
3. **near-miss 规模**: mini-matrix 单对无功效, P3 用 test 的 18 对 (全量) — 确认即可。
