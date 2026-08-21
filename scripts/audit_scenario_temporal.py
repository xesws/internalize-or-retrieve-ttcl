#!/usr/bin/env python3
"""Prerequisite 2 (JQ ruling 2026-08-21): audit free_scenario x supersede
temporal consistency across BOTH frozen splits, then rewrite violating
expect-words to the chain's final value and re-freeze as v1.1.

Rule: free_scenario probes evaluate at END OF STREAM, so a scenario bundling
an old (superseded) memory must expect the chain's FINAL (new) value's
keywords. Only answer_keywords change; scenario text is never touched
(target-free by construction, so it carries no temporal anchor).

usage:
  python scripts/audit_scenario_temporal.py --check     # audit only
  python scripts/audit_scenario_temporal.py --fix       # fix + re-freeze v1.1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.workload.generator import answer_keywords  # noqa: E402

WL = Path("data/workloads")


def chains(users: list[dict]) -> dict[str, dict]:
    """old_id -> {new_id, old_target, new_target, new_keywords}."""
    by_id = {m["id"]: m for u in users for m in u["memories"]}
    out: dict[str, dict] = {}
    for m in by_id.values():
        if m.get("supersede_of"):
            old = by_id[m["supersede_of"]]
            out[old["id"]] = {
                "new_id": m["id"],
                "old_target": old["edit_target"],
                "new_target": m["edit_target"],
                "new_keywords": answer_keywords(m["edit_target"]),
            }
    return out


def audit(doc: dict) -> list[dict]:
    ch = chains(doc["users"])
    violations = []
    for u in doc["users"]:
        for sc in u["scenarios"]:
            for mid in sc["memory_ids"]:
                if mid not in ch:
                    continue
                c = ch[mid]
                for m in u["memories"]:
                    if m["id"] != mid:
                        continue
                    for p in m["probes"]:
                        if p.get("kind") == "free_scenario" and p.get("scenario_id") == sc["id"]:
                            if sorted(p["answer_keywords"]) != sorted(c["new_keywords"]):
                                violations.append({
                                    "user": u["user_id"], "scenario": sc["id"],
                                    "memory": mid, "chain_new": c["new_id"],
                                    "old_keywords": p["answer_keywords"],
                                    "expected_now": c["new_keywords"],
                                    "probe": p,
                                })
    return violations


def fix(doc: dict, violations: list[dict]) -> int:
    by_key = {(v["memory"], v["scenario"]): v for v in violations}
    fixed = 0
    for u in doc["users"]:
        for m in u["memories"]:
            for p in m["probes"]:
                if p.get("kind") != "free_scenario" or not p.get("scenario_id"):
                    continue
                v = by_key.get((m["id"], p["scenario_id"]))
                if v:
                    p["answer_keywords"] = list(v["expected_now"])
                    fixed += 1
    return fixed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true")
    args = ap.parse_args()

    report: dict = {"splits": {}, "total_violations": 0}
    for split in ("dev", "test"):
        doc = json.loads((WL / f"{split}_v1.json").read_text())
        v = audit(doc)
        report["splits"][split] = {"scenarios": sum(len(u["scenarios"]) for u in doc["users"]),
                                   "violations": len(v), "details": v}
        report["total_violations"] += len(v)
        if args.fix and v:
            n = fix(doc, v)
            out = WL / f"{split}_v1.1.json"
            doc["version"] = "v1.1"
            out.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
            report["splits"][split]["fixed_probes"] = n
            report["splits"][split]["out_path"] = str(out)

    print(json.dumps({
        "total_violations": report["total_violations"],
        "per_split": {k: {"scenarios": v["scenarios"], "violations": v["violations"],
                          **({"fixed": v.get("fixed_probes")} if args.fix else {})}
                      for k, v in report["splits"].items()},
        "detail": [{k: v for k, v in d.items() if k != "probe"}
                   for s in report["splits"].values() for d in s["details"]],
    }, indent=1, ensure_ascii=False))
    (WL / f"temporal_audit_{ 'v1.1' if args.fix else 'report'}.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
