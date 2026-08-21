# TTCL Proposal Report — Online Memory Placement for Test-Time Continual Learning Agents

版本 v1.0 · 2026-08-21 · 目标 venue: NeurIPS 2026 TTCL Workshop (general research track, 4–9 页正文, ddl Aug 29 AoE, non-archival, 双盲)

---

## 1. 标题

推荐主标题:

**Internalize or Retrieve: Online Memory Placement for Test-Time Continual Learning Agents**

备选:

**What Belongs in the Weights: An Online Routing Policy between Parametric and Retrieval Memory for LLM Agents**

**Live, Local, Attributable: A Serving-Time Memory Architecture that Decides What to Internalize**

选择理由: 主标题把论文的决策对象 (placement) 和场景 (test-time continual learning agents) 都放进了 workshop 的词汇表里, 而且天然是 proposal 口吻而不是 finding 口吻。备选一强调 policy, 如果最终 utility router 的 preliminary 结果好, 可以换它。系统名在投稿版本里不要用 Engram —— 这个名字连着公开 repo 和 AIEWF 2026 的 README, 一次搜索就破匿名; 投稿用一个中性代号 (下文用 [SYSTEM] 占位), camera-ready 再换回。

## 2. Abstract (paper-ready 草稿, 占位符待填)

Deployed LLM agents adapt mainly through prompting, retrieval, and external tools; their weights stay frozen, so nothing they experience becomes internal knowledge. Parametric knowledge editing offers a path to internalization, but existing work treats every incoming fact as an edit and evaluates it only with question-style probes. We argue the missing component is the placement decision itself: at test time, an agent must decide, per memory candidate, whether to internalize it into model weights, keep it in a reversible retrieval store, or discard it. We present [SYSTEM], a serving-time memory architecture built around this decision. The write path classifies incoming candidates — durable beliefs and preferences, reference facts and schedules, transient noise — routes each to the matching store, and maintains a dedup/supersede lifecycle; internalized items are written as multi-key codebook edits. The read path makes internalized knowledge usable beyond Q&A: a planner decomposes open-ended tasks into explicit probes, elicits answers parametrically from the edited weights with retrieval disabled, and composes them into free-form output with per-answer attribution to the responsible memory; a shadow-editing mechanism lets consolidation run during serving with atomic hot-swap. On a multi-session personal-agent workload with hidden type labels, supersession events, and explicit budget pressure, type-based routing reaches [X]% of oracle placement on a composite scorecard, while internalize-everything degrades locality by [X] and retrieve-everything loses [X] under retrieval pressure; a counterfactual-utility router trained on both-ways outcomes provides preliminary evidence that placement can be learned from outcomes rather than labels.

(约 210 词。三个 [X] 由主矩阵和 S6 结果填; 若 S6 未做完, 删最后一句, abstract 仍然成立。)

## 3. Proposal

### 3.1 问题陈述

TTCL 的 CFP 开篇论点是: 当前 agent 部署后靠 prompting、retrieval、external tools 适应, 而不是 genuine internal learning 和 memory consolidation。现有两条技术线各占一半而互不接壤。memory-agent 线 (MemGPT/Letta、MemoryBank、Mem0 一族) 把所有记忆放在外部存储, 模型本身永远没有学到任何东西, 下一个回答依赖检索命中、prompt 预算和 chunk 排序; knowledge-editing 线 (ROME/MEMIT/GRACE/HoReN/UnKE/AnyEdit 一族) 提供了往权重里写知识的机制, 但默认一切进来的知识都该被编辑, 从不问"该不该编", 而且整条线的评测被锁死在问答式 probe 上 —— 被编辑的知识在开放生成里几乎不可见。两条线中间空着的位置就是本文的对象: **放置决策 (placement decision)** —— 在服务过程中, 对每一条新到的记忆候选, 在线决定它进权重、进可撤销的检索库、还是丢弃。

### 3.2 核心主张

主张有三层。第一, 记忆类型决定正确的存储介质: 持久的信念与偏好应当内化 (always-on、不依赖检索命中、可归因、身份一致), 参考性事实与日程应当保留在可撤销的检索库 (可更新、可删除、无干扰代价), 瞬时噪声应当丢弃。第二, 这个放置决策可以在线自动做出, 且做对的收益是可测量的 —— 不是设计品味, 而是在两个极端策略 (全部内化 / 全部检索) 各自失败的工作负载上, 路由策略逼近 oracle 放置。第三, 内化知识可以在开放任务中被真正使用并保持可归因: 读取侧的 probe–elicit–compose 机制把自由任务翻译成显式探针, 在关闭检索的条件下从被编辑的权重里参数化地引出答案, 再组稿输出, 每个答案回指到负责的 memory。

