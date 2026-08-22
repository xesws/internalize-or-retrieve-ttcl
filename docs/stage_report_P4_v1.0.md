# Stage Report P4 v1.0 — G3 裁决落地: 分析 / S7 / 顺序确认 / S6 / 消融

日期 2026-08-22 · 汇报人: coding agent · 状态: **四项新测量与 S6/消融全部完成; 已停, 等 JQ 放行 P5 出表**

> **v1.1 增补 (2026-08-22, JQ 裁决落地)**: ① transient 措辞定稿已录入 P5 清单 v1.1 (触发率 0.37–0.40 与断言率 10% 并列, "触发不等于断言", 禁机制归因)。② **S7 亏损分解** (`results/analysis/s7_decomposition.json`, journal 级零 GPU): 冲突行 QA 0.142 (n=381) vs 非冲突行 0.080 (n=249)——两组都远低于两个单通道参考 (S2 0.284 / S1 0.552), 亏损**不是集中在冲突事件而是双通道共存下的全局压垮**; 容量侧: S7 journal 终行数 [189, 233] 与解析期望**逐用户完全一致** (u03 225 / u04 197 / u05 233 / u06 189), 编辑成本修正为 **210 次 / 924.3s** (此前 929.3s/211 次含一行崩溃 run 残片: run_p3s7b 中止前已写 u03-m000 一行, s7d fresh-model 重跑追加同文件; items.jsonl 212 键全唯一、零污染, 冻结 composite 0.226 不受影响, 残片已在分解脚本按"取末段 run"原则处理并披露); near-miss locality S7 0.111 vs S2 0.472 (同 codebook 行数) ——检索主动捞出孪生文本所致。③ 四条写作口径与 pressure-off 交付清单已入 P5 清单 v1.1。

## 结论

JQ 三项 G3 裁决与四项新测量全部执行完毕, 全部零 test 重跑、零读路径调优 (污染红线遵守)。要点: ① S5 错路由全部为单方向 **fact→belief (22 条)**, 误路由条目 QA 召回均值 0.272 (9 条全零)——router 的唯一系统性错误是把"favorite X"式表面形态当信念, 这同时是 S6 的动机数据; ② supersede_new=0.13 的 journal 级归因完成: **23 条探针中 12 条 gate 命中旧 slot、7 条新 slot、2 条其他、2 条未命中**——不是"没实现替换" (生命周期共享且生效), 而是新值 key 与旧值 key 在 codebook 中共存、探针键落回旧 slot; ③ **S7 双写臂是全矩阵最差 (composite 0.226, CI [0.17, 0.292])**——检索噪声污染参数化回答 + 233 行饱和 codebook 破坏 gate, "both" 不是安全默认, 动作空间补全后放置决策的价值更突出; ④ 顺序一致性确认行: S2 在 47–58 次编辑后扩容池命中 0.893–0.933 (基座 0.973), 与 HoReN 已发表稳定性一致; ⑤ **S6 utility router 得到干净的否定结果** (composite 0.508 ≈ S1, CI 完全重叠): 逐记忆孤立 QA 效用信号 30:6 偏向 RAG, 学到的 router 塌缩为近全 RAG——因为 oracle 对 all-RAG 的优势在 lifecycle 轴 (freshness +0.33) 而非 QA 轴, 逐记忆 QA 探针测不到它; G4 按"否定结果分析"分支通过; ⑥ 两个 dev 消融完成, injection vs 参数化引出在 dev 子集上使用率持平 (0.105/0.105, n=19 规模不足为空差异), lexical planner 选取率 0.474 (vs LLM planner gate 触发 0.042)。

## 第一节: 零 GPU 日志分析 (裁决 2/3 配套)

**S5 错路由矩阵** (`results/analysis/s5_misroutes.json`): 混淆矩阵 belief 53/53、transient 30/30 全对, fact 105/127 (22→belief, 0→transient)。注意披露: 冻结路由文件的实际一致率为 **188/210**, 早前 G3 报告写的 184/210 来自第一次 prepare 输出; 路由文件在第二次 prepare (gate 冻结提交时) 被温度-0 重跑覆盖, P3 实际执行的是 188 版, 二者相差 4 条, 哈希以冻结清单为准。22 条误路由清单 (canonical + 隐藏/预测标签 + 该记忆在 S5 的 QA 召回) 逐条落盘。

