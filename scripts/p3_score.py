#!/usr/bin/env python3
"""P3 scoring (MAC only): aggregate synced p3_<arm>_<user> items through the
frozen matrix; five-arm comparison, type x route failure matrix, S5-vs-S4
flag (JQ: if S5>S4 replicates on N=210, flag it), and the S5 drift bound vs
the same-config rerun (p3drift_*).
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.evalx import scorecard  # noqa: E402


def load(root: Path, prefix: str) -> dict[str, list[dict]]:
    arms: dict[str, list[dict]] = defaultdict(list)
    for d in sorted(root.glob(f"{prefix}_*")):
        f = d / "items.jsonl"
        if not f.exists():
            continue
        parts = d.name[len(prefix) + 1:].split("_")  # <ARM>_<user>
        if len(parts) != 2:
            continue
        arm = parts[0]
        for l in f.read_text().splitlines():
            if l.strip():
                r = json.loads(l)
                if r.get("arm") == arm:
                    arms[arm].append(r)
    return dict(arms)


def hit_rate(items, kind):
    sel = [i for i in items if i["kind"] == kind]
    if not sel:
        return None
    hits = sum(1 for i in sel if any(scorecard._word_hit(k, i.get("answer", ""))
                                     for k in i.get("answer_keywords", [])))
    return round(hits / len(sel), 3)


def bootstrap_ci(items, matrix, n_draws: int = 1000, seed: int = 42):
    """Probe-level bootstrap: resample each axis's item scores independently,
    recompute the composite, report the 2.5/97.5 percentiles."""
    import random as _random
    rng = _random.Random(seed)
    buckets: dict[str, list[float]] = {"recall": [], "freshness": [], "locality": []}
    for i in items:
        cell = matrix[i["memory_type"]][i["kind"]]
        if cell["axis"] in buckets and cell["in_composite"]:
            buckets[cell["axis"]].append(scorecard.score_item(dict(i), matrix))
    composites = []
    for _ in range(n_draws):
        axis_means = []
        for ax, scores in buckets.items():
            if scores:
                draw = [scores[rng.randrange(len(scores))] for _ in scores]
                axis_means.append(sum(draw) / len(draw))
        if axis_means:
            composites.append(sum(axis_means) / len(axis_means))
    if not composites:
        return None
    composites.sort()
    lo = composites[int(0.025 * len(composites))]
    hi = composites[min(int(0.975 * len(composites)), len(composites) - 1)]
    return [round(lo, 3), round(hi, 3)]


def summarize(arms: dict[str, list[dict]], matrix) -> dict:
    out: dict = {}
    for arm, items in arms.items():
        m_items = [i for i in items if i["kind"] != "unrelated"]
        agg = scorecard.aggregate([dict(i, memory_type=i["memory_type"]) for i in m_items], matrix)
        # statistical reinforcement (JQ ruling): probe-level bootstrap CI +
        # per-user composite split
        ci = bootstrap_ci([dict(i, memory_type=i["memory_type"]) for i in m_items], matrix)
        per_user = {}
        for uid in sorted({i.get("user_id") for i in m_items if i.get("user_id")}):
            u_items = [dict(i, memory_type=i["memory_type"]) for i in m_items
                       if i.get("user_id") == uid]
            u_agg = scorecard.aggregate(u_items, matrix)
            per_user[uid] = u_agg["composite"]
        # failure matrix: recall per (memory_type x route), the paper's core table
        fm: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {"n": 0, "hit": 0}))
        for i in m_items:
            if i["kind"] in ("qa_immediate", "qa_delayed", "qa_paraphrase", "free_scenario"):
                k = fm[i["memory_type"]][i.get("route", "?")]
                k["n"] += 1
                k["hit"] += int(any(scorecard._word_hit(kw, i["answer"])
                                    for kw in i["answer_keywords"]))
        out[arm] = {
            "items": len(items), "axes": agg["per_axis"], "composite": agg["composite"],
            "composite_ci95": ci, "composite_per_user": per_user,
            "per_cell": agg["per_cell"], "old_value_residual": scorecard.old_value_residual(m_items),
            "session_scoped": agg["session_scoped"],
            "unrelated_hit": hit_rate(items, "unrelated"),
            "failure_matrix": {t: {r: {"n": v["n"], "recall": round(v["hit"] / v["n"], 3)}
                                   for r, v in rs.items()} for t, rs in fm.items()},
            "cap_hit_rate": round(sum(1 for i in items if i.get("cap_hit")) / len(items), 3),
            "median_len": sorted(i.get("n_gen", 0) for i in items)[len(items) // 2],
            "scenario_gate_fires": sum(i.get("gate_fires", 0) for i in m_items
                                       if i["kind"] == "free_scenario"),
            "scenario_notes": sum(i.get("n_notes", 0) for i in m_items
                                  if i["kind"] == "free_scenario"),
        }
    return out


def main() -> int:
    root = Path("results")
    matrix = scorecard.load_matrix()
    main_arms = load(root, "p3")
    drift_arms = load(root, "p3drift")
    report = {"main": summarize(main_arms, matrix)}
    if "S5" in report["main"] and "S4" in report["main"]:
        s5 = report["main"]["S5"]["composite"]
        s4 = report["main"]["S4"]["composite"]
        report["s5_vs_s4"] = {"S5": s5, "S4": s4,
                              "s5_exceeds_oracle": s5 is not None and s4 is not None and s5 > s4,
                              "flag": "S5>S4 REPLICATED on N=210 — discussion-worthy result (JQ ruling)"
                                      if (s5 or 0) > (s4 or 0) else "not replicated"}
    if drift_arms:
        report["drift_rerun"] = summarize(drift_arms, matrix)
        if "S5" in report["main"] and "S5" in report["drift_rerun"]:
            c1 = report["main"]["S5"]["composite"]
            c2 = report["drift_rerun"]["S5"]["composite"]
            report["drift_bound"] = {"S5_run1": c1, "S5_run2": c2,
                                     "abs_diff": round(abs((c1 or 0) - (c2 or 0)), 3)}
    print(json.dumps(report, indent=1, ensure_ascii=False))
    Path("results/p3_scorecard.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print("written results/p3_scorecard.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
