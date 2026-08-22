# Stage Report — 写作期 v1.1 (全文 v0 + S8 收口)

日期 2026-08-22 · 汇报人: coding agent · 状态: **全文 v0 已编译, 匿名导出 v2 已打, 停下等 JQ 通读**

## 结论

没有挂。上一轮是会话上下文被压缩, 不是进程死掉。S8 是你在 G5 之后明确授权的防御臂, 不是新开一轮主实验: 类型感知、只检索 (belief+fact 进 RAG, transient 丢弃)、零 HoReN 编辑, 用来回答论文里 "Why not retrieval-only?"。它仍然要占 A40, 因为 740 条探针要在 Llama-3.1-8B-Instruct 上生成答案 (和 S1 一样走生成, 只是不写 codebook)。S8 已跑完并冻结: 压力开 0.618 [0.543, 0.69], 压力关 0.731 [0.68, 0.78], 与 LLM router 持平或略高, 新鲜度到 oracle 水平。主表数字未改 (`frozen_scorecard_v1.json` 零触碰)。全文 v0 已按这份诚实口径改写, PDF 在 `paper/main.pdf`。本回合修完 PDF 视觉审查里的硬伤 (MemGPT 文献键、附录 A/B 重复、S8 上标被 `\S` 吃成乱码、表堆在参考文献后、摘要 "reaches 0.612 of oracle"、正文手写 n=19)。然后停下, 等你通读和 rebuttal 意见。不启动 P6, 不加新 GPU run。

## 交付物与路径

| 交付物 | 路径 |
|---|---|
| 全文 v0 (双盲, MEMPLACE) | `paper/main.tex` |
| 编译 PDF | `paper/main.pdf` |
| 宏 (散文唯一数字入口) | `paper/numbers.tex` ← `scripts/paper_macros.py` |
| 主表 + 附录表 (自动生成) | `paper/tables.tex`, `paper/appendix_tables.tex` ← `scripts/paper_tables.py` |
| 主张↔表/宏追溯 | `docs/claims_traceability_v1.0.md` |
| S8 冻结 | `data/p5/s8_frozen_v1.json` |
| 分析冻结 (含 ablation n=19 与 S7 参照) | `data/p5/analysis_frozen_v1.json` |
| 匿名导出 v2 | `exports/memplace_v2/` (`ANON_CHECK.md` 必须 0 命中) |
| 本报告 | `docs/stage_report_writing_prep_v1.1.md` |

## S8 一句话

S8 证明: 带 supersede 的类型感知单库检索已经是强默认; 放置决策的复合分优势不在 "编辑本身", 而在可替换记录的生命周期。论文 Claim 2 按此改写, 不把 S8 藏起来。

## 本回合 PDF 修订

1. MemGPT: bib 键改为 `packer2023memgpt`, 与正文 `\citep` 对齐 (原先键是 `zhong2024memgpt`, 编译成 `[?]`)。
2. 附录不再双重编号: `appendix_tables.tex` 出 A/B 节, `appendix.tex` 只留 Prompt / Manifests。
3. 失败矩阵用 `\makecell` 折行, 避免 Dual/RAG/Edit 列撑破版心。
4. S8 行标签改为 `\textsc{single-store} (S8)`, 不再写 `$^{\S8}$` (Times 里 `\S` 看起来像第二个 8)。
5. `\input{tables}` 移到参考文献之前并 `\clearpage`, 表不再堆在 bib 后面。
6. 摘要改为 "scores 0.612 against oracle 0.639"。
7. `n=19` 改为宏 `\AblationN`, 来源写入 analysis freeze。

## Pod 与下一步

Pod 维持到 **2026-08-26**, 无新 run。关闭仍须你确认: rsync 校验 → `rm ~/.hf_env` → 轮换 HF_TOKEN。官方 `neurips_2026.sty` 发布后替换 stub。P6 与任何新 GPU 工作未授权。

## 待 JQ 决策清单

1. 通读 `paper/main.pdf` 与 rebuttal 意见 (本阶段停在这里)。
2. 官方 NeurIPS 2026 风格文件到位后替换 stub。
3. 8/26 后是否关 pod (仍按 checklist v1.2, 需你点头)。
