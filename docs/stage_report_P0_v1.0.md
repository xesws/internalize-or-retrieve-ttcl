# Stage Report P0 v1.0 — 环境与编辑后端冒烟 (G0)

日期 2026-08-21 · 汇报人: coding agent · 状态: **G0 通过**

## 结论

G0 全部验收项通过: 在 RunPod A40 上, 5/5 条虚构事实编辑成功写入同一 HoReN codebook, gate 在 5/5 条 stem 上命中自身 key (sim 1.00–1.01, 阈值 0.85), §4.1 三查全部通过。**编辑后端 (移植 + 补丁) 可用于 P2。** 比计划多发现并修复了一层更深的 §4.1 缺陷 (训练序列中根本没有终止符), 详见下文; 这属于红线补丁的完成而非范围变更。

## 做了什么

按 handbook §3.1 建出仓库脚手架并推送 (commit 6e5e828 起); 从参考实现 main@5ee64839 移植 `third_party/horen` (最小编辑路径: `horen_backend/models/horen/*` + util 存根 + `hparams/HOREN/llama3.1-8b.yaml`)、`keying.py` → `src/readpath/keying.py`、`serving/model_host.py` → `src/stores/model_host.py` (常驻模型 + 编辑模块热切换)、`editing.py` → `src/stores/editing.py` (含 §4.2 multi-key chat 写入)。vendored 包顶层目录由 `src/` 改名 `horen_backend/` 以避免与本仓库 `src/` 的 Python 包名冲突, 代码逐字未动, 偏差全部记录在 `third_party/horen/PROVENANCE.md`; yaml 仅把绝对路径换成 HF hub id, 编辑超参一个未动。在 pod 上完成 pod_setup (依赖、backbone 16GB 下载、CPU 测试、GPU smoke), 然后以 tmux 运行 `spikes/spike_g0_smoke.py` (run: g0_smoke, 第 4 次执行通过, 前三次为 check(a) 参照口径修正, 见"异常与修复")。

## 验收逐条勾对 (handbook §5 P0 → G0)

| 验收项 | 结果 | 数字 |
|---|---|---|
| 5 条编辑写入成功 | ✅ | codebook 16 行 (1 占位 + 5 原生 key + 10 追加 chat key), 每条编辑 100 步, loss 3.8–8.6 → 0.0001–0.0015, 单条编辑 ~4.4s |
| gate 命中自身 key | ✅ | 5/5, sim 1.00–1.01 (阈值 0.85), slot 全部落在该条记忆自己的追加 key 上 (2/5/8/11/14) |
| 三查 (a) gold 边界 p(eos) 恢复 | ✅ | 补丁前 (序列无 eos): 编辑后 ~1e-8; 补丁后: 0.72–0.96, 与未编辑基线在 chat 自然回答边界的参照 (p(eot)=1.0) 同量级 (比值 0.72–0.96) |
| 三查 (b) 512 解码上限 | ✅ | cap-hit 0/5 (0% ≤ 10%), 生成长度中位数 16 (< 150) |
| 三查 (c) 训练步数分布不变 | ✅ | 5 条编辑全部恰好 n_iter=100 步 (无早停机制, 与补丁前结构一致) |

Run manifest (`results/g0_smoke/manifest.json`): GPU = NVIDIA A40 46068MiB, commit = 7bb54ad, config 哈希已记录, 模型串 GEN=SYS=glm-5.3 / JUDGE=deepseek-v4-pro / DEV_AUX=deepseek-v4-flash (JQ 2026-08-21 指定的两家族模型池)。

## §4.1 补丁的完整故事 (异常与修复)

上游缺陷手册已确诊两层: pad=eos 别名导致 (i) prompt 长度按"非 pad 计数"偏差 1, (ii) 按 pad 掩码把答案末端真正的 eos 一并掩掉。移植后打补丁将掩码改为 attention_mask 口径, CPU 单测 (7 项, `tests/test_pad_eos_mask.py`) 全部编码了这些不变量。但 G0 三查 (a) 第一轮即失败并暴露**第三层缺陷**: 我们管线的编码是纯文本, tokenizer 根本不会在序列里放终止符——掩码逻辑修得再对, 也无 eos 可监督, 编辑后模型在 gold 边界 p(eos) 仍 ~1e-8 (无停止信号, 与手册描述的病症一致)。修复: 在 `_tokenize_prompt_and_label` 中给目标 span **追加终止 eos 并纳入监督** (仍打 PATCH 标记), 单测同步扩展。修复后编辑模型在 gold 边界 p(eos) = 0.72–0.96, 三查 (a) 通过。另两轮重跑是把 check(a) 的"未编辑基线"参照修到有意义的口径: Llama-3.1-Instruct 的 eos 是 `<|eot_id|>`, 只在 chat 轮次结束处活跃, 因此参照必须取 chat 模式自然回答的边界 (raw 文本模式下基线也 ~3e-8, 无参照意义); 参照答案取典型 chat 形态 (带句号的一词回答) 后 natural_ref=1.0。

其余异常与修复: pod 系统 Python 受 PEP 668 管控, pod_setup.sh 加 `--break-system-packages` (容器内安全); `~/.hf_env` 首版变量未 export 导致 HF_TOKEN 传不进子进程, 已修; pod 只持有 HF_TOKEN 一枚凭证 (handbook v1.1 §1), 付费 key 未上 pod。

## 观察 (非阻塞)

编辑后的模型对自由提问 ("Where is the fictional city Zarithon located?") 回答 "I'm not aware…" 而非给出内化答案。这是预期行为: G0 只验证写入与 gate, 探针 → key prompt 的读取路径 (planner + 参数化引出) 是 P2 的读侧工作; 生成以正常长度终止 (无失控、无 cap-hit) 恰是补丁生效的表现。

## 下一步

P1 (Mac 侧工作负载) 全量生成正在进行 (6 用户 × 24 会话, GLM-5.3); 完成后冻结 dev/test 并出 P1 报告, 然后停等 JQ 抽查 10 条样本。P2 (mini-matrix) 在 G1 + JQ 放行后启动。

## 待 JQ 决策清单

1. **Persona 播种源偏离** (详见 P1 报告): proposal §5.2 写"belief ← PersonaChat 播种", 当前实现为 GEN 模型自生成虚构 persona (规避 license 核实成本与时间)。dev/test 切分仍满足 persona 不相交。是否要求换回真实 PersonaChat 播种, 请裁决; 不裁则按自生成执行。
2. **DeepSeek 余额** (沿上次裁决执行中): P0 未消耗付费 API; 后续 judge 启用前会在报告里持续报余额水位, P3 前再议充值。
