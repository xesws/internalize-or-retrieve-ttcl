"""P4 dual-path contrast (JQ ruling 2026-08-21): per-memory utility labels.

POD ONLY. For each selected dev memory, run BOTH placements in isolation:
  edit clone: fresh model -> edit m -> answer m's QA probes rag_off;
  rag clone : store(m + frozen distractors, pressure v2.1) -> probes w/ retrieval;
  drop      : base model answers the probes (no write) — the gain baseline.
Locality cost per edit clone: unrelated-pool drift (15 frozen items) + the
memory's near-miss probe when it has a twin. Compute cost: edit_seconds.
Utility label = (edit_gain - lambda_loc*drift - lambda_cpu*cpu) > rag_gain,
lambdas = dev medians, disclosed in the output.

Output: results/p4/dualpath_dev.json (consumed by scripts/p4_train_router.py).
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import torch
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from src.evalx.unrelated import UNRELATED_POOL  # noqa: E402
from src.readpath import keying  # noqa: E402
from src.readpath.prompting import build_prompt  # noqa: E402
from src.stores import editing, model_host  # noqa: E402
from src.stores.rag_store import RagStore  # noqa: E402

MAX_NEW_TOKENS = 512
N_SELECT = 36


def _word_hit(kw, ans):
    a = re.sub(r"\s+", " ", ans.lower())
    k = re.sub(r"\s+", " ", kw.strip().lower())
    if " " in k:
        return k in a
    return re.search(rf"\b{re.escape(k)}\b", a) is not None


def gen(model, tok, q, hits=(), notes=()):
    messages = build_prompt(q, rag_hits=[{"text": h, "type": "fact"} for h in hits],
                            private_notes=list(notes))
    rendered = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    enc = tok(rendered, return_tensors="pt").to("cuda")
    adapter = model_host.edit_module() if model_host.edit_active() else None
    if adapter is not None:
        adapter.query_span = keying.query_span_in_rendered(tok, rendered, q)
    try:
        with torch.no_grad():
            out = model.generate(**enc, max_new_tokens=MAX_NEW_TOKENS, do_sample=False,
                                 pad_token_id=tok.eos_token_id)
    finally:
        if adapter is not None:
            adapter.query_span = None
    ids = out[0][enc["input_ids"].shape[1]:]
    return tok.decode(ids, skip_special_tokens=True)


def main() -> int:
    cfg = yaml.safe_load((_REPO_ROOT / "configs" / "default.yaml").read_text())
    pres = yaml.safe_load((_REPO_ROOT / "configs" / "pressure_v2.yaml").read_text())["pressure"]
    dev = json.loads((_REPO_ROOT / "data" / "workloads" / "dev_v1.1.json").read_text())

    # stratified selection: all types represented, keep supersede/near-miss members
    import random
    rng = random.Random(42)
    mems = [m for u in dev["users"] for m in u["memories"]]
    paired = [m for m in mems if m.get("supersede_of") or m.get("near_miss_twin_of")]
    plain = [m for m in mems if m not in paired]
    sel = paired[:12] + rng.sample(plain, N_SELECT - min(12, len(paired)))
    # dev users' distractors: same-split other-user facts (dev side)
    sel_users = {m["user_id"] for m in sel}
    distractors = [{"id": f"dis-{m['id']}", "text": m["canonical"]}
                   for u in dev["users"] if u["user_id"] not in sel_users
                   for m in u["memories"] if m["type"] == "fact"]

    records = []
    edit_seconds_all = []
    for m in sel:
        probes = [p for p in m["probes"] if p["kind"] in
                  ("qa_immediate", "qa_delayed", "qa_paraphrase") and p.get("text")]
        if not probes:
            continue
        kws = probes[0]["answer_keywords"]

        # --- drop baseline (base model) ---------------------------------------
        model_host.load_base()
        tok = model_host.tokenizer()
        model = model_host.current_model()
        drop_hits = [any(_word_hit(k, gen(model, tok, p["text"])) for k in kws)
                     for p in probes]
        drop_score = sum(drop_hits) / len(probes)

        # --- edit clone --------------------------------------------------------
        t0 = time.time()
        editing.edit(model_host.current_model(), {
            "prompt": m["edit_stem"], "target_new": m["edit_target"],
            "key_prompts": m["key_prompts"]})
        edit_seconds = time.time() - t0
        edit_seconds_all.append(edit_seconds)
        model = model_host.current_model()
        edit_hits = [any(_word_hit(k, gen(model, tok, p["text"])) for k in kws)
                     for p in probes]
        edit_score = sum(edit_hits) / len(probes)
        # locality cost: unrelated drift after this single edit
        un_hits = [any(_word_hit(k, gen(model, tok, u["q"])) for k in u["keywords"])
                   for u in UNRELATED_POOL]
        unrelated_after = sum(un_hits) / len(UNRELATED_POOL)
        # near-miss probe on the twin (if any)
        nm = next((p for p in m["probes"] if p["kind"] == "near_miss" and p.get("text")), None)

        # --- rag clone ---------------------------------------------------------
        model_host.swap_edit_module(None)  # base Linear for the RAG-side reads
        model = model_host.current_model()
        model = model.model if hasattr(model, "model") and hasattr(model, "edit_log") else model
        store = RagStore(top_k=pres["rag_top_k"], budget=None)
        store.seed_distractors(distractors)
        store.add(m["id"], m["canonical"])
        rag_hits_ = [any(_word_hit(k, gen(model, tok, p["text"],
                                          hits=[h["text"] for h in store.query(p["text"])]))
                         for k in kws) for p in probes]
        rag_score = sum(rag_hits_) / len(probes)

        records.append({
            "memory": m["id"], "type": m["type"], "canonical": m["canonical"],
            "edit_stem": m["edit_stem"], "edit_target": m["edit_target"],
            "key_prompts": m["key_prompts"],
            "probes_text": [p["text"] for p in probes], "keywords": kws,
            "drop_score": round(drop_score, 3), "edit_score": round(edit_score, 3),
            "rag_score": round(rag_score, 3),
            "edit_seconds": round(edit_seconds, 1),
            "unrelated_after_edit": round(unrelated_after, 3),
            "has_near_miss_probe": bool(nm),
            "paired": bool(m.get("supersede_of") or m.get("near_miss_twin_of")),
        })
        print(json.dumps({"memory": m["id"], "type": m["type"],
                          "drop": records[-1]["drop_score"],
                          "edit": records[-1]["edit_score"],
                          "rag": records[-1]["rag_score"]}), flush=True)

    # lambdas from dev medians (disclosed)
    med_cpu = sorted(edit_seconds_all)[len(edit_seconds_all) // 2]
    # normalize scales: gains in [0,1]; drift in [0,1]; cpu in seconds -> cpu/60
    lam_loc, lam_cpu = 1.0, round(1.0 / max(med_cpu * 10, 1e-9), 4)
    base_unrelated = None
    for r in records:
        gain_edit = r["edit_score"] - r["drop_score"]
        gain_rag = r["rag_score"] - r["drop_score"]
        drift = (base_unrelated if base_unrelated is not None else 1.0) - r["unrelated_after_edit"]
        drift = max(0.0, 1.0 - r["unrelated_after_edit"])  # vs perfect 1.0 baseline
        cpu = r["edit_seconds"] / 60.0
        utility_edit = gain_edit - lam_loc * drift - lam_cpu * cpu
        r.update({"gain_edit": round(gain_edit, 3), "gain_rag": round(gain_rag, 3),
                  "loc_drift": round(drift, 3), "cpu_cost": round(cpu, 4),
                  "utility_edit": round(utility_edit, 3),
                  "label": "edit" if utility_edit > gain_rag else "rag"})
    out = {"lambda_loc": lam_loc, "lambda_cpu": lam_cpu, "median_edit_seconds": round(med_cpu, 1),
           "n": len(records), "records": records}
    out_path = _REPO_ROOT / "results" / "p4"
    out_path.mkdir(parents=True, exist_ok=True)
    (out_path / "dualpath_dev.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    from collections import Counter
    print(json.dumps({"labels": Counter(r["label"] for r in records),
                      "lambda_loc": lam_loc, "lambda_cpu": lam_cpu}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
