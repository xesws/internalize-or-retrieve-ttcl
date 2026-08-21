# Stage Report P1 v1.0 — 工作负载与 Probe 套件 (G1)

日期 2026-08-21 · 汇报人: coding agent · 状态: **G1 有条件关闭 → 条件已达成 (2026-08-21 JQ 抽查 8/10 通过, 两项前置完成后视为关闭, 无需再等)**

> **v1.1 增补 (2026-08-21 晚, G1 收口)**: 按 JQ 抽查结论完成两项前置。
> **前置一 (计分语义矩阵)**: `configs/scoring_v1.yaml` 冻结 per-type × per-kind 口径——transient 不进 recall 综合; transient × qa_delayed 反转计分 (断言陈旧瞬时状态 = freshness 失败); transient × qa_immediate/qa_paraphrase 因各臂 v0 服务路径均无会话缓冲而剔除综合分、单独报告; supersede_new/old 归 freshness; near_miss 归 locality (keyword_exclusive 打分)。G2 判据 ③ 的综合分只经 `src/evalx/scorecard.py` 按此矩阵计算, 配 6 项 CPU 单测。
> **前置二 (时间一致性审计)**: `scripts/audit_scenario_temporal.py` 全量审计 free_scenario × supersede 链, 发现 **15 处违例** (dev 3 / test 12)——捆住被取代旧值记忆的场景探针仍期望旧值 keywords, 而场景约定流末求值、当时值应为链终新值。修复仅改 15 条探针的 answer_keywords (机械推导、无 LLM 调用、场景文本未动), 工作负载升 **v1.1** 重冻结 (`{dev,test}_v1.1.json` + `freeze_manifest_v1.1.json` + `data/workloads/CHANGELOG.md`), 全部冻结门重验通过 (schema 0 / lint 0 / turn 0)。审计明细存 `data/workloads/temporal_audit_v1.1.json`。附带修正: answer_keywords 派生改为"边缘修剪整短语"语义 (内部停用词保留, "Coffee by Design" 可匹配; 边缘代词仍去除)。
> 三项裁决落档: proposal §5.2 播种句改写 (头部升 v1.1); 分类规则与 belief 23% 冻结、P2 N=20 分层 (belief ≥ 6) 写入 `docs/workload_spec_v1.0.md`; DeepSeek 口径不变。两条小项: `docs/adjudication_log_v1.0.md` 开档 (首批 2 条词面误报); probe 视角分布实测 (第二人称 572 / 第一 216 / 第三 121 / 中性 129) 冻结为约定写入 workload spec §4。**G1 就此关闭。**

## 结论

工作负载 v1 已生成并冻结入 `data/workloads/` (dev_v1.json + test_v1.json + freeze_manifest_v1.json, 均已入 git)。G1 的三项机器验收全部通过: schema 校验 100% (冻结门拒绝任何非法记录, 0 错误)、target-free lint 100% (dev 363 + test 740 共 1103 个探针, 冻结态 0 违规)、probe 计数达标 (test 740 个, 高于主矩阵 400–500 的需要; dev 363 个, 足够 P2 的 N=20 子集)。persona 不相交的 session 级 dev/test 切分完成 (dev 2 用户 / test 4 用户, 用户级隔离, 记忆与场景 id 无交叉)。**唯一待办是人抽查 10 条 (G1 第四项), 样本已备好 (下文), 通过后 G1 正式关闭。**

## 做了什么

按 handbook §3.1 在 Mac 侧建成 `src/workload/` (schema / generator / lint / repair / split / freeze) 与 `src/llm/client.py` (Mac 侧唯一付费 API 出口, 角色制, 逐调用 token 计量入 journal, 3 次重试后报错不静默降级), 五组版本化 prompt 落盘 `prompts/gen_*_v1.md` (哈希入冻结清单)。生成管线: 每用户 persona+类型化记忆池 → 会话话轮嵌入 → 逐记忆 edit 字段+三连 QA 探针 → supersede/near-miss 成对探针 → 自由场景 (捆 2–3 条记忆) → 一致性审计与重绑 → lint 修复轮 (每探针最多 3 次重写 + QA 回退, 超一轮仍 >2% 即停) → dev/test 切分 → 冻结门 (schema + lint + turn 一致性三项全零才允许写盘)。全程 journal 幂等可续跑。GEN=SYS=glm-5.3 (Z.AI 订阅), judge=deepseek-v4-pro 已通冒烟 (1 次调用, 175 tokens); DeepSeek 余额 $2.29 未动 (judge 冒烟 < $0.001)。

## 冻结产物数字

| | 用户 | 记忆 (belief/fact/transient) | 探针 (7 类) | lint | turn 一致 |
|---|---|---|---|---|---|
| dev | 2 | 104 (24/64/16) | 363 | 0 违规 | 0 不匹配 |
| test | 4 | 210 (53/127/30) | 740 | 0 违规 | 0 不匹配 |

探针构成 (test): qa_immediate/delayed/paraphrase 各 207–211, free_scenario 47, supersede_old/new 各 23, near_miss 18。生成用量: GLM-5.3 共 973 次调用 / 2.42M tokens (订阅额度); 冻结清单 git sha f8c245a08。

## 异常与修复 (按发现顺序)

