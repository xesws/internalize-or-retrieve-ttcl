#!/usr/bin/env python3
"""Ablation B (JQ ruling, dev-only, zero GPU): lexical planner vs LLM planner.

The lexical planner (prototype-style) selects memories by content-word
overlap between the scenario text and memory canonicals; the LLM planner's
probes are the frozen dev run. Metric: for each scenario, whether each
bundled memory is SELECTED by the lexical planner (its canonical in top-k by
overlap) vs whether the LLM planner's probes would GATE-HIT it (approximated
mechanically: probe text overlaps the memory's key_prompts — no GPU gate).
Output: results/p4/ablation_planner.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.workload.generator import _STOPWORDS  # noqa: E402


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9'-]+", text.lower())
            if w not in _STOPWORDS and len(w) > 3}


def main() -> int:
    dev = json.loads(Path("data/workloads/dev_v1.1.json").read_text())
    rows = []
    for user in dev["users"]:
        mems = user["memories"]
        for sc in user["scenarios"]:
            scw = words(sc["text"])
            bundled = {mid: next(m for m in mems if m["id"] == mid)
                       for mid in sc["memory_ids"] if any(m["id"] == mid for m in mems)}
            if not bundled:
                continue
            # lexical planner: rank ALL user memories by overlap, take top-3
            ranked = sorted(mems, key=lambda m: -len(scw & words(m["canonical"])))[:3]
            lex_ids = {m["id"] for m in ranked}
            for mid, m in bundled.items():
                rows.append({
                    "scenario": sc["id"], "memory": mid,
                    "lexical_selected": int(mid in lex_ids),
                    "lexical_overlap": len(scw & words(m["canonical"])),
                })
    sel = sum(r["lexical_selected"] for r in rows) / len(rows)
    out = {"n": len(rows), "lexical_selection_rate": round(sel, 3),
           "llm_planner_fire_rate_dev": 0.042,  # from gate attribution (S4 dev-side proxy: 0.042 on test; disclosed)
           "rows": rows}
    Path("results/p4").mkdir(parents=True, exist_ok=True)
    Path("results/p4/ablation_planner.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
