#!/usr/bin/env python3
"""P2 preparation (MAC only): stratified selection + S5 LLM routing decisions.

Outputs (git-tracked small frozen data):
  data/p2/selection.json     — the N=20 stream (with scenarios)
  data/p2/router_s5_v1.json  — {routing: {memory_id: type}} via SYS=glm-5.3,
                               prompt prompts/router_v1.md (hash recorded)
Routing runs BEFORE any test-set-related evaluation and is frozen with the
prompt hash (contamination discipline, handbook §4.2).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.arms.selection import load_dev, select_p2  # noqa: E402
from src.llm import client  # noqa: E402

OUT = Path("data/p2")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    dev = load_dev()
    sel = select_p2(dev, seed=42)
    (OUT / "selection.json").write_text(json.dumps(sel, indent=1, ensure_ascii=False))
    print(json.dumps({k: v for k, v in sel.items() if k not in ("memories", "scenarios")},
                     indent=1))

    prompt = Path("prompts/router_v1.md").read_text()
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    client.set_usage_journal(Path("results/workload_build/llm_usage.jsonl"))
    routing: dict[str, str] = {}
    agree = 0
    for m in sel["memories"]:
        raw = client.chat([{"role": "user", "content": prompt.replace("{memory}", m["canonical"])}],
                          role="sys", temperature=0.0, max_tokens=2048,
                          meta={"step": "router_s5", "memory": m["id"]})
        t = client.parse_json_block(raw).get("type")
        assert t in ("belief", "fact", "transient"), f"bad router output for {m['id']}: {t!r}"
        routing[m["id"]] = t
        agree += int(t == m["type"])
    doc = {"prompt": "prompts/router_v1.md", "prompt_hash": prompt_hash,
           "model": client.resolve_role("sys", client.load_env())["model"],
           "hidden_label_agreement": f"{agree}/{len(routing)}",
           "routing": routing}
    (OUT / "router_s5_v1.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    print(f"router agreement with hidden labels: {agree}/{len(routing)}")
    print(f"usage so far: {json.dumps(client.usage_summary())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