### 3.3 Contributions

C1 (写入侧): typed memory routing —— 抽取、三类分型 (belief / fact / transient)、类型到存储的路由、dedup/supersede 生命周期; 内化条目以 multi-key codebook edit 写入。C2 (读取侧): probe–elicit–compose planner —— 面向开放任务的探针生成、codebook gate、参数化引出 (主变体; text-injection 仅作消融)、组稿与 per-answer attribution。C3 (系统性质): shadow editing 下的边服务边学与请求边界上的原子热切换, 以及 attribution 通路。C4 (验证协议): 一个针对 placement policy 的多 session 工作负载构建法与 type × store 失败矩阵评测协议 —— 它把"belief 该进权重"从设计假设变成测量结果, 本身可复用。

### 3.4 定位与差异化

related work 分四线写。editing 线: HoReN/UnKE/AnyEdit 提供机制与非结构化 payload, LEME 提供长文评测, 但全线不做放置决策、评测不出开放任务中的使用; in-context 编辑线: IKE/MeLLo/DeepEdit 做"分解问题查编辑记忆", 但记忆是纯文本、目标是 multi-hop QA 而非开放写作, 且同样没有内化; memory-agent 线: MemGPT/Letta/MemoryBank/Mem0 全部外存, 正是 CFP 批评的对象; 学习型记忆管理线: Memory-R1 用 outcome-driven RL 训练 Memory Manager 在外部 memory bank 上做 ADD/UPDATE/DELETE/NOOP (ACL 2026), 是最近邻 —— 差异化的一句话是: Memory-R1 学的是单一外部存储上的 CRUD, 我们决策的是跨异构存储的放置, 其中一个目的地是权重, 内化的不可逆性、干扰代价与算力代价才使"放哪"成为真正的决策问题而不是记账。另一个要主动切割的邻居是 adaptive-RAG / Self-RAG 一族: 它们决定的是读取时要不要检索 (read-side, per-query), 我们决定的是写入时放到哪 (write-side, per-memory), 正交。

### 3.5 边界约束 (不进论文, 写作时自查)

与 AAAI 投稿 disjoint: 不做任何"自生成 query 改进 key/value"的 contribution 主张; canonical answer-free key prompts 降级为实现细节, 只按个人信念域的 collision 问题讲一段, 不进 contribution 列表, 不引 synQ 数字。与 Paper A disjoint: 本文存储介质锁死 HoReN codebook; 不做 per-domain LoRA adapter 作为路由目的地的任何变体 (那是 Paper A 的 sequential LoRA internalization 地盘)。双盲: 匿名 repo、系统改名、README 与封面素材不出现。Venue 事实: TTCL non-archival、明确欢迎 under review 工作, 与 AAAI 无 dual-submission 冲突。

## 4. Method

### 4.1 系统总览

写入路径: 用户轮 → LLM 抽取器输出严格 JSON 的记忆候选 (type、canonical text、edit stem/target、subject、answer-free key prompts、confidence) → router 分型路由: belief 进编辑缓冲, fact/other 进 RAG 库, transient / 低置信度丢弃 → consolidation pass 排空缓冲: 对既有记忆做 dedup / supersede / new 判定 → HoReN codebook edit (multi-key 写入) → 记录 provenance。读取路径: 请求先做任务形态判定 (直接 QA vs 开放任务); 直接 QA 走常规 gate → 生成; 开放任务走 planner: 由 LLM 把任务分解为若干显式探针 → 每个探针过 codebook gate (阈值判定 + slot 归属) → 对命中的记忆, 在 rag_off 条件下用探针直接问被编辑的权重, 收集参数化引出的答案 → 以这些答案为 private notes 组稿生成 → attribution: 每个使用到的答案回指 codebook slot → memory id → provenance。服务层: consolidation 在 shadow module tree 上训练, 完成后在请求边界原子晋升, 保证单次生成不混用新旧 codebook 状态; RAG 记录、chunk 向量与 codebook checkpoint 本地持久化。

### 4.2 写入侧细节 (C1)

