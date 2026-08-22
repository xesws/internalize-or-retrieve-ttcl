#!/usr/bin/env python3
"""Gate geometry diagnostic (POD, forwards only, ~1h).

Installs a dummy HoReN adapter then REPLACES its keys with compute_key
rows for every dev belief/fact (no value training — gate is key-only).
Scores three query groups at multi-key on/off.

Does not write frozen scorecards or change gate 0.90.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import torch

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from src.readpath import keying  # noqa: E402
from src.stores import editing, model_host  # noqa: E402

DATA = _REPO_ROOT / "data/gate_geometry/oblique_dev_v1.json"
WORKLOAD = _REPO_ROOT / "data/workloads/dev_v1.1.json"
OUT = _REPO_ROOT / "results/gate_geometry"
BETAS = (0.70, 0.75, 0.80, 0.85, 0.90)


def _memories() -> list[dict]:
    doc = json.loads(WORKLOAD.read_text())
    return [m for u in doc["users"] for m in u["memories"]
            if m["type"] in ("belief", "fact")]


def _install_dummy() -> None:
    model_host.load_base()
    editing.edit(
        model_host.current_model(),
        {"prompt": "The diagnostic placeholder fact is",
         "target_new": " unused.", "key_prompts": []},
        key_mode="raw",
    )


def _build_keys(memories: list[dict], *, multi_key: bool) -> dict[str, list[int]]:
    adapter = model_host.edit_module()
    hf = model_host.current_model().model
    tok = model_host.tokenizer()
    rows: dict[str, list[int]] = {}
    keys = []
    for m in memories:
        start = len(keys)
        stem = m["edit_stem"]
        k_raw = keying.compute_key(
            stem, templated=False, hf_model=hf, tok=tok, adapter=adapter)
        keys.append(k_raw.detach())
        if multi_key:
            seen: set[str] = set()
            for p in [stem, *list(m.get("key_prompts") or [])]:
                p = (p or "").strip()
                if not p or p.lower() in seen:
                    continue
                seen.add(p.lower())
                k = keying.compute_key(
                    p, templated=True, hf_model=hf, tok=tok, adapter=adapter)
                keys.append(k.detach())
        rows[m["id"]] = list(range(start, len(keys)))
    stacked = torch.cat(keys, dim=0).to(
        device=adapter.keys.device, dtype=adapter.keys.dtype)
    adapter.keys = stacked
    return rows


def _max_on_rows(scores: torch.Tensor, idxs: list[int]) -> float:
    if not idxs:
        return float("nan")
    return float(scores[0, idxs].max().item())


def score_queries(pack: dict, rows: dict[str, list[int]], *,
                  multi_key: bool, tag: str) -> list[dict]:
    adapter = model_host.edit_module()
    hf = model_host.current_model().model
    tok = model_host.tokenizer()
    recs = []

    def run(query: str, group: str, related_id: str | None, extra: dict) -> None:
        rk = keying.compute_key(
            query, templated=True, hf_model=hf, tok=tok, adapter=adapter)
        scores = adapter._query(rk.float())
        glob_max = float(scores.max().item())
        glob_arg = int(scores.argmax().item())
        own = _max_on_rows(scores, rows[related_id]) if related_id else glob_max
        recs.append({
            "group": group, "query": query[:180], "related_id": related_id,
            "max_sim": round(own, 6), "global_max": round(glob_max, 6),
            "global_arg": glob_arg, "multi_key": multi_key, **extra,
        })

    for o in pack["oblique"]:
        run(o["text"], "oblique", o["memory_id"],
            {"memory_id": o["memory_id"], "type": o["type"]})
    for t in pack["twins"]:
        run(t["query"], "twin", t["related_id"],
            {"self_id": t["self_id"]})
    for u in pack["unrelated"]:
        run(u["query"], "unrelated", None, {"uid": u.get("id")})
    return recs


def summarize(recs: list[dict]) -> dict:
    by = {}
    for r in recs:
        by.setdefault(r["group"], []).append(r["max_sim"])
    table = {}
    pos = by.get("oblique", [])
    for b in BETAS:
        table[str(b)] = {
            "oblique_tpr": round(sum(s >= b for s in pos) / len(pos), 3) if pos else None,
            "twin_fpr": (round(sum(s >= b for s in by["twin"]) / len(by["twin"]), 3)
                         if by.get("twin") else None),
            "unrelated_fpr": (round(sum(s >= b for s in by["unrelated"]) / len(by["unrelated"]), 3)
                              if by.get("unrelated") else None),
        }
    return {
        "n": {g: len(v) for g, v in by.items()},
        "mean": {g: round(sum(v) / len(v), 4) for g, v in by.items() if v},
        "threshold_table": table,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    pack = json.loads(DATA.read_text())
    memories = _memories()
    t_all = time.time()
    print(json.dumps({"event": "load_base"}), flush=True)
    _install_dummy()
    print(json.dumps({"event": "dummy_installed",
                      "seconds": round(time.time() - t_all, 1)}), flush=True)

    reports = {}
    for mk in (False, True):
        tag = "on" if mk else "off"
        t0 = time.time()
        rows = _build_keys(memories, multi_key=mk)
        recs = score_queries(pack, rows, multi_key=mk, tag=tag)
        path = OUT / f"sims_multikey_{tag}.jsonl"
        with path.open("w") as f:
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        summary = summarize(recs)
        summary["seconds"] = round(time.time() - t0, 1)
        reports[tag] = summary
        (OUT / f"summary_{tag}.json").write_text(json.dumps(summary, indent=1))
        print(json.dumps({"event": "pass_done", "multi_key": tag,
                          **summary}), flush=True)

    (OUT / "run_meta.json").write_text(json.dumps({
        "disclosure": "key-only codebook (no value training); dummy edit to install adapter",
        "n_memories": len(memories),
        "n_oblique": len(pack["oblique"]),
        "wall_seconds": round(time.time() - t_all, 1),
        "reports": reports,
    }, indent=1))
    print(json.dumps({"event": "done", "out": str(OUT),
                      "wall": round(time.time() - t_all, 1)}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
