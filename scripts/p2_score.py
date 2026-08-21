#!/usr/bin/env python3
"""P2 scoring (MAC only): aggregate synced items.jsonl per arm through the
frozen scoring matrix; evaluate the three preregistered G2 criteria.

usage: python scripts/p2_score.py <results_root>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.evalx import scorecard  # noqa: E402


def load_items(root: Path) -> dict[str, list[dict]]:
    arms: dict[str, list[dict]] = {}
    for d in sorted(root.glob("p2_*")):
        f = d / "items.jsonl"
        if not f.exists():
            continue
        arms[d.name.replace("p2_", "")] = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    return arms


def hit_rate(items: list[dict], kind: str) -> float | None:
    sel = [i for i in items if i["kind"] == kind]
    if not sel:
        return None
    hits = sum(1 for i in sel if any(scorecard._word_hit(k, i.get("answer", ""))
                                     for k in i.get("answer_keywords", [])))
    return round(hits / len(sel), 3)


def near_miss_score(items: list[dict]) -> float | None:
    sel = [i for i in items if i["kind"] == "near_miss"]
    if not sel:
        return None
    return scorecard.aggregate([dict(i, memory_type=i.get("memory_type", "fact"))
                                for i in sel])["per_axis"]["locality"]["score"]


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("results")
    arms = load_items(root)
    if not arms:
        print("no p2_* items found")
        return 1
    matrix = scorecard.load_matrix()
    report: dict = {"arms": {}}
    for arm, items in arms.items():
        # exclude unrelated + BASE rows from matrix aggregation
        m_items = [i for i in items if i["kind"] != "unrelated"]
        agg = scorecard.aggregate([dict(i, memory_type=i["memory_type"]) for i in m_items], matrix)
        unrel = hit_rate(items, "unrelated")
        evicted = [i for i in m_items if i.get("store_evicted")
                   and i["kind"] in ("qa_immediate", "qa_delayed", "qa_paraphrase")]
        live = [i for i in m_items if not i.get("store_evicted") and i.get("write_session") is not None
                and i["kind"] in ("qa_immediate", "qa_delayed", "qa_paraphrase")]
        report["arms"][arm] = {
            "items": len(items),
            "axes": agg["per_axis"], "composite": agg["composite"],
            "session_scoped": agg["session_scoped"],
            "per_cell": agg["per_cell"],
            "old_value_residual": scorecard.old_value_residual(m_items),
            "unrelated_hit": unrel,
            "evicted_recall": (round(sum(1 for i in evicted if any(
                scorecard._word_hit(k, i["answer"]) for k in i["answer_keywords"])) / len(evicted), 3)
                if evicted else None),
            "live_recall": (round(sum(1 for i in live if any(
                scorecard._word_hit(k, i["answer"]) for k in i["answer_keywords"])) / len(live), 3)
                if live else None),
            "cap_hit_rate": round(sum(1 for i in items if i.get("cap_hit")) / len(items), 3),
            "median_len": sorted(i.get("n_gen", 0) for i in items)[len(items) // 2],
        }
    base = arms.get("BASE") or []
    if base:
        report["base_unrelated_hit"] = hit_rate(base, "unrelated")

    # G2 preregistered criteria
    a = report["arms"]
    if all(k in a for k in ("S1", "S2", "S4", "S5")):
        base_un = report.get("base_unrelated_hit") or 0.0
        nm_s1, nm_s2 = near_miss_score(a and arms["S1"]), near_miss_score(arms["S2"])
        drift = {arm: round(base_un - (a[arm]["unrelated_hit"] or 0.0), 3) for arm in a}
        crit = {
            "c1_S2_degrades_locality_S1_not": {
                "S2_unrelated_drift": drift.get("S2"), "S1_unrelated_drift": drift.get("S1"),
                "S2_near_miss": nm_s2, "S1_near_miss": nm_s1,
                "pass": (drift.get("S2", 0) > drift.get("S1", 0)) or ((nm_s2 or 1) < (nm_s1 or 0))},
            "c2_S1_evicted_recall_collapse": {
                "S1_evicted_recall": a["S1"]["evicted_recall"], "S1_live_recall": a["S1"]["live_recall"],
                "S2_recall_proxy": a["S2"]["axes"]["recall"]["score"],
                "pass": (a["S1"]["evicted_recall"] is not None
                         and (a["S1"]["live_recall"] or 0) - a["S1"]["evicted_recall"] >= 0.2)},
            "c3_composite": {
                "S1": a["S1"]["composite"], "S2": a["S2"]["composite"],
                "S4": a["S4"]["composite"], "S5": a["S5"]["composite"],
                "pass": ((a["S5"]["composite"] or 0) >= max(a["S1"]["composite"] or 0,
                                                            a["S2"]["composite"] or 0)
                         and (a["S5"]["composite"] or 0) >= 0.8 * (a["S4"]["composite"] or 0))},
        }
        report["g2_criteria"] = crit
        report["unrelated_drift"] = drift
    print(json.dumps(report, indent=1, ensure_ascii=False))
    out = Path("results/p2_scorecard.json")
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(f"\nwritten {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
