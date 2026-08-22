#!/usr/bin/env python3
"""P3 preparation (MAC only): S5 routing for ALL test memories, S3 random
routing, and the frozen-artifact manifest (prompt + scaffold hashes) that the
P3 test run must execute against (contamination discipline).
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.llm import client  # noqa: E402

OUT = Path("data/p3")
ROUTER_PROMPT = Path("prompts/router_v1.md")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    doc = json.loads(Path("data/workloads/test_v1.1.json").read_text())
    router_prompt = ROUTER_PROMPT.read_text()

    # --- S5: LLM routing over every test memory --------------------------------
    client.set_usage_journal(Path("results/workload_build/llm_usage.jsonl"))
    routing: dict[str, str] = {}
    agree = 0
    for u in doc["users"]:
        for m in u["memories"]:
            raw = client.chat(
                [{"role": "user", "content": router_prompt.replace("{memory}", m["canonical"])}],
                role="sys", temperature=0.0, max_tokens=2048,
                meta={"step": "router_s5_test", "memory": m["id"]})
            t = client.parse_json_block(raw).get("type")
            assert t in ("belief", "fact", "transient"), f"bad router output {m['id']}: {t!r}"
            routing[m["id"]] = t
            agree += int(t == m["type"])
    (OUT / "router_s5_test_v1.json").write_text(json.dumps({
        "prompt": "prompts/router_v1.md", "prompt_hash": sha(ROUTER_PROMPT),
        "model": client.resolve_role("sys", client.load_env())["model"],
        "hidden_label_agreement": f"{agree}/{len(routing)}",
        "routing": routing}, indent=1, ensure_ascii=False))
    print(f"S5 test routing: agreement {agree}/{len(routing)}")

    # --- S3: random placement policy (uniform over edit/rag/drop), seed 42 ------
    s3: dict[str, str] = {}
    for u in doc["users"]:
        rng = random.Random(42 + int(u["user_id"][1:]))
        for m in u["memories"]:
            s3[m["id"]] = rng.choice(["edit", "rag", "drop"])
    (OUT / "router_s3_v1.json").write_text(json.dumps({
        "policy": "uniform_random(edit,rag,drop)", "seed": 42,
        "routing": s3}, indent=1, ensure_ascii=False))
    counts = {}
    for v in s3.values():
        counts[v] = counts.get(v, 0) + 1
    print(f"S3 random routing: {counts}")

    # --- frozen-artifact manifest for the P3 test run ---------------------------
    freeze = {
        "scoring": {"path": "configs/scoring_v1.yaml", "hash": sha(Path("configs/scoring_v1.yaml"))},
        "pressure": {"path": "configs/pressure_v2.yaml", "hash": sha(Path("configs/pressure_v2.yaml"))},
        "gate_config": {"path": "configs/default.yaml", "hash": sha(Path("configs/default.yaml"))},
        "planner_prompt": {"path": "prompts/planner_v1.md", "hash": sha(Path("prompts/planner_v1.md"))},
        "compose_scaffold": {"path": "src/readpath/prompting.py", "hash": sha(Path("src/readpath/prompting.py"))},
        "judge_prompt": {"path": "prompts/judge_v1.md", "hash": sha(Path("prompts/judge_v1.md"))},
        "router_prompt": {"path": "prompts/router_v1.md", "hash": sha(ROUTER_PROMPT)},
        "planner_probes": {"path": "data/p3/planner_probes_test_v1.json",
                           "hash": sha(OUT / "planner_probes_test_v1.json")},
        "s5_routing": {"path": "data/p3/router_s5_test_v1.json", "hash": sha(OUT / "router_s5_test_v1.json")},
        "s3_routing": {"path": "data/p3/router_s3_v1.json", "hash": sha(OUT / "router_s3_v1.json")},
        "workload": {"path": "data/workloads/test_v1.1.json", "hash": sha(Path("data/workloads/test_v1.1.json"))},
        "seed": 42,
    }
    (OUT / "freeze_v1.json").write_text(json.dumps(freeze, indent=1, ensure_ascii=False))
    print(f"frozen artifacts manifest written ({len(freeze)} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
