#!/usr/bin/env python3
"""P3 planner: generate probe questions for free_scenario tasks via GLM.

Phase 1 (--dev): tune on the dev split's scenarios; report parse rate, probe
count distribution, and target-free lint vs each scenario's bundled memories.
Phase 2 (--test): with the prompt FROZEN, generate probes for all test
scenarios, lint + one repair round, write data/p3/planner_probes_test_v1.json.

The planner sees ONLY the task text (never answers); the lint enforces the
"no candidate answer words" rule mechanically.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.llm import client  # noqa: E402
from src.workload.generator import _STOPWORDS  # noqa: E402

PROMPT_PATH = Path("prompts/planner_v1.md")
OUT = Path("data/p3")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def word_hit(keyword: str, text: str) -> bool:
    a = _norm(text)
    k = _norm(keyword)
    if " " in k:
        return k in a
    return re.search(rf"\b{re.escape(k)}\b", a) is not None


def keywords_of(mem: dict) -> list[str]:
    return [k for p in mem.get("probes", []) for k in p.get("answer_keywords", [])]


def gen_probes(scenario: dict, mems_by_id: dict, prompt: str) -> tuple[list[str], list[str]]:
    """Returns (probes, leaks). One regeneration attempt on leak."""
    task = scenario["text"]
    leaks_for: list[str] = []

    def call() -> list[str]:
        raw = client.chat([{"role": "user", "content": prompt.replace("{task}", task)}],
                          role="sys", temperature=0.3, max_tokens=2048,
                          meta={"step": "planner", "scenario": scenario["id"]})
        probes = client.parse_json_block(raw).get("probes", [])
        return [p.strip() for p in probes if isinstance(p, str) and 8 <= len(p.strip())]

    def find_leaks(probes: list[str]) -> list[str]:
        leaks = []
        for mid in scenario["memory_ids"]:
            for kw in keywords_of(mems_by_id.get(mid, {})):
                for p in probes:
                    if word_hit(kw, p):
                        leaks.append(f"{mid}:{kw}")
        return sorted(set(leaks))

    probes = call()
    leaks_for = find_leaks(probes)
    if leaks_for:
        probes = call()  # one regeneration attempt
        leaks_for = find_leaks(probes)
    return probes, leaks_for


def run(split: str, doc: dict) -> dict:
    prompt = PROMPT_PATH.read_text()
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    mems_by_id = {m["id"]: m for u in doc["users"] for m in u["memories"]}
    out: dict[str, list[str]] = {}
    stats = Counter()
    leaks_all: dict[str, list[str]] = {}
    for u in doc["users"]:
        for sc in u["scenarios"]:
            probes, leaks = gen_probes(sc, mems_by_id, prompt)
            if not (2 <= len(probes) <= 4):
                stats["bad_probe_count"] += 1
            if leaks:
                stats["scenarios_with_leaks"] += 1
                leaks_all[sc["id"]] = leaks
            stats["scenarios"] += 1
            stats["probes"] += len(probes)
            out[sc["id"]] = probes
    return {"prompt_hash": prompt_hash, "probes": out, "stats": dict(stats),
            "leaks": leaks_all}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", action="store_true")
    ap.add_argument("--test", action="store_true")
    args = ap.parse_args()
    if not (args.dev or args.test):
        ap.error("choose --dev or --test")
    OUT.mkdir(parents=True, exist_ok=True)
    client.set_usage_journal(Path("results/workload_build/llm_usage.jsonl"))

    split = "dev" if args.dev else "test"
    doc = json.loads(Path(f"data/workloads/{split}_v1.1.json").read_text())
    res = run(split, doc)
    stats = res["stats"]
    n = stats.get("scenarios", 0)
    print(json.dumps({
        "split": split, "prompt_hash": res["prompt_hash"],
        "scenarios": n, "probes_total": stats.get("probes", 0),
        "avg_probes": round(stats.get("probes", 0) / n, 2) if n else 0,
        "bad_probe_count": stats.get("bad_probe_count", 0),
        "scenarios_with_leaks": stats.get("scenarios_with_leaks", 0),
        "leaks": res["leaks"],
    }, indent=1, ensure_ascii=False))
    if args.test:
        path = OUT / "planner_probes_test_v1.json"
        path.write_text(json.dumps(res, indent=1, ensure_ascii=False))
        print(f"written {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
