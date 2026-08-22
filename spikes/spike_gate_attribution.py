"""Gate-only attribution replay (JQ ruling 2026-08-21, Phase A2).

Pod-only, lightweight: replays each user's edit sequence per arm (fresh model
per (arm, user)), records codebook row ownership per memory, then runs GATE
FORWARDS ONLY (no generation, no arm rerun) to produce:
  1. supersede attribution on S2: each supersede_new probe's gate hit
     classified as old-slot / new-slot / other-row / no-hit;
  2. delayed transient trigger rate on S2 (gate >= frozen 0.90);
  3. scenario-probe max-sim histograms per arm (S2/S4/S5), with the
     [0.85, 0.90) lower-edge band the limitation analysis needs.

Output: results/analysis/gate_attribution.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

import yaml  # noqa: E402

from src.readpath import keying  # noqa: E402
from src.stores import editing, model_host  # noqa: E402

ARMS = ("S2", "S4", "S5")
DEST = {"belief": "edit", "fact": "rag", "transient": "drop"}
THRESHOLD = None  # from configs at runtime


def rows_for_memory(adapter, before: int) -> list[int]:
    return list(range(before, int(adapter.keys.shape[0])))


def replay_and_gate(arm: str, user: dict, routing: dict | None) -> dict:
    model_host.load_base()
    tok = model_host.tokenizer()
    model = model_host.current_model()
    hf = model.model if hasattr(model, "model") else model

    rows: dict[str, list[int]] = {}
    mems = sorted(user["memories"], key=lambda m: (m["session_idx"], m["id"]))
    for m in mems:
        if arm == "S2":
            dest = "edit"
        elif arm == "S4":
            dest = DEST[m["type"]]
        else:
            t = routing.get(m["id"], m["type"])
            dest = DEST[t]
        if dest != "edit":
            continue
        module = model_host.edit_module()
        before = int(module.keys.shape[0]) if hasattr(module, "keys") else 1
        editing.edit(model_host.current_model(), {
            "prompt": m["edit_stem"], "target_new": m["edit_target"],
            "key_prompts": m["key_prompts"]})
        model = model_host.current_model()
        rows[m["id"]] = rows_for_memory(model_host.edit_module(), before)

    adapter = model_host.edit_module()
    out: dict = {"rows": {k: v for k, v in rows.items()}}

    mem_by_id = {m["id"]: m for m in mems}
    gate = lambda text: keying.gate(text, hf_model=hf, tok=tok, adapter=adapter)  # noqa: E731

    if arm == "S2":
        sup = []
        for m in mems:
            for p in m["probes"]:
                if p["kind"] != "supersede_new" or not p.get("text"):
                    continue
                sim, slot = gate(p["text"])
                old_rows = set(rows.get(m.get("supersede_of"), []))
                new_rows = set(rows.get(m["id"], []))
                cls = ("no_hit" if sim < THRESHOLD else
                       "old_slot" if slot in old_rows else
                       "new_slot" if slot in new_rows else "other_row")
                sup.append({"memory": m["id"], "probe": p["text"][:60],
                            "sim": round(sim, 3), "slot": slot, "class": cls})
        out["supersede"] = sup

        tr = []
        for m in mems:
            if m["type"] != "transient":
                continue
            for p in m["probes"]:
                if p["kind"] == "qa_delayed" and p.get("text"):
                    sim, slot = gate(p["text"])
                    own_rows = set(rows.get(m["id"], []))
                    cls = ("no_hit" if sim < THRESHOLD else
                           "own_slot" if slot in own_rows else "other_row")
                    tr.append({"memory": m["id"], "sim": round(sim, 3),
                               "fired": bool(sim >= THRESHOLD), "class": cls})
        out["transient_delayed"] = tr

    probes = json.loads((_REPO_ROOT / "data" / "p3" / "planner_probes_test_v1.json")
                        .read_text())["probes"]
    sims = []
    for sid, plist in probes.items():
        if not sid.startswith(user["user_id"]):
            continue
        for p in plist:
            sim, slot = gate(p)
            sims.append(round(sim, 3))
    out["scenario_sims"] = sims
    return out


def main() -> int:
    global THRESHOLD
    cfg = yaml.safe_load((_REPO_ROOT / "configs" / "default.yaml").read_text())
    THRESHOLD = cfg["gate"]["hopfield_key_match_threshold"]
    test = json.loads((_REPO_ROOT / "data" / "workloads" / "test_v1.1.json").read_text())
    s5 = json.loads((_REPO_ROOT / "data" / "p3" / "router_s5_test_v1.json").read_text())["routing"]

    result: dict = {"threshold": THRESHOLD, "arms": {}}
    import os
    arms_env = os.environ.get("ATTR_ARMS")
    arms = tuple(a.strip() for a in arms_env.split(",")) if arms_env else ARMS
    for arm in arms:
        per_user = {}
        for user in test["users"]:
            per_user[user["user_id"]] = replay_and_gate(arm, user, s5 if arm == "S5" else None)
            print(json.dumps({"event": "replay_done", "arm": arm,
                              "user": user["user_id"]}), flush=True)
        # merge
        merged = {"scenario_sims": [], "supersede": [], "transient_delayed": []}
        for u, r in per_user.items():
            merged["scenario_sims"] += r["scenario_sims"]
            merged["supersede"] += r.get("supersede", [])
            merged["transient_delayed"] += r.get("transient_delayed", [])
        result["arms"][arm] = merged

    # histogram summary
    hist_out = {}
    for arm, r in result["arms"].items():
        sims = r["scenario_sims"]
        bins = {"<0.60": 0, "0.60-0.70": 0, "0.70-0.80": 0, "0.80-0.85": 0,
                "0.85-0.90": 0, ">=0.90": 0}
        for s in sims:
            if s < 0.60: bins["<0.60"] += 1
            elif s < 0.70: bins["0.60-0.70"] += 1
            elif s < 0.80: bins["0.70-0.80"] += 1
            elif s < 0.85: bins["0.80-0.85"] += 1
            elif s < 0.90: bins["0.85-0.90"] += 1
            else: bins[">=0.90"] += 1
        hist_out[arm] = {"n": len(sims), "bins": bins,
                         "band_085_090": bins["0.85-0.90"],
                         "fire_rate": round(bins[">=0.90"] / len(sims), 3) if sims else None}
    result["scenario_histogram"] = hist_out

    sup = result["arms"]["S2"]["supersede"]
    cls = {}
    for s in sup:
        cls[s["class"]] = cls.get(s["class"], 0) + 1
    result["supersede_summary"] = {"n": len(sup), "classes": cls}
    tr = result["arms"]["S2"]["transient_delayed"]
    by_cls = {}
    for t in tr:
        by_cls[t.get("class", "?")] = by_cls.get(t.get("class", "?"), 0) + 1
    result["transient_summary"] = {
        "n": len(tr), "fired": sum(1 for t in tr if t["fired"]),
        "fired_rate": round(sum(1 for t in tr if t["fired"]) / len(tr), 3) if tr else None,
        "own_slot_fired": by_cls.get("own_slot", 0),
        "own_slot_rate": round(by_cls.get("own_slot", 0) / len(tr), 3) if tr else None,
        "classes": by_cls}

    out_path = _REPO_ROOT / "results" / "analysis" / (
        f"gate_attribution_{'_'.join(a.lower() for a in arms)}.json"
        if arms != ARMS else "gate_attribution.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    slim = {k: v for k, v in result.items() if k != "arms"}
    slim["arms"] = {a: {kk: vv for kk, vv in r.items() if kk != "rows"}
                    for a, r in result["arms"].items()}
    out_path.write_text(json.dumps(slim, indent=1, ensure_ascii=False))
    print(json.dumps({k: v for k, v in slim.items() if k != "arms"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
