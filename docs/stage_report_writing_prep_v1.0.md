# Stage Report — 写作期就绪报告 v1.0

日期 2026-08-22 · 汇报人: coding agent · 状态: **写作期任务 1/3 完成, 待命处理机械性修订**

## 结论

论文脚手架 (任务一) 与匿名化打包 (任务三) 完成, 叙事口径入清单 (任务二), pod 处置时间线入清单 (任务四, 8/26 JQ 门控)。全部冻结数据零触碰——表格一律由脚本从 `data/p5/frozen_scorecard_v1.json` 生成, 无手抄数字。匿名导出一次过审 (身份模式 0 命中)。

## 交付物与路径

| 交付物 | 路径 |
|---|---|
| 论文骨架 (双盲, section 结构+每节要点注释, 不含正文) | `paper/main.tex` |
| 附录骨架 (顺序确认/gate 校准/prompt/manifests 四节) | `paper/appendix.tex` |
| **表格 (七表 booktabs, 自动生成)** | `paper/tables.tex` + `paper/appendix_tables.tex` |
| 表格生成脚本 (唯一数字来源=frozen scorecard) | `scripts/paper_tables.py` (重跑: `python3 scripts/paper_tables.py`) |
| bib 起底稿 (18 条, 逐条网络核实) | `paper/refs.bib` |
| 风格文件 (占位 stub, 官方 2026 kit 发布后替换) | `paper/neurips_2026.sty` |
| 匿名导出 (代号 MEMPLACE, 暂定) | `exports/memplace_v1/` (repo/ + supplementary/ + ANON_CHECK.md, 审计 0 命中 PASS) |
| 叙事口径 + pod 处置时间线 | `docs/p5_checklist_v1.0.md` (已升 v1.2, 文件名不变) |
| 匿名导出脚本 | `scripts/anonymize_export.py` |

## Bib 核实状态表 (全部已核实; 两处 handbook venue 勘误)

| 条目 | arXiv ID | 核实结果 |
|---|---|---|
| HoReN | 2605.08143 | ✅ "HoReN: Normalized Hopfield Retrieval for Large-Scale Sequential Model Editing" |
| ROME / MEMIT / GRACE | 2202.05262 / 2210.07229 / 2211.11031 | ✅ (高置信, 未变) |
| UnKE | 2405.15349 | ✅ "Everything is Editable: Extend Knowledge Editing to Unstructured Data…" (handbook 未记 ID, 已补) |
| AnyEdit (LLM 版, 我们引用的语义) | 2502.05628 | ✅ "AnyEdit: Edit Any Knowledge Encoded in Language Models", ICML 2025; 注意与同名图像编辑论文 (2411.15738, CVPR 2025) 区分 |
| LEME | 2402.09394 | ✅ "Long-form evaluation of model editing" |
| IKE / MQuAKE / DeepEdit | 2305.12740 / 2305.14795 / 2401.10471 | ✅ DeepEdit 为 "Knowledge Editing as Decoding with Constraints" (handbook 只写名字, 已核实) |
| MemGPT | 2310.08560 | ✅ |
| MemoryBank | 2305.10250 | ✅ (AAAI 2024 版入 bib) |
| Mem0 / Memory-R1 | 2504.19413 / 2508.19828 | ✅ (Memory-R1 标题与 ADD/UPDATE/DELETE/NOOP 语义确认, 差异化句可用) |
| Self-RAG / Adaptive-RAG | 2310.11511 / 2403.14403 | ✅ Adaptive-RAG = NAACL 2024 |
| PersonaChat | 1801.07243 | ✅ ⚠️ **handbook 勘误: venue 是 ACL 2018 非 ICLR** |
| MSC | 2107.07567 | ✅ ⚠️ **handbook 勘误: venue 是 ACL 2022 非 EMNLP 2021** |
| LOCOMO | 2402.17753 | ✅ ACL 2024, "Evaluating Very Long-Term Conversational Memory of LLM Agents" |

注: HoReN 与 Memory-R1 的 bib 作者字段留占位——前者以正式发表版作者为准 (arXiv 页已见, 写作时从原文确认), 后者作者列表较长建议从 arXiv 页直接粘贴。这两条在 refs.bib 里有注释可查。

## 表格生成纪律

`paper/tables.tex` 头部有 AUTO-GENERATED 标记; 修改数字的唯一合法路径 = 改 frozen scorecard (冻结, 不动) 或改脚本。写作期如需调整表格式 (列序/表注措辞), 改 `scripts/paper_tables.py` 后重跑即可, LaTeX 手改仅限 caption 文字。

## Pod 状态

维持运行 (无新 run); 8/26 草稿数字定稿后按 checklist v1.2 关闭清单执行 (rsync 校验 → 清凭证 → 轮换 HF_TOKEN), 全程等 JQ 确认。

## 待 JQ 决策清单

1. **代号定稿**: MEMPLACE 为暂定, 可改 (改 = 跑 `scripts/anonymize_export.py` 顶部 CODENAME + 重跑)。
2. **HoReN/Memory-R1 作者字段**: 写作时从原文粘贴, 或授权我用 arXiv 页作者列表填全。
3. 官方 neurips_2026.sty 发布后替换 stub (编译兼容性届时验证一次)。
