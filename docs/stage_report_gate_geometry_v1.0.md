# Stage Report — Gate 斜向触发几何诊断 v1.0

日期 2026-08-22 · 汇报人: coding agent · 状态: **完成, 停下等选型裁决**

## 结论

**阈值类方案无效，应建对比学习度量头。** 斜向正例与负群在 HoReN 键空间里不可分到可工作的程度。

预注册规则：可分 = AUC(斜向 vs unrelated) ≥ 0.70 **且** 存在 β∈{0.70,0.75,0.80,0.85,0.90} 使斜向 TPR≥0.70 且 unrelated FPR≤0.10。孪生 AUC 照登、不作否决。

| 配置 | AUC vs unrelated | AUC vs twin (n=10) | 可行 β | 判定 |
|---|---|---|---|---|
| multi-key **off** | 0.649 | 0.252 | 无 | 不可分 |
| multi-key **on** | 0.780 | 0.211 | 无 | 不可分（AUC 过线但无工作点） |

孪生均值 **高于** 斜向正例（on: 0.877 vs 0.852；off: 0.728 vs 0.696）——现有 Hopfield 相似度把硬负例排得比目标还近。冻结 0.90 在斜向上 TPR=0，打不到场景探针。

**不改任何冻结数字、不改论文、不改 0.90。**

## 数据

| 项 | 数量 | 路径 |
|---|---|---|
| 斜向正例（目标 264） | **246**（缺口 18） | `data/gate_geometry/oblique_dev_v1.json` |
| 孪生负例 | 10（dev 无 dedicated near_miss probe，用 qa_paraphrase × twin 链接） | 同上 `twins` |
| unrelated | 75 | `data/p3/unrelated_expanded_v1.json` |
| 词面桥 lint + MiniLM top-10 审计 | 合格才入库 | `scripts/gen_oblique_dev.py` |

审计：`all-MiniLM-L6-v2` cosine，全 dev belief+fact canonical 为库，目标 ∉ top-10。MiniLM 只用于造数审计，**不是**系统检索器。

## 测量

Key-only codebook（一次 dummy HoReN 安装 adapter，随后 `compute_key` 写入 keys，**无 value 训练**）。与生产 gate 同一套 `_query`。pod 墙钟 **71.2 s**。

原始分布：

- `results/gate_geometry/sims_multikey_off.jsonl`
- `results/gate_geometry/sims_multikey_on.jsonl`

图表（git 副本）：

- `docs/gate_geometry_v1.0/hist_three_group_{on,off}.png`
- `docs/gate_geometry_v1.0/roc_three_group_{on,off}.png`

## 触发率表

**multi-key on**

| β | 斜向 TPR | 孪生 FPR | unrelated FPR |
|---|---|---|---|
| 0.70 | 1.000 | 1.000 | 1.000 |
| 0.75 | 1.000 | 1.000 | 0.947 |
| 0.80 | 0.984 | 1.000 | 0.707 |
| 0.85 | 0.549 | 1.000 | 0.213 |
| 0.90 | 0.000 | 0.200 | 0.000 |

**multi-key off**

| β | 斜向 TPR | 孪生 FPR | unrelated FPR |
|---|---|---|---|
| 0.70 | 0.467 | 0.800 | 0.213 |
| 0.75 | 0.053 | 0.400 | 0.000 |
| 0.80–0.90 | 0.000 | 0.000 | 0.000 |

## 推荐与训练对估计

建 **对比学习度量头**（query vs memory-key），不要在现有 Hopfield 分上做逐键 margin / 分位数校准——校准救不了孪生比正例更像的排序。

估计：n_pos ≈ 246（满额 3×88=264）。每正例 8–16 个硬负例（孪生 + 随机他键）→ **2k–4k 对起跳，建议 5k–10k** 再训一个小头。正例可复用本 oblique 集，硬负例优先用孪生 paraphrase。

## 限制

- key-only，不是 88 次完整编辑后的生产 codebook。
- 孪生 n=10，AUC 方差大，但方向稳定（两次都 <0.5）。
- 18/264 斜向槽位未填满（lint/审计未过），未放宽规则。

## 待 JQ 决策清单

1. **选型**：对比学习度量头（本报告建议）还是仍要试逐键 margin（与预注册规则相悖）。
2. 若选度量头：是否授权用本 oblique 集开训，以及训练对规模（5k vs 10k）。
3. 程序性策略库仍未下发。

论文 v0 与 `frozen_scorecard_v1.json` 未动。pod 维持到 8/26。