**Gate 归因** (`results/analysis/gate_attribution.json` + `..._s2.json`, gate-only 重放, 未重跑任何臂):
- **supersede 三分类** (S2, n=23): 旧 slot 12 / 新 slot 7 / 其他行 2 / 未命中 2。旧 slot 命中者即"探针键距旧值 key 更近"——旧值编辑先入 codebook、新值编辑追加 key 但探针措辞 (来自生成器的链探针) 与旧 stem 更相似。五臂共享同一 dedup/supersede 生命周期、仅放置决策不同——此归因直接反证"没实现替换"的解读 (替换生效 = 新 key 已写入且可命中 7 条)。
- **transient×edit 延迟触发率** (S2, n=30): gate 触发 0.40, 命中自身 slot 0.367 (18 未命中 + 1 其他), 但回答断言率仅 0.1 (反转计分 0.9 的另一面)。⚠ **措辞预警**: 裁决预设句"延迟的陈旧状态探针很少触发对应编辑"与实测 0.37–0.40 不符; 建议改为"延迟的陈旧状态探针仍以 ~0.4 比率触发对应编辑, 但回答中仅 10% 断言该状态"——纯描述、无机制推测, 待 JQ 定稿 (已入 P5 清单)。
- **场景探针直方图** (72 条 × S2/S4/S5): S4/S5 的 53/52 条落在 [0.85, 0.90) 冻结阈值下沿带, 触发率仅 0.042/0.083; S2 (全量编辑) 触发 0.389。limitation 口径成立: 瓶颈是"规划器探针与 key 措辞的距离" (读路径), 不是编辑机制。

## 第二节: S7 双写臂 (新测量 1)

标注: **主矩阵后追加的动作空间补全臂** (固定策略: 全部 210 条记忆含 transient 双写 edit+RAG; 流序/读路径/冻结计分与主矩阵一致)。**composite 0.226 [0.17, 0.292], 全臂最差** (recall 0.119 / freshness 0.447 / locality 0.111; unrelated 1.0)。失败矩阵 both 列: belief 0.172 / fact 0.097 / transient 0.078——fact 双写 (0.097) 比 fact 仅编辑 (0.233) 更差: 检索窗口的噪声 (distractor + 陈旧 superseded + transient 全在库里) 污染了参数化回答, 同时 233 行 codebook 让 near-miss locality 崩到 0.111。**双写成本落盘**: 编辑算力 929.3s (210 次编辑, ~4.4s/条), codebook 233 行 + RAG 库存储翻倍; **冲突日志 438 条** (`results/p3_S7_u*/items.jsonl` 的 s7_conflict 字段: gate 引出值、检索文本、两者是否都可答、组稿最终答案是否含关键词)。结论: "both" 既贵又最差, 放置决策的必要性拿到第七个数据点。

## 第三节: 统计加固 + 顺序一致性 (新测量 2/4)

**Bootstrap CI 与分用户拆分** (`results/p3_scorecard.json` 全臂):

| 臂 | composite | CI95 | 分用户 (u03/u04/u05/u06) |
|---|---|---|---|
| S1 | 0.510 | [0.434, 0.579] | 0.598/0.500/0.424/0.518 |
| S2 | 0.401 | [0.319, 0.486] | 0.544/0.353/0.360/0.330 |
| S3 | 0.388 | [0.304, 0.476] | 0.641/0.301/0.236/0.352 |
| S4 | 0.639 | [0.564, 0.706] | 0.788/0.569/0.566/0.624 |
| S5 | 0.612 | [0.548, 0.678] | 0.696/0.527/0.593/0.621 |
| S6 | 0.508 | [0.432, 0.578] | — (与 S1 同构) |
| S7 | 0.226 | [0.170, 0.292] | 0.230/0.280/0.251/0.144 |

S5 与 S4 区间大幅重叠 (方差内追平口径成立), S5 与 S2/S3/S7 不相交。S4−S5 = 0.027 vs 漂移界 0.025。

