#!/usr/bin/env python3
"""Judge pass (MAC only, paid API): naturalness of free_scenario completions.
Auxiliary axis (proposal §5.4 recall 辅) — NOT part of the G2 composite.
Post-processes synced items.jsonl in place (adds judge_score), idempotent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.llm import client  # noqa: E402

PROMPT = """Rate how naturally this assistant response weaves in the required personal context (0-2 scale).
2 = naturally integrated, reads like the assistant just knows the user; 1 = present but awkward/mechanical; 0 = missing or contradicts.
Reply with ONLY the number.

Scenario task: {task}
Assistant response: {response}"""


def main() -> int:
    client.set_usage_journal(Path("results/workload_build/llm_usage.jsonl"))
    scored = 0
    for d in sorted(Path("results").glob("p2_*")):
        f = d / "items.jsonl"
        if not f.exists():
            continue
        rows = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
        changed = False
        for r in rows:
            if r.get("kind") != "free_scenario" or r.get("judge_score") is not None:
                continue
            out = client.chat(
                [{"role": "user", "content": PROMPT.replace("{task}", r["question"][:800])
                  .replace("{response}", r["answer"][:1200])}],
                role="judge", temperature=0.0, max_tokens=2048,
                meta={"step": "judge_free_scenario", "arm": r["arm"]})
            try:
                r["judge_score"] = int(str(out).strip()[:1])
            except ValueError:
                r["judge_score"] = None
            changed = True
            scored += 1
        if changed:
            f.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
    print(json.dumps({"scored": scored, "usage": client.usage_summary()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
