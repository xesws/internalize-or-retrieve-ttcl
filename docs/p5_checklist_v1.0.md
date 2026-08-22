# P5 写作出表清单 v1.1

按 JQ 2026-08-21/22 裁决固化的写作口径与出表项。P5 出表时逐条执行; 变更需 JQ 同意。
变更记录: v1.1 (2026-08-22, JQ 裁决) — 口径 3 按定稿句替换; 追加口径 5–8 (错路由单方向、supersede 键竞争、injection 空差异、abstract 末句否定结果导向); 交付清单固定含 pressure-off 消融行。

## 四条写作口径 (JQ 原裁决 + 实测数字)

1. **S4−S5 差距的措辞**: S4−S5 = 0.027, 漂移界 |Δ|=0.025。写法: "router 在运行间方差内追平 oracle 放置" (数字照登主表, 不四舍五入到主张); S5 对两个极端臂 +0.102, 为漂移界的四倍, 是主要量化主张。
2. **unrelated = 1.000 (全臂)**: 按确认性结果呈现——codebook 后端不触碰基座权重 (基线 Linear 冻结, 编辑只在 adapter 侧), 与 HoReN 已发表性质一致。dev 敏感性表 (0.75/0.80/0.85/0.90 → 误触发 0.933/0.667/0.267/0.000) 仅作为按预注册规则选定 0.90 的校准记录存档 (附录), 不进正文叙事。
3. **transient × edit 延迟高分 (S2 反转计分 0.9)** — JQ 定稿句 (2026-08-22, 替换原预设句): 中文 "对陈旧瞬时状态的延迟探针有 0.37–0.40 的触发率 (命中自身 slot 0.367), 但最终回答断言旧状态的比例仅 10%——触发不等于断言; 两个比率如实并列报告, 机制分析留给后续工作"。英文稿同义翻译。**禁** decay / interference / 任何机制归因词汇。
4. **judge 自然度与使用率成对呈现**: 任何自然度数字旁必须并列该臂的场景使用率 (keyword 命中); S3 的 0.89 注明"低使用率下的空洞流畅"。

## 追加四条 (JQ 2026-08-22)

5. **错路由呈现为单方向**: "带具体指称的偏好类条目被过度内化" (22 条全部 fact→belief), 回指 workload 文档 (docs/workload_spec_v1.0.md) 的分类规则边界——favorite-X 式表面形态与信念判据的重叠区是规则边界问题, 非模型随机错误。
6. **supersede 失败 = 键竞争一般现象**: 写成"同主体连续更新的键竞争"——key-value 存储的一般现象 (新 key 写入且可命中 7/23, 旧 key 仍在, 探针键落回旧 slot 12/23), 不表述为编辑后端缺陷; 与"fact 的归宿是可替换记录的检索库"的结论衔接。
7. **injection 对参数化引出**: dev 空差异如实报 (n=19 规模不足); 参数化引出的保留理由写为**归因与持久性的设计动机**, 不写实证优势。
8. **abstract 末句改否定结果导向**: 逐条反事实效用回归无法恢复 oracle 优势、信号在生命周期轴上 (freshness +0.33)——由此引出 sequence-aware 放置学习的 future work; 删除原 "placement can be learned from outcomes" 初步证据句。

## 结构性口径

- **v2.1 压力参数的部署对应物** (G3 paper note): distractor = 环境文档噪声, eviction = 用户记忆库容量生命周期, 二者预算独立; 防"定向设计 RAG"解读。参数全披露 + pressure-off 消融行。
- **五臂 (含 S7/S6) 共享同一 dedup/supersede 生命周期, 仅放置决策不同**——防"没实现替换"稻草人; supersede_new=0.13 的归因 (旧 slot 12 / 新 slot 7 / 其他 2 / 未命中 2) 写入失败分析。
- **场景使用率 limitation**: 口径 = "规划器探针与 key 措辞的距离" (读路径诊断): S4/S5 的 72 条场景探针中 53/52 条落在 [0.85, 0.90) 冻结阈值下沿带, 触发率 4–8%; 作为 S6 与 future work 的动机, 不表述为编辑机制缺陷。禁止读路径 prompt 再调优与 test 重跑。
- **S5>S4 未在 N=210 复现** (P2 反超为噪声) 如实标注。
- **顺序一致性确认行**: 单独成列, 定位为 HoReN 已发表顺序稳定性的复现确认; 不做门槛对比、不并入综合分; 扩容池 (75 题) 与冻结清单 v1.1 披露。

## 出表项

| 表/图 | 内容 | 数据源 |
|---|---|---|
| 主表 | 五臂+P4 增补臂 composite/五轴/judge/使用率, 附 bootstrap 95% CI 与分用户拆分 | results/p3_scorecard.json (+P4 增补) |
| 失败矩阵 | type × route 召回 (含 S7 both 列) | 同上 |
| 顺序确认行 | S2/S5 检查点 × 扩容池命中率 + base 抽查 | results/seqcheck_summary.json |
| gate 敏感性 | 校准存档 (附录) | results/gate_sweep/report.json |
| 漂移界 | S5 重跑 | results/p3_scorecard.json |
| 消融 (若完成) | text-injection / lexical planner (dev 子集) | P4 产物 |

## 数字纪律

不报四位小数 (三位为限); 全部数字可溯源到 results/ 下 journal; 主表脚注记 run manifest (GPU/commit/config hash/model strings/token 用量)。