router v0 是 LLM 分型 + 固定的类型到存储映射。分型 schema 的判据要在论文里写死: belief/preference = 关于用户自身的、预期跨 session 稳定的、希望在任何相关生成中 always-on 的陈述; fact/schedule = 参考性、可更新、可能过期、只在被问到时需要的内容; transient = 情绪、状态、一次性上下文。dedup/supersede: 新候选与既有记忆做同主体判定, supersede 时旧编辑失效、新编辑写入并在 provenance 里链到前任 —— 这是 all-edit 臂的天然弱点 (供 5.3 的失败矩阵测量), 也是本系统生命周期能力的展示点。multi-key 写入: 每条编辑除主 key 外追加若干 answer-free canonical key prompts 作为同一 value 的额外 codebook key, 动机是个人信念域的 query 高度同质 ("what do I believe / what's the best X") 导致的 collision; 一段带过, 不作为 contribution。

### 4.3 读取侧细节 (C2)

planner 用 LLM 替换现有的 lexical 词表匹配 (lexical 降级为消融, 因为手写 planner_terms 等于把一半答案喂给规划器)。探针生成的 prompt 约束: 只允许从任务文本出发提出"我关于 X 的立场/偏好是什么"形态的探针, 不允许出现任何候选答案词。gate: 探针取 query-span key, 过 hopfield_key_match_threshold, 记录 sim、slot、owner。参数化引出是本文不可妥协的设计: notes 不取存储原文, 而是 rag_off 下对被编辑权重逐探针生成的答案 —— 这是"内化知识被使用"的证据链核心; text-injection (取存储原文入 prompt) 保留为消融, 两者对照本身回答"瓶颈在激活时机还是表达能力"。组稿 prompt 要求自然融入、禁止提及 notes 存在。attribution 精度作为独立指标报告 (5.4)。

### 4.4 Router 阶梯 (v0 → v1 → v2)

原则: 复杂度加在训练信号上, 不加在机制上。信号是类型标签时, zero-shot 分类器已把信号吃满, LoRA/RL 只加参数不加能力。v0 (必交付): LLM 分型路由, 即 4.2。v1 (preliminary, 视余量): counterfactual utility router —— 在 dev 子集 (30–40 条) 上每条记忆两条路都跑 (edit-only 克隆 vs RAG-only 克隆), 量出每条的 utility 标签 = 下游 probe 增益 − locality 代价 − 算力代价, 用小模型 (embedding 上的 logistic/GBM 或 LoRA head, 形式无所谓) 学习预测更优存储, 在 held-out session 上作为第六臂报 preliminary。这是监督式 utility regression, 不是 RL, 但它是"自动决定"主张的最强实例化。v2 (future work 段, 不做实验): 真正的 RL 放置策略 —— 状态含 codebook 占用与 collision 地形, 动作含 {edit, rag, both, drop}, 奖励是延迟的 probe 结果; 与 Memory-R1 的差异化在 3.4 已立。论文里 v2 只占一段 roadmap。

### 4.5 实现映射 (repo → 论文组件)

memory/extract.py + memory/router.py → C1 分型路由; memory/consolidate.py + memory/dedup → C1 生命周期; keying.py → 4.2 的 multi-key 细节; spikes/spike_v27_free_scenario_planner.py → C2 的原型, 需要三处升级 (LLM planner 替换词表、参数化引出替换 text 注入、场景从 3 个手写升到自动生成); serving/async_editor.py + serving/shadow_editing.py + serving/model_host.py → C3; eval/ 目录现有 schema/metrics helpers → 5 的工作负载与指标层的落点。

## 5. 验证协议 (C4)

### 5.1 设计第一原则

claim 是 policy claim, 所以测试集的第一目标是让两个极端策略各自在某处失败; 造不出这两种压力, all-RAG 打平一切, 论文不成立。同时为了防"你把基准造成对自己有利"的攻击, 压力参数全部披露、以部署现实为据 (检索依赖 prompt 预算与 chunk 排序是真实约束), 并加一行 pressure-off 消融: 无压力条件下 all-RAG 与路由打平 —— 这行不是弱点, 它把结论收敛成诚实的条件句"内化在预算压力下产生收益", 并给出收益出现的边界。

### 5.2 工作负载构建

单位是合成用户的 session 流: 每用户 20–40 session, 60–100 条记忆候选, 隐藏类型标签仅生成器可见。素材播种自公开数据再由 LLM 改写成自然对话轮: belief ← PersonaChat persona 语句; 多 session 结构 ← LOCOMO/MSC 形态; fact/schedule ← 模板; transient ← 闲聊语料。每条记忆在生成时自动配套 probe: 即时 QA、延迟 QA (隔 k session)、paraphrase、自由写作场景 (每场景捆 2–3 条记忆, 场景文本不得含目标词)、supersede 后续 (更新后探老值与新值)、near-miss 孪生 (同表面不同归属, 测 collision 与 locality)。全局健康检查: 固定 MMLU 子集 + unrelated 池, 每 N 条编辑跑一次。压力机制: 对 all-RAG —— distractor 文档库、top-k 上限、store 预算触发旧条目 eviction; 对 all-edit —— 编辑数增长 (locality 漂移、collision 率)、supersede 频度 (staleness 与重编辑代价)。