**顺序一致性确认行** (`results/seqcheck_summary.json`; 扩容池 75 题冻结于 `data/p3/unrelated_expanded_v1.json`, freeze v1.1, 对称 lint 全过): 基座抽查 0.973; S2 各用户 ck10/ck25/流末 = 0.92–0.973 / 0.907–0.973 / 0.893–0.933 (47–58 次编辑); S5 (16–22 次编辑, ck25 不可达已披露) 流末 0.867–0.947。全内化臂在 ~55 次顺序编辑后漂移 ≤ 0.08——与 HoReN 已发表顺序稳定性一致的复现确认; 不做门槛对比、不并入综合分、单独成列。

## 第四节: S6 utility router (P4, preliminary) — 否定结果分支

双路对照 (`results/p4/dualpath_dev.json`, dev 36 条含 12 条配对成员; λ_loc=1.0, λ_cpu=0.022, 中位编辑 4.4s, 全披露): **效用标签 30 rag / 6 edit**——孤立克隆里编辑的 QA 增益很少跑赢检索, 且要扣 locality 漂移与算力。logistic (11 个可解释特征, 纯 numpy) train 0.833 / LOO 0.778, 但把该决策面应用到 test 只路由 2/210 条进编辑。**S6 实测: composite 0.508 ≈ S1 (0.510), CI 完全重叠; judge 0.83。**

归因 (干净、可写): oracle 对 all-RAG 的优势分解为 recall +0.005 / **freshness +0.329** / locality +0.055——全部在 lifecycle 轴; 而逐记忆孤立双路只测 QA 探针增益, lifecycle 收益 (supersede 新旧值、near-miss 排他) 在单记忆克隆里结构性不可见。**教训 (论文 S6 preliminary 段)**: 从结果学放置, 训练信号必须包含生命周期探针 (或流级对照), 否则效用回归塌缩为 all-RAG。G4 判据按 handbook 预注册的"否定结果分析"分支通过。

## 第五节: 消融 (dev 子集, 时间富余完成)

1. **text-injection vs 参数化引出** (`results/p4/ablation_injection.json`, n=19 记忆×场景行): 使用率 0.105 vs 0.105——**空差异**, dev 子集规模不足以区分两变体; 如实报为 "no difference at this scale", 主变体选择的依据仍是参数化引出的可归因性 (设计论点) 而非该消融。
2. **lexical vs LLM planner** (`results/p4/ablation_planner.json`): lexical 词表选取率 0.474 (被捆记忆进入 top-3 的比率), LLM planner 的 gate 触发率 0.042–0.083——词表法"选得多"但选出的是表面重叠 (含大量非答案条目), LLM 法问得准但探针措辞距 key 远; 两者是不同性质的失败, 支撑"读路径诊断"的 limitation 口径。

## 异常与修复

S7 首派发两连崩 (冲突函数调用多传一参; S6 路由文件未按需加载), 修复后一次跑通; dispatch.sh 的 EXIT 码此前记录的是 tee 的退出码, 已加 pipefail 修正 (历史 run 的成败以日志 traceback 为准, 未受影响)。扩容池生成首批被思考截断, 改小批量+8192 预算后过 lint (75 题)。S2-only 归因重放补 transient 自身 slot 分类一次。

## 成本与用量

GPU: S7 四流 ~31 min + seqcheck 8 流+base ~75 min + 双路对照 ~30 min + 归因重放 ~45 min + 消融 ~12 min。API: glm-5.3 累计 2.61M tokens (订阅); deepseek-v4-pro 累计 421K tokens ≈ $1.0, **余额 $6.03 (未过半线 $3.64)**。

## 下一步

等 JQ 放行 P5 出表: `docs/p5_checklist_v1.0.md` 已就绪 (四条写作口径 + v2.1 paper note + 出表清单 + 数字纪律); 一处措辞待裁 (transient 触发率, 见第一节)。

## 待 JQ 决策清单

1. **transient 措辞定稿** (第一节 ⚠): 实测触发率 0.37–0.40 vs 预设句"很少触发"。建议句已给出, 请裁决。
2. **P5 放行** + injection 消融的呈现方式: 建议作为附录空差异诚实报告, 正文不引。
3. **S6 写法确认**: 按"否定结果 + 生命周期信号缺失归因"写 preliminary 段 (G4 允许), 若你希望再给 S6 一次机会 (效用标签加入 near-miss/unrelated 项后重训重跑, ~1 GPU 时 + 20 min), 需明确授权——它是对 G4 协议的扩展而非重试。
