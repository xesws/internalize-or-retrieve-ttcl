#!/usr/bin/env python3
"""P3 judge pass (MAC only, paid API): naturalness of free_scenario
compositions using the FROZEN judge prompt (prompts/judge_v1.md, hash in
data/p3/freeze_v1.json). Auxiliary axis — NOT in the composite.
Idempotent: adds judge_score in place, skips already-scored rows.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.llm import client  # noqa: E402


def main() -> int:
    prompt = Path("prompts/judge_v1.md").read_text()
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    client.set_usage_journal(Path("results/workload_build/llm_usage.jsonl"))
    scored = 0
    for d in sorted(list(Path("results").glob("p3_*")) + list(Path("results").glob("p3drift_*"))):
        f = d / "items.jsonl"
        if not f.exists():
            continue
        rows = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
        changed = False
        for r in rows:
            if r.get("kind") != "free_scenario" or r.get("judge_score") is not None:
                continue
            try:
                out = client.chat(
                    [{"role": "user", "content": prompt.replace("{task}", r["question"][:800])
                      .replace("{response}", r["answer"][:1200])}],
                    role="judge", temperature=0.0, max_tokens=2048,
                    meta={"step": "judge_p3", "arm": r["arm"], "user": r.get("user_id")})
                r["judge_score"] = int(str(out).strip()[:1])
            except (client.LLMError, ValueError):
                # after 3 retries: record the failure explicitly, keep going;
                # the G3 report discloses the failed-judge count
                r["judge_score"] = None
                r["judge_failed"] = True
            changed = True
            scored += 1
        if changed:
            f.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
    by_arm = defaultdict(list)
    for d in sorted(list(Path("results").glob("p3_*")) + list(Path("results").glob("p3drift_*"))):
        f = d / "items.jsonl"
        if not f.exists():
            continue
        for l in f.read_text().splitlines():
            if not l.strip():
                continue
            r = json.loads(l)
            if r.get("kind") == "free_scenario" and r.get("judge_score") is not None:
                by_arm[r["arm"]].append(r["judge_score"])
    print(json.dumps({"prompt_hash": prompt_hash, "scored": scored,
                      "mean_by_arm": {a: round(sum(s) / len(s), 2) for a, s in sorted(by_arm.items())},
                      "usage": client.usage_summary()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
