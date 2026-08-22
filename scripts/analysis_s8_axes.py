#!/usr/bin/env python3
"""Zero-GPU S8 axis decomposition (JQ 2026-08-22).

Pressure on: S4 / S5 / S8 journals (p3_*).
Pressure off: S5 / S8 (p3off_*). S4-off was never run — cell is not_run.

Five columns = composite + recall + freshness + locality + unrelated
(frozen scoring_v1.yaml composite axes plus the unrelated pool).
Belief×supersede and belief×near-miss are inventoried from the frozen
workload; n=0 cells are reported empty (workload spec: pairs mostly fact).

Does not write data/p5/frozen_scorecard_v1.json.
"""
from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.evalx import scorecard  # noqa: E402
from scripts.p3_score import bootstrap_ci, hit_rate, load  # noqa: E402

_ROOT = Path(__file__).resolve().parents[1]
OUT = _ROOT / "data" / "p5" / "s8_axis_decomp_frozen_v1.json"
RESULTS = _ROOT / "results"
WORKLOAD = _ROOT / "data" / "workloads" / "test_v1.1.json"
S8_FREEZE = _ROOT / "data" / "p5" / "s8_frozen_v1.json"

AXES = ("recall", "freshness", "locality")
CELLS = (
    "beliefxsupersede_old",
    "beliefxsupersede_new",
    "beliefxnear_miss",
    "factxsupersede_old",
    "factxsupersede_new",
    "factxnear_miss",
)


def workload_inventory(doc: dict) -> dict:
    c: Counter = Counter()
    for u in doc["users"]:
        for m in u["memories"]:
            for p in m["probes"]:
                if p["kind"] in ("near_miss", "supersede_old", "supersede_new"):
                    c[f"{m['type']}x{p['kind']}"] += 1
    return {k: int(c.get(k, 0)) for k in CELLS}


def bootstrap_axes(items: list[dict], matrix: dict, n_draws: int = 1000,
                   seed: int = 42) -> dict:
    rng = random.Random(seed)
    buckets: dict[str, list[float]] = {ax: [] for ax in AXES}
    scored = []
    for i in items:
        if i.get("kind") == "unrelated" or i.get("memory_type") not in ("belief", "fact", "transient"):
            continue
        cell = matrix[i["memory_type"]][i["kind"]]
        if cell["axis"] in buckets and cell["in_composite"]:
            s = scorecard.score_item(dict(i), matrix)
            buckets[cell["axis"]].append(s)
            scored.append(i)
    out: dict = {}
    for ax, scores in buckets.items():
        if not scores:
            out[ax] = None
            continue
        means = []
        for _ in range(n_draws):
            draw = [scores[rng.randrange(len(scores))] for _ in scores]
            means.append(sum(draw) / len(draw))
        means.sort()
        out[ax] = [round(means[int(0.025 * len(means))], 3),
                   round(means[min(int(0.975 * len(means)), len(means) - 1)], 3)]
    return out


def summarize_arm(items: list[dict], matrix: dict) -> dict:
    m_items = [i for i in items if i.get("kind") != "unrelated"
               and i.get("memory_type") in ("belief", "fact", "transient")]
    agg = scorecard.aggregate([dict(i) for i in m_items], matrix)
    ci = bootstrap_ci([dict(i) for i in m_items], matrix)
    axis_ci = bootstrap_axes(m_items, matrix)
    cells = {}
    for key in CELLS:
        v = agg["per_cell"].get(key)
        cells[key] = v if v else {"n": 0, "score": None}
    axes = {ax: agg["per_axis"][ax]["score"] for ax in AXES}
    return {
        "n_items": len(items),
        "composite": agg["composite"],
        "ci95": ci,
        "axes": axes,
        "axis_ci95": axis_ci,
        "unrelated": hit_rate(items, "unrelated"),
        "session_scoped": agg["session_scoped"],
        "cells": cells,
    }


def main() -> int:
    matrix = scorecard.load_matrix()
    inv = workload_inventory(json.loads(WORKLOAD.read_text()))
    on = load(RESULTS, "p3")
    off = load(RESULTS, "p3off")
    rows = {}
    for arm in ("S4", "S5", "S8"):
        rows[arm] = {}
        if arm in on:
            rows[arm]["on"] = summarize_arm(on[arm], matrix)
        else:
            rows[arm]["on"] = {"status": "not_run"}
        if arm in off:
            rows[arm]["off"] = summarize_arm(off[arm], matrix)
        else:
            rows[arm]["off"] = {"status": "not_run"}

    # checksum against the appended S8 freeze (composite axes only)
    s8f = json.loads(S8_FREEZE.read_text())
    s8_on = rows["S8"]["on"]
    checks = {
        "s8_on_composite": s8_on["composite"] == round(s8f["on"]["composite"], 3),
        "s8_on_recall": s8_on["axes"]["recall"] == round(s8f["on"]["axes"]["recall"], 3),
        "s8_on_freshness": s8_on["axes"]["freshness"] == round(s8f["on"]["axes"]["freshness"], 3),
        "s8_on_locality": s8_on["axes"]["locality"] == round(s8f["on"]["axes"]["locality"], 3),
    }

    payload = {
        "disclosure": (
            "JQ-authorized appended freeze (2026-08-22): S8 axis decomposition "
            "from existing p3/p3off journals; zero GPU; frozen_scorecard_v1.json "
            "untouched. Belief×supersede and belief×near-miss n=0 in test_v1.1 "
            "(pairs constructed mostly on facts, workload spec)."
        ),
        "workload_inventory": inv,
        "arms": rows,
        "checksum_vs_s8_frozen_v1": checks,
    }
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({"written": str(OUT), "checksum": checks,
                      "inventory": inv,
                      "s4_off": rows["S4"]["off"].get("status", "scored")},
                     indent=2))
    if not all(checks.values()):
        print("WARNING: S8-on axes do not match s8_frozen_v1.json", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
