"""Ablation A (JQ ruling, dev-only): text-injection vs parametric elicitation.

For each dev user: replay the S4 (oracle) routing, then run every scenario
TWICE — identical composition scaffold, differing only in where the private
notes come from:
  parametric : rag_off generation against the edited weights (the paper's
               main variant);
  injection  : the stored canonical text verbatim (the ablation variant).
Score both by the scenario probes' answer-keyword usage. GPU but tiny.
Output: results/p4/ablation_injection.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import torch
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from src.readpath import keying  # noqa: E402
from src.readpath.prompting import build_prompt  # noqa: E402
from src.stores import editing, model_host  # noqa: E402

MAX_NEW_TOKENS = 512


def _word_hit(kw, ans):
    a = re.sub(r"\s+", " ", ans.lower())
    k = re.sub(r"\s+", " ", kw.strip().lower())
    if " " in k:
        return k in a
    return re.search(rf"\b{re.escape(k)}\b", a) is not None


def gen(model, tok, q, notes):
    messages = build_prompt(q, private_notes=notes)
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
    return tok.decode(out[0][enc["input_ids"].shape[1]:], skip_special_tokens=True)


def gen_rag_off(model, tok, q):
    """Generation with the edit module BYPASSED is NOT what we want here; the
    parametric elicitation keeps the adapter active but no RAG window — that
    is exactly gen() with empty notes when the adapter is installed."""
    return gen(model, tok, q, [])


def main() -> int:
    cfg = yaml.safe_load((_REPO_ROOT / "configs" / "default.yaml").read_text())
    thr = cfg["gate"]["hopfield_key_match_threshold"]
    dev = json.loads((_REPO_ROOT / "data" / "workloads" / "dev_v1.1.json").read_text())
    # dev planner probes: regenerate? NO — reuse the frozen planner on dev text
    # via the same frozen prompt is not journaled here; instead use each
    # scenario's bundled memories' key_prompts as the probe set (deterministic,
    # no LLM): probes = first key_prompt of each bundled memory.
    DEST = {"belief": "edit", "fact": "rag", "transient": "drop"}
    rows = []
    for user in dev["users"]:
        model_host.load_base()
        tok = model_host.tokenizer()
        mems = sorted(user["memories"], key=lambda m: (m["session_idx"], m["id"]))
        mem_by_id = {m["id"]: m for m in mems}
        for m in mems:
            if DEST[m["type"]] == "edit":
                editing.edit(model_host.current_model(), {
                    "prompt": m["edit_stem"], "target_new": m["edit_target"],
                    "key_prompts": m["key_prompts"]})
        model = model_host.current_model()
        hf = model.model if hasattr(model, "model") else model
        for sc in user["scenarios"]:
            bundled = [mem_by_id[mid] for mid in sc["memory_ids"] if mid in mem_by_id]
            if not bundled:
                continue
            probes = [m["key_prompts"][0] for m in bundled if m["key_prompts"]]
            # parametric notes
            notes_param = []
            for p in probes:
                sim, _ = keying.gate(p, hf_model=hf, tok=tok,
                                     adapter=model_host.edit_module())
                if sim >= thr:
                    notes_param.append(f"{p} — {gen_rag_off(model, tok, p).strip()}")
            # injection notes: canonical text verbatim
            notes_inj = [m["canonical"] for m in bundled]
            ans_p = gen(model, tok, sc["text"], notes_param)
            ans_i = gen(model, tok, sc["text"], notes_inj)
            for m in bundled:
                kws = next((p["answer_keywords"] for p in m["probes"]
                            if p["kind"] == "free_scenario"), [])
                if not kws:
                    continue
                rows.append({"user": user["user_id"], "scenario": sc["id"],
                             "memory": m["id"],
                             "param_hit": int(any(_word_hit(k, ans_p) for k in kws)),
                             "inj_hit": int(any(_word_hit(k, ans_i) for k in kws)),
                             "n_notes_param": len(notes_param),
                             "n_notes_inj": len(notes_inj)})
        print(json.dumps({"event": "user_done", "user": user["user_id"],
                          "rows": len(rows)}), flush=True)
    p = sum(r["param_hit"] for r in rows) / len(rows)
    i = sum(r["inj_hit"] for r in rows) / len(rows)
    out = {"n": len(rows), "parametric_usage": round(p, 3),
           "injection_usage": round(i, 3), "rows": rows}
    (_REPO_ROOT / "results" / "p4").mkdir(parents=True, exist_ok=True)
    (_REPO_ROOT / "results" / "p4" / "ablation_injection.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
