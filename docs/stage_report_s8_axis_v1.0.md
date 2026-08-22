# Stage Report — S8 分轴拆解 v1.0

日期 2026-08-22 · 汇报人: coding agent · 状态: **零 GPU 完成; belief 格子为空 (n=0)**

## 结论

S8 在真实容量设定 (pressure-off) 上综合分 0.731, 高于 router 0.708 与 oracle 未跑的 off 档; 压力开 (持久性压力测试) 上 S8 0.618 与 router 0.612、oracle 0.639 同带。新鲜度三臂压力开均为 0.724 (S5 为 0.671)。**编辑侧局部优势在综合分上不存在。** near-miss 局部性在压力测试中 S8 0.639 < S4/S5 0.694, 关驱逐后两边都到 0.833, 差距消失。belief×supersede 与 belief×near-miss **n=0** (test_v1.1 的 supersede/near-miss 对全是 fact, 共 23+23+18), 按 workload spec 如实空格, 不能用来主张「信念进权重有 supersede/near-miss 优势」。

S4-off 从未跑, 格标 `not_run`, 不补 GPU。

## 交付路径

| 项 | 路径 |
|---|---|
| 脚本 | `scripts/analysis_s8_axes.py` |
| 追加冻结 | `data/p5/s8_axis_decomp_frozen_v1.json` (checksum 对 `s8_frozen_v1.json` 四轴全过) |
| 附录表 | `tab:s8-axes`, `tab:s8-cells` (App.~C) |

## 程序性策略库

**未收到, 未开工。** 等 JQ 下发。

## 预算扫描

**撤回, 未跑。** pod `tmux ls` 空, 无 `p3b*` journal。理由已入 checklist v1.3 与 traceability v1.1。
