#!/usr/bin/env python3
"""Phase A1 (JQ ruling 2026-08-21): S5 misroute analysis from frozen artifacts.

Confusion matrix (hidden label x router prediction) over the 210 test
memories + the itemized misroute list. Pure journal work, no GPU.
Output: results/analysis/s5_misroutes.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUT = Path("results/analysis")


def main() -> int:
    doc = json.loads(Path("data/workloads/test_v1.1.json").read_text())
    routing = json.loads(Path("data/p3/router_s5_test_v1.json").read_text())["routing"]
    mem_by_id = {m["id"]: m for u in doc["users"] for m in u["memories"]}

    types = ["belief", "fact", "transient"]
    matrix = {t: {p: [] for p in types} for t in types}
    for mid, pred in routing.items():
        hidden = mem_by_id[mid]["type"]
        matrix[hidden][pred].append(mid)

    confusion = {t: {p: len(v) for p, v in row.items()} for t, row in matrix.items()}
    misroutes = []
    for t, row in matrix.items():
        for p, ids in row.items():
            if p != t:
                for mid in ids:
                    m = mem_by_id[mid]
                    misroutes.append({
                        "memory": mid, "user": m["user_id"],
                        "canonical": m["canonical"][:110],
                        "hidden": t, "predicted": p,
                    })
    misroutes.sort(key=lambda r: (r["hidden"], r["predicted"], r["memory"]))

    # where do misroutes hurt? join with the failure matrix memory-level rows
    # (route actually taken in S5 = DEST[predicted]) — attach per-memory QA recall
    recall_by_mem = {}
    for d in Path("results").glob("p3_S5_u*"):
        f = d / "items.jsonl"
        if not f.exists():
            continue
        for l in f.read_text().splitlines():
            if not l.strip():
                continue
            r = json.loads(l)
            if r.get("kind") in ("qa_immediate", "qa_delayed", "qa_paraphrase") and r.get("memory_id"):
                hit = any(kw.lower() in r["answer"].lower() for kw in r["answer_keywords"])
                rec = recall_by_mem.setdefault(r["memory_id"], {"n": 0, "hit": 0})
                rec["n"] += 1
                rec["hit"] += int(hit)
    for r in misroutes:
        rec = recall_by_mem.get(r["memory"])
        if rec and rec["n"]:
            r["s5_qa_recall"] = round(rec["hit"] / rec["n"], 2)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "s5_misroutes.json").write_text(json.dumps({
        "confusion": confusion, "n_misroutes": len(misroutes),
        "misroutes": misroutes}, indent=1, ensure_ascii=False))
    print(json.dumps({"confusion": confusion, "n_misroutes": len(misroutes)}, indent=1))
    by = {}
    for r in misroutes:
        k = f"{r['hidden']}->{r['predicted']}"
        by[k] = by.get(k, 0) + 1
    print("misroute breakdown:", by)
    return 0


if __name__ == "__main__":
    sys.exit(main())
