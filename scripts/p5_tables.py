#!/usr/bin/env python3
"""P5 tables (JQ ruling 2026-08-22): generate the frozen deliverable tables
from results/p3_scorecard.json + the pressure-off ablation, and freeze the
summary-level scorecard to data/p5/frozen_scorecard_v1.json (git-tracked,
allowed by handbook v1.1). Raw journals stay out of git.

usage: python scripts/p5_tables.py   (after syncing p3off_* runs)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.evalx import scorecard  # noqa: E402


def load_off_items():
    arms: dict[str, list[dict]] = {}
    for d in Path("results").glob("p3off_*"):
        f = d / "items.jsonl"
        if not f.exists():
            continue
        arm = d.name.split("_")[1]
        for l in f.read_text().splitlines():
            if l.strip():
                r = json.loads(l)
                if r.get("arm") == arm:
                    arms.setdefault(arm, []).append(r)
    return arms


def main() -> int:
    sc = json.loads(Path("results/p3_scorecard.json").read_text())
    matrix = scorecard.load_matrix()

    # ---- pressure-off aggregation ------------------------------------------------
    off = load_off_items()
    off_summary = {}
    for arm, items in off.items():
        m_items = [dict(i, memory_type=i["memory_type"]) for i in items if i["kind"] != "unrelated"]
        agg = scorecard.aggregate(m_items, matrix)
        fm: dict[str, dict[str, dict]] = {}
        for i in m_items:
            if i["kind"] in ("qa_immediate", "qa_delayed", "qa_paraphrase", "free_scenario"):
                k = fm.setdefault(i["memory_type"], {}).setdefault(i.get("route", "?"),
                                                                   {"n": 0, "hit": 0})
                k["n"] += 1
                k["hit"] += int(any(scorecard._word_hit(kw, i["answer"])
                                    for kw in i["answer_keywords"]))
        off_summary[arm] = {
            "composite": agg["composite"], "axes": agg["per_axis"],
            "failure_matrix": {t: {r: round(v["hit"] / v["n"], 3) for r, v in rs.items()}
                               for t, rs in fm.items()},
            "evicted_recall": None, "n_items": len(items),
        }

    main_ = sc["main"]
    drift = sc.get("drift_bound", {})
    mis = json.loads(Path("results/analysis/s5_misroutes.json").read_text())
    attr = json.loads(Path("results/analysis/gate_attribution.json").read_text())
    attr_s2 = json.loads(Path("results/analysis/gate_attribution_s2.json").read_text())
    seq = json.loads(Path("results/seqcheck_summary.json").read_text())
    gate_sweep = json.loads(Path("results/gate_sweep/report.json").read_text())
    s7dec = json.loads(Path("results/analysis/s7_decomposition.json").read_text())
    judge_means = {"S1": 0.76, "S2": 0.59, "S3": 0.89, "S4": 0.91, "S5": 0.68,
                   "S6": 0.83, "S7": 0.72}  # from p3_judge runs (frozen prompt hash bec5d95094013fd5)
    L: list[str] = []
    L.append("# P5 冻结表 v1.0\n")
    L.append("生成: 2026-08-22 · 计分口径 configs/scoring_v1.yaml (冻结) · gate 0.90 (冻结) · "
             "压力 v2.1 (冻结) · judge prompt bec5d95094013fd5 (冻结)。数字三位小数。\n")

    # ---- main table ---------------------------------------------------------------
    L.append("## 表 1 · 七臂主表 (test 全量, N=210 记忆 / 740 探针)\n")
    L.append("| 臂 | composite | CI95 (bootstrap) | recall | freshness | locality | unrelated* | judge 自然度 (与使用率成对†) | cap-hit | 中位长度 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    usage_rate = {"S1": "0.15/0.19", "S2": "0.00/0.10", "S3": "0.07/0.16", "S4": "0.07/0.23",
                  "S5": "0.07/0.16", "S6": "—", "S7": "—"}
    arm_desc = {"S1": "all-RAG", "S2": "all-edit", "S3": "random", "S4": "oracle",
                "S5": "LLM router", "S6": "utility router (prelim)", "S7": "dual-write (追加臂)"}
    for arm in ("S1", "S2", "S3", "S4", "S5", "S6", "S7"):
        v = main_[arm]
        L.append(f"| {arm} {arm_desc[arm]} | {v['composite']} | {v['composite_ci95']} | "
                 f"{v['axes']['recall']['score']} | {v['axes']['freshness']['score']} | "
                 f"{v['axes']['locality']['score']} | {v['unrelated_hit']} | "
                 f"{judge_means[arm]} ({usage_rate[arm]}) | {v['cap_hit_rate']} | {v['median_len']} |")
    L.append("\n* unrelated 15 题池 (dev 校准用); 顺序一致性确认行用 75 题高分辨率池, 见表 6。"
             "两口径调和: 小池选自 dev 校准、大池为顺序检查点复测, 基座在小池 1.000 / 大池 0.973。\n")
    L.append("† 场景使用率 = belief/fact 场景 keyword 命中 (per_cell beliefxfree_scenario / factxfree_scenario)。"
             "S3 的 0.89 为低使用率下的空洞流畅。\n")
    per_user_rows = []
    for arm in ("S1", "S2", "S3", "S4", "S5", "S6", "S7"):
        pu = main_[arm].get("composite_per_user", {})
        per_user_rows.append(f"| {arm} | " + " | ".join(str(pu.get(u, "—")) for u in ("u03", "u04", "u05", "u06")) + " |")
    L.append("### 分用户 composite\n")
    L.append("| 臂 | u03 | u04 | u05 | u06 |")
    L.append("|---|---|---|---|---|")
    L.extend(per_user_rows)
    L.append("")

    # ---- failure matrix -----------------------------------------------------------
    L.append("## 表 2 · type × store 失败矩阵 (QA+场景召回)\n")
    L.append("| type \\ route | rag | edit | drop | both (S7) |")
    L.append("|---|---|---|---|---|")
    routes_cells = {"rag": [], "edit": [], "drop": [], "both": []}
    for arm in ("S1", "S2", "S3", "S4", "S5", "S7"):
        fm = main_[arm]["failure_matrix"]
        for t, rs in fm.items():
            for r, v in rs.items():
                routes_cells.setdefault(r, []).append((arm, t, v["recall"], v["n"]))
    for t in ("belief", "fact", "transient"):
        row = [t]
        for r in ("rag", "edit", "drop", "both"):
            vals = [f"{rec:.3f}({n}) [{arm}]" for arm, tt, rec, n in routes_cells[r] if tt == t]
            row.append("<br>".join(vals) if vals else "—")
        L.append("| " + " | ".join(row) + " |")
    L.append("")

    # ---- supersede attribution ------------------------------------------------
    L.append("## 表 3 · supersede_new=0.13 归因 (S2, n=23, gate-only 重放)\n")
    cls = attr_s2["supersede_summary"]["classes"]
    L.append(f"| 命中旧 slot | 命中新 slot | 其他行 | 未命中 |")
    L.append(f"| {cls.get('old_slot',0)} | {cls.get('new_slot',0)} | {cls.get('other_row',0)} | {cls.get('no_hit',0)} |")
    L.append("\n口径: 同主体连续更新的键竞争 (key-value 存储一般现象, 非编辑后端缺陷); "
             "五臂共享同一 dedup/supersede 生命周期, 仅放置决策不同。\n")

    # ---- misroutes -----------------------------------------------------------
    L.append("## 表 4 · S5 错路由混淆矩阵 (N=210)\n")
    conf = mis["confusion"]
    L.append("| hidden \\ pred | belief | fact | transient |")
    L.append("|---|---|---|---|")
    for t in ("belief", "fact", "transient"):
        L.append(f"| {t} | {conf[t]['belief']} | {conf[t]['fact']} | {conf[t]['transient']} |")
    L.append(f"\n单方向口径: 全部 {mis['n_misroutes']} 条为 fact→belief——\"带具体指称的偏好类条目被过度内化\""
             "(favorite-X 表面形态与信念判据重叠, 见 docs/workload_spec_v1.0.md 分类规则边界); "
             "误路由条目 QA 召回均值 0.272。\n")

    # ---- seqcheck -----------------------------------------------------------
    L.append("## 表 5 · 顺序一致性确认行 (75 题冻结池 v1, gate 0.90, 不并入综合分)\n")
    L.append("| 臂×用户 | ck10 | ck25 | 流末 (编辑数) |")
    L.append("|---|---|---|---|")
    for k in sorted(seq["results"]):
        if k == "BASE":
            continue
        v = seq["results"][k]
        cells = []
        for ck, val in v["checkpoints"].items():
            cells.append(f"{val} ({ck.split('_')[0]})")
        L.append(f"| {k} | " + " | ".join(cells) + " |")
    L.append(f"| BASE 抽查 | {seq['results']['BASE']['hit_rate']} (n={seq['results']['BASE']['n']}) | | |")
    L.append("\n定位: 与 HoReN 已发表顺序稳定性一致的复现确认; 不做门槛对比。S5 各用户编辑数 16–22, "
             "ck25 不可达 (检查点取实际最大并披露为流末)。\n")

    # ---- gate sensitivity (appendix) ----------------------------------------
    L.append("## 附录 A · gate 敏感性 (dev 单次扫描, 校准存档)\n")
    L.append("| 阈值 | 0.75 | 0.80 | 0.85 | 0.90 |")
    L.append("|---|---|---|---|---|")
    L.append("| own-key 命中 | " + " | ".join(f"{gate_sweep['thresholds'][str(t)]['own_hit']:.3f}" if str(t) in gate_sweep['thresholds'] else f"{gate_sweep['thresholds'][t]['own_hit']:.3f}" for t in (0.75, 0.8, 0.85, 0.9)) + " |")
    L.append("| unrelated 误触发 | " + " | ".join(f"{gate_sweep['thresholds'][str(t)]['false_fire']:.3f}" if str(t) in gate_sweep['thresholds'] else f"{gate_sweep['thresholds'][t]['false_fire']:.3f}" for t in (0.75, 0.8, 0.85, 0.9)) + " |")
    L.append("\n预注册规则选定 0.90; 本表仅作校准存档, 不进正文叙事。\n")

    # ---- drift + pressure-off ------------------------------------------------
    L.append("## 表 6 · 漂移界与 pressure-off 消融 (P5 既定项)\n")
    L.append(f"| S5 同配置重跑 | run1 {drift.get('S5_run1')} → run2 {drift.get('S5_run2')} | |Δ|={drift.get('abs_diff')} |")
    L.append("\n| 臂 (pressure-off) | composite | recall | freshness | locality | fact×rag | fact×edit |")
    L.append("|---|---|---|---|---|---|---|")
    for arm, v in sorted(off_summary.items()):
        fm = v["failure_matrix"].get("fact", {})
        L.append(f"| {arm} (预算/驱逐关, 无 distractor) | {v['composite']} | "
                 f"{v['axes']['recall']['score']} | {v['axes']['freshness']['score']} | "
                 f"{v['axes']['locality']['score']} | {fm.get('rag', '—')} | {fm.get('edit', '—')} |")
    L.append("\n口径: pressure-off 为 P5 预注册既定项 (计划落盘先于运行); 其余冻结配置不动。"
             "与压力行对照给出\"内化在预算压力下产生收益\"条件句的边界。\n")

    # ---- S7 decomposition ------------------------------------------------
    L.append("## 表 7 · S7 双写亏损分解 (journal 级, 零 GPU)\n")
    c1 = s7dec["component1_conflict_pollution"]
    c2 = s7dec["component2_capacity"]
    L.append(f"| 冲突行 QA (n={c1['S7_conflict_rows_qa']['n']}) | 非冲突行 QA (n={c1['S7_plain_rows_qa']['n']}) | S2 参考 | S1 参考 |")
    L.append(f"| {c1['S7_conflict_rows_qa']['score']} | {c1['S7_plain_rows_qa']['score']} | {c1['reference_S2_qa']['score']} | {c1['reference_S1_qa']['score']} |")
    L.append(f"\n容量: S7 journal 终行数 {c2['S7']['final_codebook_rows_range']} 与解析期望逐用户一致 "
             f"({c2['rows_match_expectation']}); 编辑成本 {c2['S7']['n_edits_total']} 次 / "
             f"{c2['S7']['total_edit_seconds']}s; near-miss locality S7 0.111 vs S2 0.472 (同 codebook 行数)。"
             "journal 残片披露: " + c2["journal_fragment_disclosed"][:120] + "…\n")

    out_md = Path("docs/tables_p5_v1.0.md")
    out_md.write_text("\n".join(L), encoding="utf-8")
    print(f"written {out_md}")

    # ---- frozen summary scorecard (git-tracked) --------------------------
    frozen = {
        "meta": {"frozen": "2026-08-22", "scoring": "configs/scoring_v1.yaml",
                 "gate": 0.90, "pressure": "configs/pressure_v2.yaml",
                 "judge_prompt": "bec5d95094013fd5",
                 "seed": 42, "backbone": "meta-llama/Llama-3.1-8B-Instruct",
                 "models": {"gen": "glm-5.3", "sys": "glm-5.3", "judge": "deepseek-v4-pro"}},
        "arms": {a: {"composite": v["composite"], "ci95": v["composite_ci95"],
                     "axes": {k: vv["score"] for k, vv in v["axes"].items()},
                     "judge": judge_means[a], "unrelated": v["unrelated_hit"],
                     "per_user": v.get("composite_per_user")}
                 for a, v in main_.items()},
        "drift_bound": drift,
        "pressure_off": off_summary,
        "seqcheck": {k: v for k, v in seq["results"].items()},
        "supersede_attribution": attr_s2["supersede_summary"],
        "misroutes": {"confusion": mis["confusion"], "n": mis["n_misroutes"]},
        "s7_decomposition": {"conflict_qa": c1["S7_conflict_rows_qa"],
                             "plain_qa": c1["S7_plain_rows_qa"],
                             "rows_match": c2["rows_match_expectation"]},
        "gate_sweep": gate_sweep["thresholds"],
    }
    dest = Path("data/p5")
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "frozen_scorecard_v1.json").write_text(json.dumps(frozen, indent=1, ensure_ascii=False))
    print("written data/p5/frozen_scorecard_v1.json (git-tracked summary)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
