#!/usr/bin/env python3
"""P2 arm runner (POD ONLY; needs the resident backbone; no paid keys here).

Replays the selected dev-stream per arm, writes memories by arm policy,
evaluates probes at their temporal positions, journals items.jsonl per arm
(idempotent resume). One invocation runs S1, S2, S4, S5 sequentially, each
with a FRESH model load (edit state must not leak across arms).

Read-only inputs (from git): data/p2/selection.json, data/p2/router_s5_v1.json,
data/workloads/dev_v1.1.json, configs/{default,scoring_v1,pressure_v2}.yaml.
Outputs: results/p2_<arm>/items.jsonl + run.log + manifest.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import torch
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from src.evalx.unrelated import UNRELATED_POOL  # noqa: E402
from src.manifest import build_manifest, write_manifest  # noqa: E402
from src.readpath import keying  # noqa: E402
from src.readpath.prompting import build_prompt  # noqa: E402
from src.stores import editing, model_host  # noqa: E402
from src.stores.rag_store import RagStore  # noqa: E402

MAX_NEW_TOKENS = 512  # hard decode budget (handbook §4.2)
ARMS = ("S1", "S2", "S4", "S5")


def generate_answer(model, tok, question: str, rag_hits: list[dict]) -> dict:
    messages = build_prompt(question, rag_hits=[
        {"text": h["text"], "type": "fact"} for h in rag_hits])
    rendered = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    enc = tok(rendered, return_tensors="pt").to("cuda")
    # PORT FIX (read path): the prototype sets adapter.query_span over the
    # user-turn tokens at chat decode so the retrieval key excludes the fixed
    # scaffold rows (same extraction as the write-side chat keys). Legacy
    # last-60%-of-whole-prompt pooling mixes scaffold into the key and, with a
    # grown codebook, matches a wrong slot on every query.
    adapter = model_host.edit_module() if model_host.edit_active() else None
    if adapter is not None:
        span = keying.query_span_in_rendered(tok, rendered, question)
        adapter.query_span = span
    t0 = time.time()
    try:
        with torch.no_grad():
            out = model.generate(**enc, max_new_tokens=MAX_NEW_TOKENS, do_sample=False,
                                 pad_token_id=tok.eos_token_id)
    finally:
        if adapter is not None:
            adapter.query_span = None
    gen_ids = out[0][enc["input_ids"].shape[1]:]
    n_gen = int(gen_ids.shape[0])
    text = tok.decode(gen_ids, skip_special_tokens=True)
    return {"answer": text, "n_gen": n_gen, "cap_hit": n_gen >= MAX_NEW_TOKENS,
            "length_ratio": round(n_gen / MAX_NEW_TOKENS, 3),
            "gen_seconds": round(time.time() - t0, 1)}


def hf_model():
    m = model_host.current_model()
    return m.model if hasattr(m, "model") and hasattr(m, "edit_log") else m


def run_arm(arm: str, sel: dict, dev_doc: dict, router: dict, cfg: dict,
            results_root: Path) -> Path:
    # fresh backbone per arm: load_base() overwrites the module-level resident
    # state (_S), so no module reload is needed — adapters never leak across arms
    model = model_host.load_base()
    tok = model_host.tokenizer()

    run_dir = results_root / f"p2_{arm}"
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    journal = run_dir / "items.jsonl"
    done: set[str] = set()
    if journal.exists():
        for line in journal.read_text().splitlines():
            if line.strip():
                done.add(json.loads(line)["key"])

    def emit(key: str, rec: dict) -> None:
        if key in done:
            return
        rec["key"] = key
        with journal.open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        done.add(key)
        print(json.dumps({"arm": arm, **{k: v for k, v in rec.items()
                                         if k in ("key", "n_gen", "cap_hit", "answer")}}),
              flush=True)

    # --- routing policy ---------------------------------------------------------
    def route(mem: dict) -> str:
        if arm == "S1":
            return "rag"
        if arm == "S2":
            return "edit"
        t = mem["type"] if arm == "S4" else router.get(mem["id"], mem["type"])
        return {"belief": "edit", "fact": "rag", "transient": "drop"}[t]

    n_rag_expected = sum(1 for m in sel["memories"] if route(m) == "rag")
    # distractors: same-split OTHER users' facts (retrieval competition)
    sel_users = {m["user_id"] for m in sel["memories"]}
    distractors = [{"id": f"dis-{m['id']}", "text": m["canonical"]}
                   for u in dev_doc["users"] if u["user_id"] not in sel_users
                   for m in u["memories"] if m["type"] == "fact"]
    pres = cfg["pressure"]
    # budget applies to REAL routed entries only (recalibration round 1,
    # disclosed in the G2 report: pinning distractors, else eviction eats the
    # distractors and never pressures the memories — criterion 2 untestable)
    store = RagStore(top_k=pres["rag_top_k"],
                     budget=int(round(pres["store_budget_ratio"] * n_rag_expected)))
    store.seed_distractors(distractors)

    # --- replay -------------------------------------------------------------------
    mems = sorted(sel["memories"], key=lambda m: (m["session_idx"], m["id"]))
    max_session = max(m["session_idx"] for m in mems)
    scen_by_mem = {}
    for sc in sel["scenarios"]:
        for mid in sc["memory_ids"]:
            scen_by_mem.setdefault(mid, sc)
    mem_by_id = {m["id"]: m for m in mems}

    def eval_probe(mem: dict, probe: dict, eval_session: int) -> None:
        key = f"{arm}|{mem['id']}|{probe['kind']}|{probe.get('scenario_id', probe.get('text', '')[:40])}"
        if key in done:
            return
        if probe["kind"] == "free_scenario":
            question = scen_by_mem[mem["id"]]["text"]
        else:
            question = probe["text"]
        rag_hits = store.query(question)
        gen = generate_answer(model, tok, question, rag_hits)
        item = {"arm": arm, "memory_id": mem["id"], "memory_type": mem["type"],
                "kind": probe["kind"], "question": question,
                "answer_keywords": probe["answer_keywords"],
                "eval_session": eval_session, "write_session": mem["session_idx"],
                "store_evicted": mem["id"] not in store.live_ids() and route(mem) == "rag",
                "rag_hit_ids": [h["id"] for h in rag_hits], **gen}
        if probe.get("near_miss_of"):
            twin = mem_by_id.get(probe["near_miss_of"])
            if twin:
                item["twin_keywords"] = twin["probes"][0]["answer_keywords"]
        if probe["kind"] == "supersede_new" and mem.get("supersede_of"):
            old = mem_by_id.get(mem["supersede_of"])
            if old:
                item["old_keywords"] = old["probes"][0]["answer_keywords"]
        emit(key, item)

    by_session: dict[int, list[dict]] = {}
    for m in mems:
        by_session.setdefault(m["session_idx"], []).append(m)
    pending_delayed: list[tuple[dict, dict, int]] = []

    for s in range(max_session + 1):
        for m in by_session.get(s, []):
            dest = route(m)
            if dest == "edit":
                editing.edit(model_host.current_model(), {
                    "prompt": m["edit_stem"], "target_new": m["edit_target"],
                    "key_prompts": m["key_prompts"]})
                model = model_host.current_model()
            elif dest == "rag":
                if m.get("supersede_of") and m["supersede_of"] in store.live_ids():
                    store.supersede(m["supersede_of"], m["id"], m["canonical"])
                else:
                    store.add(m["id"], m["canonical"])
            # immediate probes for this memory
            for p in m["probes"]:
                if p["kind"] == "qa_immediate":
                    eval_probe(m, p, s)
                elif p["kind"] == "qa_delayed":
                    pending_delayed.append((m, p, min(s + p.get("after_sessions", 5), max_session)))
        # delayed probes due this session (written in earlier sessions)
        still = []
        for m, p, due in pending_delayed:
            if due <= s:
                eval_probe(m, p, s)
            else:
                still.append((m, p, due))
        pending_delayed = still

    # --- end-of-stream probes -------------------------------------------------------
    for m in mems:
        for p in m["probes"]:
            if p["kind"] in ("qa_paraphrase", "free_scenario", "supersede_old",
                             "supersede_new", "near_miss"):
                if p["kind"] == "free_scenario" and m["id"] not in scen_by_mem:
                    continue
                eval_probe(m, p, max_session)
    # unrelated pool per arm
    for uq in UNRELATED_POOL:
        key = f"{arm}|unrelated|{uq['id']}"
        if key in done:
            continue
        gen = generate_answer(model, tok, uq["q"], [])
        emit(key, {"arm": arm, "memory_id": None, "memory_type": "none",
                   "kind": "unrelated", "question": uq["q"],
                   "answer_keywords": uq["keywords"], "eval_session": max_session,
                   "write_session": None, "store_evicted": False, "rag_hit_ids": [],
                   **gen})
    # base-model unrelated reference (once, arm S1's run directory)
    if arm == "S1":
        model_host.swap_edit_module(None)  # base Linear (S1 never edits anyway)
        for uq in UNRELATED_POOL:
            key = f"BASE|unrelated|{uq['id']}"
            if key in done:
                continue
            gen = generate_answer(hf_model(), tok, uq["q"], [])
            emit(key, {"arm": "BASE", "memory_id": None, "memory_type": "none",
                       "kind": "unrelated", "question": uq["q"],
                       "answer_keywords": uq["keywords"], "eval_session": None,
                       "write_session": None, "store_evicted": False, "rag_hit_ids": [],
                       **gen})

    write_manifest(run_dir, build_manifest(f"p2_{arm}", cfg, extra={
        "arm": arm, "n_selected": sel["n"], "store_stats": store.stats(),
        "routing": {m["id"]: route(m) for m in sel["memories"]},
    }))
    return run_dir


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default=",".join(ARMS))
    args = ap.parse_args()
    cfg = yaml.safe_load((_REPO_ROOT / "configs" / "default.yaml").read_text())
    cfg["pressure"] = yaml.safe_load((_REPO_ROOT / "configs" / "pressure_v2.yaml").read_text())["pressure"]
    sel = json.loads((_REPO_ROOT / "data" / "p2" / "selection.json").read_text())
    dev_doc = json.loads((_REPO_ROOT / "data" / "workloads" / "dev_v1.1.json").read_text())
    router = json.loads((_REPO_ROOT / "data" / "p2" / "router_s5_v1.json").read_text())["routing"]

    results_root = _REPO_ROOT / "results"
    for arm in [a.strip() for a in args.arms.split(",")]:
        t0 = time.time()
        run_arm(arm, sel, dev_doc, router, cfg, results_root)
        print(json.dumps({"event": "arm_done", "arm": arm,
                          "seconds": round(time.time() - t0, 1)}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