### 5.3 对照臂与成功判据

| 臂 | 策略 | 预期失败点 |
|---|---|---|
| S1 | all-RAG + 同一 read-path planner | 检索压力下召回掉、eviction 后持久性失效 |
| S2 | all-edit | locality/MMLU 漂移、supersede 代价、collision 率升 |
| S3 | 随机路由 | 两边失败各占一半, 提供底线 |
| S4 | oracle 路由 (生成器标签) | 无 (上限) |
| S5 | [SYSTEM] LLM router | —— 目标: ≈ S4 |
| S6 | utility router (v1, preliminary) | 可选臂 |

成功判据预注册: 综合记分上 S5 ≈ S4 > max(S1, S2), 且 type × store 失败矩阵显示每类记忆在错误存储中的特征性失败。矩阵是论文的实证心脏: 它把类型学从假设变成测量结果。

### 5.4 指标记分卡

不合成单一数字, 报五轴: recall (即时/延迟 QA、paraphrase、自由场景使用率 —— 关键词召回为主, 异族 LLM judge 的融入自然度为辅)、locality (unrelated Δ + MMLU Δ + near-miss 误触率)、freshness (supersede 后新值正确率与旧值残留率)、cost (token、墙钟、编辑算力)、attribution 精度。数值报告遵守既有纪律: 不报四位小数, 附 run-to-run 漂移界。

### 5.5 污染纪律

session 级 dev/test 切分, persona 不相交; 工作负载生成器、router、planner、组稿四组 prompt 在测试集生成前全部冻结并打版本哈希, 附录逐字印出; 生成器模型与 judge 模型异族, judge 与系统内 LLM 异族; HoReN 编辑超参锁原文配置不动 (第一类旋钮); 系统参数 (gate 阈值、key 数、top-k、probe 数、confidence 阈值、consolidation 节奏) 仅在 dev 上小网格调后冻结 (第二类), 其中 gate 阈值给敏感性曲线且按 backbone 家族分别推定。

## 6. 实验矩阵、预算与时间线

主 backbone Llama-3.1-8B-Instruct; Qwen2.5-7B 为 stretch, 只在主矩阵提前完成时加 (gate 阈值按家族重推)。规模: 1 个工作负载 ≈ 80 条记忆 / 400–500 probe, 五臂主矩阵 ≈ 1–1.5 个 A40 GPU 日 (编辑 ~100s/条主导 S2/S4/S5, probe 生成主导评测), v1 utility router 的双路对照 ≈ 0.5–1 GPU 日, dev 迭代与返工余量 ≈ 1 GPU 日, 合计 3–4 GPU 日, A40 可承载, H100 更宽裕。时间线 (今日 8/21, ddl 8/29 AoE): 8/22–23 工作负载生成器 + probe 套件 + 冻结; 8/24–25 五臂主矩阵; 8/26 v1 双路对照与 router 训练 (若砍, 删 abstract 末句即可); 8/27–28 写作 (5–6 页: intro 1 / 架构与机制 1.5 / serving 0.5 / 评测 2 / related 0.5 / limitations 0.5, 动机段直接对位 workshop thesis); 8/29 buffer 与提交。启动前置: 该排程与 sprint Paper A 共享 GPU 与人手, 是否开跑以 8/22 sprint 收尾时 Paper A 的状态为准。

## 7. 风险与预案

R1 压力标定失败 (all-RAG 全线打平): 在 dev 上标定 eviction/top-k/distractor 参数直至极端臂分离, 参数全披露 + pressure-off 消融行; 若 belief 类在无压力下也无内化收益, 结论降级为条件句, proposal 仍立 (放置决策在预算约束下有价值)。R2 planner 探针质量不稳: 保留 oracle-plan 臂做上限拆解, 把规划误差与放置误差解耦。R3 gate 阈值敏感: 敏感性曲线 + dev 冻结, 已有前科可引以为戒。R4 时间不够: 砍序为 S6 → Qwen → 场景规模 (100→60), C1–C3 与主矩阵不砍。R5 匿名性: 改名 + 匿名 repo, 投稿 PDF 与补充材料全文 grep 一遍系统旧名与 GitHub 句柄。