1. **GLM 思考内容挤占 completion 预算**: 4096 max_tokens 下长 JSON 被截断无法解析, 曾致全量 run 中断。修复: 预算升至 8192 + 解析失败一次双倍预算重试 + 逐用户故障隔离。
2. **会话 id 绑定松动**: 会话生成 LLM 偶尔把记忆 id 挂到内容无关的话轮上 (抽查发现约半数样本 turn 与 edit 字段讲不同事实)。修复: 完整性校验 (id 集合精确匹配) + 冻结门加 turn↔canonical/target 一致性审计, 不一致记忆由 rebind prompt 按 canonical 重写话轮。
3. **journal 跨计划污染 (最严重)**: pilot (6 会话) 与全量 (24 会话) 的 `plan_memories` rng 消耗序列不同, canonical→id 映射不同, 但 journal 只按 id 缓存——u01 的 pilot 数据被复用到全量计划, 41/47 条 canonical 错位。修复: journal 按 n_sessions 命名空间隔离, u01 在 24 会话命名空间全量重生成; 迁移 u02–u06 的有效缓存后终检 dev/test 的 canon-fields 漂移为 2/0, 且残余 2 条经人工核对均为词面启发式误报 ("hand-written lists"↔"pen and paper"; 单复数 "paperback(s)"), 语义一致。
4. **lint 假阳性两类**: 代词 "her" 被当答案关键词; 单词子串 ("hat"⊂"what")。修复: 停用词扩充代词/系动词; 词边界匹配; 多词目标以整短语为关键词 (判别单元是 "second tuesday" 而非 "tuesday")。
5. **near-miss 探针装配 key 错位** (挂 B 查 A 的键), 修复后 near_miss 计数 10+18 恢复。

## JQ 抽查样本 (10 条, 全部取自 dev split, 冻结后随机分层抽取)

1. **u02-m035 (belief)** 话轮 "if the family gathering drifts into politics, change the subject" → stem "At family gatherings, the one subject the user never brings up is" → target " politics"; 探针 "To keep the peace at those family get-togethers, what topic do you refuse to get into?"
2. **u01-m010 (belief)** 话轮 "keep my mornings clear — early morning is the best writing time" → stem "Regarding focused editing work, the user believes the ideal time of day is" → target " early morning"; 探针 "when during the day do you feel most able to concentrate on your editing?"; 场景探针捆月度排版计划。
3. **u01-m003 (belief)** 话轮 "assume I'd rather walk or cycle than drive" → target " walking or cycling"; 探针 "So how do you usually get around town?"
4. **u02-m043 (fact)** 话轮提到 Blue Heron Bakehouse → stem "the user's favorite cafe in town is" → target " Blue Heron Bakehouse"; 探针 "Where do you like to stop for coffee and a pastry these days?" (无泄漏)
5. **u01-m032 (fact)** 话轮 "my sister's birthday is April 12th" → target " April 12th"; 探针 "When does your sister's birthday come around?"
6. **u01-m030 (fact)** 话轮父亲心脏医生 → stem "The cardiologist overseeing the user's father's heart care is" → target " Helen Marsh"; 探针 "Who is the cardiologist taking care of my father?"
7. **u01-m044 (transient)** 话轮 "feeling pretty foggy and under-caffeinated" → target " foggy and under-caffeinated"; 探针 "how would you sum up how I'm doing this morning?"
8. **u01-m012 (fact, supersede 新值)** 话轮换社区后常去 Coffee by Design; `supersede_of: u01-m000` (旧值 Tandem Coffee); 探针 "Which spot became your favorite after the neighborhood change?"; 旧值记忆 m000 带 supersede_old 探针。
9. **u01-m023 (fact, near-miss A)** 备用**车**钥匙在厨房抽屉, `near_miss_twin_of: u01-m007` (备用**公寓**钥匙放邻居处) — 同表面 ("spare key") 不同归属。
10. **u01-m000 (fact + 场景)** 最爱咖啡馆 Tandem Coffee; 场景探针 "Plan my Saturday morning… prescriptions dropped off by ten, two hours of manuscript…" 捆 2 条记忆, 场景文本无任何目标词。

## 下一步 (等 JQ)

抽查通过 → G1 关闭 → 启动 P2 mini-matrix (N=20, 4 臂, 压力开启, pod 单卡, G2 预注册三判据)。

## 待 JQ 决策清单

1. **Persona 播种源偏离**: proposal §5.2 写 "belief ← PersonaChat 播种"; 当前实现为 GLM 自生成虚构 persona (规避 license 核实与下载成本, dev/test persona 不相交不受影响)。若要求真实 PersonaChat 播种, 需重生成工作负载 (约半天); 不裁则维持自生成并写入论文 workload 构建节。
2. **类型配比**: belief 占比 ~23% (24/104 dev, 53/210 test), 低于 persona 池配比的原因是 supersede/near-miss 的发明对默认计为 fact。belief 是内化主张的核心类, 配比是否需要上调 (如把部分发明对计入 belief) 请裁决; P2 选 N=20 时可按类型分层抽样缓解。
3. **DeepSeek 余额**: 当前 $2.29 未动 (P1 未用付费 API; judge 冒烟 < $0.001)。P2 的 judge 用量预计 < $1, 维持"不充值不阻塞、过半报警"口径。
