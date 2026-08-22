#!/usr/bin/env python3
"""P3 main-matrix arm runner (POD ONLY; resident backbone; no paid keys).

Five arms x four test users, each (arm, user) a FRESH model load (edit state
never leaks). Read path (shared by all arms, JQ ruling 2026-08-21):
  - QA probes: memories routed to RAG answer with retrieval hits; memories
    routed edit/drop answer rag_off (parametric measurement of the weights).
  - free_scenario tasks: probe-elicit-compose — precomputed planner probes;
    each probe goes through the codebook gate (elicitation rag_off on hit) AND
    the same probe queries the RAG store; collected notes compose the final
    answer via the private-notes scaffold.
Inputs (frozen, data/p3/freeze_v1.json): test_v1.1 workload, planner probes,
S3/S5 routing, scoring + pressure configs. Journal per run: items.jsonl.
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
ARMS = ("S1", "S2", "S3", "S4", "S5", "S6", "S7")
DEST = {"belief": "edit", "fact": "rag", "transient": "drop"}


def _word_hit(keyword: str, answer: str) -> bool:
    import re as _re
    a = _re.sub(r"\s+", " ", answer.lower())
    k = _re.sub(r"\s+", " ", keyword.strip().lower())
    if not k:
        return False
    if " " in k:
        return k in a
    return _re.search(rf"\b{_re.escape(k)}\b", a) is not None


def generate_answer(model, tok, question: str, rag_hits: list[dict],
                    private_notes: list[str] | None = None) -> dict:
    messages = build_prompt(question, rag_hits=[
        {"text": h["text"], "type": "fact"} for h in rag_hits],
        private_notes=private_notes or [])
    rendered = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    enc = tok(rendered, return_tensors="pt").to("cuda")
    adapter = model_host.edit_module() if model_host.edit_active() else None
    if adapter is not None:
        adapter.query_span = keying.query_span_in_rendered(tok, rendered, question)
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


def run_stream(arm: str, user: dict, test_doc: dict, routing: dict,
               planner_probes: dict[str, list[str]], cfg: dict,
               results_root: Path, run_prefix: str = "p3") -> Path:
    model = model_host.load_base()
    tok = model_host.tokenizer()
    # gate threshold: system parameter from configs (frozen); runtime override
    # of the shared hparams object propagates to every adapter constructed later
    model_host.hparams().hopfield_key_match_threshold = cfg["gate"]["hopfield_key_match_threshold"]

    run_dir = results_root / f"{run_prefix}_{arm}_{user['user_id']}"
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

    def route(mem: dict) -> str:
        if arm == "S1":
            return "rag"
        if arm == "S2":
            return "edit"
        if arm == "S7":
            return "both"  # dual-write: edit + RAG, every memory incl. transients
        if arm == "S3":
            return routing[mem["id"]]
        if arm == "S6":
            return routing[mem["id"]]  # utility router: precomputed edit/rag
        t = mem["type"] if arm == "S4" else routing.get(mem["id"], mem["type"])
        return DEST[t]

    mems = sorted(user["memories"], key=lambda m: (m["session_idx"], m["id"]))
    mem_by_id = {m["id"]: m for m in mems}
    routes = {m["id"]: route(m) for m in mems}
    edits_journal = run_dir / "edits.jsonl" if arm == "S7" else None

    def _s7_conflict(question: str, mem: dict, hits: list, final_gen: dict) -> dict | None:
        """S7 only: gate-elicited value vs retrieval record when BOTH present;
        logs the disagreement and what the composed answer actually did."""
        if not model_host.edit_active():
            return None
        hf_now = model_host.current_model()
        hf_plain = hf_now.model if hasattr(hf_now, "model") and hasattr(hf_now, "edit_log") else hf_now
        sim, _slot = keying.gate(question, hf_model=hf_plain, tok=tok,
                                 adapter=model_host.edit_module())
        if sim < cfg["gate"]["hopfield_key_match_threshold"]:
            return None
        retrieved = [h["text"] for h in hits]
        if not retrieved:
            return None
        eli = generate_answer(model, tok, question, [])  # rag_off elicitation
        kws = [k for p in mem["probes"] for k in p.get("answer_keywords", [])][:3]
        gate_hit = any(_word_hit(k, eli["answer"]) for k in kws)
        ret_hit = any(any(_word_hit(k, t) for k in kws) for t in retrieved)
        final_hit = any(_word_hit(k, final_gen["answer"]) for k in kws)
        return {"gate_sim": round(sim, 3), "gate_value": eli["answer"].strip()[:160],
                "retrieved": [t[:120] for t in retrieved[:2]],
                "gate_answerable": gate_hit, "retrieval_answerable": ret_hit,
                "consistent": gate_hit == ret_hit, "final_has_keywords": final_hit,
                "final_head": final_gen["answer"].strip()[:120]}

    n_rag = sum(1 for m in mems if routes[m["id"]] == "rag")
    pres = cfg["pressure"]
    others_facts = [{"id": f"dis-{m['id']}", "text": m["canonical"]}
                    for u in test_doc["users"] if u["user_id"] != user["user_id"]
                    for m in u["memories"] if m["type"] == "fact"]
    store = RagStore(top_k=pres["rag_top_k"],
                     budget=int(round(pres["store_budget_ratio"] * n_rag)))
    store.seed_distractors(others_facts)

    scen_by_mem: dict[str, dict] = {}
    for sc in user["scenarios"]:
        for mid in sc["memory_ids"]:
            scen_by_mem.setdefault(mid, sc)

    def eval_qa(mem: dict, probe: dict, eval_session: int) -> None:
        key = f"{arm}|{user['user_id']}|{mem['id']}|{probe['kind']}|{probe.get('text', '')[:40]}"
        if key in done:
            return
        dest = routes[mem["id"]]
        hits = store.query(probe["text"]) if dest in ("rag", "both") else []
        gen = generate_answer(model, tok, probe["text"], hits)
        item = {"arm": arm, "user_id": user["user_id"], "memory_id": mem["id"],
                "memory_type": mem["type"], "kind": probe["kind"], "route": dest,
                "question": probe["text"], "answer_keywords": probe["answer_keywords"],
                "eval_session": eval_session, "write_session": mem["session_idx"],
                "store_evicted": dest in ("rag", "both") and mem["id"] not in store.live_ids(),
                "rag_hit_ids": [h["id"] for h in hits], **gen}
        if arm == "S7":
            # conflict log: gate elicited value vs retrieval record, both present
            conflict = _s7_conflict(probe["text"], mem, hits, gen)
            if conflict:
                item["s7_conflict"] = conflict
        if probe.get("near_miss_of") and probe["near_miss_of"] in mem_by_id:
            twin = mem_by_id[probe["near_miss_of"]]
            item["twin_keywords"] = twin["probes"][0]["answer_keywords"]
        if probe["kind"] == "supersede_new" and mem.get("supersede_of") in mem_by_id:
            old = mem_by_id[mem["supersede_of"]]
            item["old_keywords"] = old["probes"][0]["answer_keywords"]
        emit(key, item)

    # --- session replay ---------------------------------------------------------
    max_session = max(m["session_idx"] for m in mems)
    by_session: dict[int, list[dict]] = {}
    for m in mems:
        by_session.setdefault(m["session_idx"], []).append(m)
    pending: list[tuple[dict, dict, int]] = []

    for s in range(max_session + 1):
        for m in by_session.get(s, []):
            dest = routes[m["id"]]
            if dest in ("edit", "both"):
                res = editing.edit(model_host.current_model(), {
                    "prompt": m["edit_stem"], "target_new": m["edit_target"],
                    "key_prompts": m["key_prompts"]})
                model = model_host.current_model()
                if edits_journal is not None:
                    with edits_journal.open("a") as f:
                        f.write(json.dumps({
                            "memory": m["id"], "edit_seconds": res["edit_seconds"],
                            "codebook_size": res["codebook_size"]}) + "\n")
            if dest in ("rag", "both"):
                if m.get("supersede_of") and m["supersede_of"] in store.live_ids():
                    store.supersede(m["supersede_of"], m["id"], m["canonical"])
                else:
                    store.add(m["id"], m["canonical"])
            for p in m["probes"]:
                if p["kind"] == "qa_immediate":
                    eval_qa(m, p, s)
                elif p["kind"] == "qa_delayed":
                    pending.append((m, p, min(s + p.get("after_sessions", 5), max_session)))
        still = []
        for m, p, due in pending:
            if due <= s:
                eval_qa(m, p, s)
            else:
                still.append((m, p, due))
        pending = still

    # --- end-of-stream QA -------------------------------------------------------
    for m in mems:
        for p in m["probes"]:
            if p["kind"] in ("qa_paraphrase", "supersede_old", "supersede_new", "near_miss"):
                eval_qa(m, p, max_session)

    # --- free scenarios: probe - elicit - compose (shared read path) -------------
    hf = model_host.current_model()
    hf_plain = hf.model if hasattr(hf, "model") and hasattr(hf, "edit_log") else hf
    for sc in user["scenarios"]:
        selected_mems = [m for m in sc["memory_ids"] if m in mem_by_id]
        if not selected_mems or sc["id"] not in planner_probes:
            continue
        probes = planner_probes[sc["id"]]
        notes: list[str] = []
        gate_fires = 0
        s7_note_conflicts = []
        for probe in probes:
            gate_head = None
            if model_host.edit_active():
                sim, slot = keying.gate(probe, hf_model=hf_plain, tok=tok,
                                        adapter=model_host.edit_module())
                if sim >= cfg["gate"]["hopfield_key_match_threshold"]:
                    gate_fires += 1
                    eli = generate_answer(model, tok, probe, [])
                    gate_head = eli["answer"].strip()
                    notes.append(f"{probe} — {gate_head}")
            retrieved_texts = [h["text"] for h in store.query(probe)]
            for t in retrieved_texts:
                notes.append(t)
            if arm == "S7" and gate_head is not None and retrieved_texts:
                # both sources present for the same probe: log agreement
                import re as _re
                words = lambda x: {w for w in _re.findall(r"[a-z0-9'-]+", x.lower()) if len(w) > 3}
                ov = len(words(gate_head) & words(" ".join(retrieved_texts)))
                s7_note_conflicts.append({
                    "probe": probe[:80], "gate_head": gate_head[:100],
                    "retrieved_head": retrieved_texts[0][:100],
                    "content_overlap": ov})
        comp = generate_answer(model, tok, sc["text"], [], private_notes=notes)
        for mid in selected_mems:
            m = mem_by_id[mid]
            p = next((x for x in m["probes"] if x["kind"] == "free_scenario"
                      and x.get("scenario_id") == sc["id"]), None)
            if p is None:
                continue
            key = f"{arm}|{user['user_id']}|{mid}|free_scenario|{sc['id']}"
            item = {"arm": arm, "user_id": user["user_id"], "memory_id": mid,
                    "memory_type": m["type"], "kind": "free_scenario",
                    "route": routes[mid], "question": sc["text"],
                    "answer_keywords": p["answer_keywords"],
                    "eval_session": max_session, "write_session": m["session_idx"],
                    "store_evicted": routes[mid] == "rag" and mid not in store.live_ids(),
                    "rag_hit_ids": [], "planner_probes": probes,
                    "gate_fires": gate_fires, "n_notes": len(notes),
                    **comp}
            if arm == "S7" and s7_note_conflicts:
                item["s7_note_conflicts"] = s7_note_conflicts
            emit(key, item)

    # --- unrelated pool ----------------------------------------------------------
    for uq in UNRELATED_POOL:
        key = f"{arm}|{user['user_id']}|unrelated|{uq['id']}"
        if key in done:
            continue
        gen = generate_answer(model, tok, uq["q"], [])
        emit(key, {"arm": arm, "user_id": user["user_id"], "memory_id": None,
                   "memory_type": "none", "kind": "unrelated", "route": "none",
                   "question": uq["q"], "answer_keywords": uq["keywords"],
                   "eval_session": max_session, "write_session": None,
                   "store_evicted": False, "rag_hit_ids": [], **gen})

    write_manifest(run_dir, build_manifest(f"{run_prefix}_{arm}_{user['user_id']}", cfg, extra={
        "arm": arm, "user_id": user["user_id"], "n_memories": len(mems),
        "store_stats": store.stats(), "routing": routes}))
    # free the resident model before the next stream loads a fresh copy
    model = None
    import gc
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return run_dir


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--prefix", default="p3")
    args = ap.parse_args()
    cfg = yaml.safe_load((_REPO_ROOT / "configs" / "default.yaml").read_text())
    cfg["pressure"] = yaml.safe_load(
        (_REPO_ROOT / "configs" / "pressure_v2.yaml").read_text())["pressure"]
    test_doc = json.loads((_REPO_ROOT / "data" / "workloads" / "test_v1.1.json").read_text())
    planner = json.loads(
        (_REPO_ROOT / "data" / "p3" / "planner_probes_test_v1.json").read_text())["probes"]
    s3 = json.loads((_REPO_ROOT / "data" / "p3" / "router_s3_v1.json").read_text())["routing"]
    s5 = json.loads((_REPO_ROOT / "data" / "p3" / "router_s5_test_v1.json").read_text())["routing"]
    s6_doc = json.loads((_REPO_ROOT / "data" / "p4" / "utility_router_v1.json").read_text())
    routings = {"S3": s3, "S5": s5, "S6": s6_doc["test_routing"],
                "S1": {}, "S2": {}, "S4": {}, "S7": {}}

    for arm in [a.strip() for a in args.arms.split(",")]:
        for user in test_doc["users"]:
            t0 = time.time()
            run_stream(arm, user, test_doc, routings[arm], planner, cfg,
                       _REPO_ROOT / "results", run_prefix=args.prefix)
            print(json.dumps({"event": "stream_done", "arm": arm,
                              "user": user["user_id"],
                              "seconds": round(time.time() - t0, 1)}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
