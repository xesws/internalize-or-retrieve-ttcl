# Workload Spec v1.0 — 构建规则与冻结约定

适用: `data/workloads/{dev,test}_v1.1.json`。本文件是工作负载构建规则的显性化记录, JQ 2026-08-21 抽查后裁决要求的落点; 变更需升版。

## 1. 类型判定规则 (冻结)

- **belief** = 关于用户的立场、偏好、习惯的陈述, **无可变外部指称** — 不指向会过期的日期/地点/人名/账户/排班, 预期跨 session 稳定, 希望在任何相关生成中 always-on。
- **fact** = 带具体**可更新外部指称**的条目 — 日期、地点、机构、人名、账户、排班、持有物; 可能过期, 被问到时才需要, 天然适合可撤销的检索存储。
- **transient** = 一次性状态、情绪、上下文 (如 "今早有点迷糊"); 不跨 session, 正确归宿是丢弃或会话级缓冲。
- supersede 对与 near-miss 对在 belief/fact 上构造; 其发明条目按上述规则归类 (多数落 fact)。
- **belief 占比 ~23% (24/104 dev, 53/210 test) 冻结**, 不再上调 (JQ 裁决 2026-08-21)。

## 2. persona 来源 (裁决定案)

persona 与记忆池由 GEN 模型 (glm-5.3) 自生成虚构用户; PersonaChat / MSC / LOCOMO 仅作多 session 结构与类型学的**参照引用**, 不作素材播种源。论文 workload 构建节**如实披露**自生成来源。dev/test 切分按用户粒度, persona 天然不相交。

## 3. P2 选取规则 (冻结)

P2 mini-matrix 的 N=20 从 dev split 分层抽样: **belief ≥ 6 条**, 余量按冻结配比分配 fact/transient, 且至少含 1 条完整 supersede 链与 1 对 near-miss 孪生。抽样 seed=42, 选取清单随 run manifest 冻结。

## 4. probe 叙述视角约定 (冻结)

v1.1 实测分布: 第二人称 (you/your) 572 / 第一人称 (I/my) 216 / 第三人称 121 / 中性 129 (共 1038 条文本探针)。约定: **面向助手的提问以第二人称为默认形态**, 同义改写与修复轮不得切换视角; 场景任务文本为指令体 (中性)。后续生成若偏离此分布视为缺陷。

## 5. 语义等价裁定留档

词面启发式 (keyword overlap) 判定不一致但语义等价的条目, 逐条录入 `docs/adjudication_log_v1.0.md`, 不改数据。

## 6. 求值时位约定

qa_immediate / qa_paraphrase 在写入 session 求值; qa_delayed 在隔 `after_sessions` 个 session 后求值; free_scenario 一律**流末**求值 (v1.1 时间一致性修复的依据); supersede_old / supersede_new 在链完成后求值。
