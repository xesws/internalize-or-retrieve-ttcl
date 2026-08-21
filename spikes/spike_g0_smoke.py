"""G0 smoke (dev handbook P0): 5 fictional edits + gate round-trip + the §4.1
three checks. Pod-only (needs the resident backbone on cuda); never part of
pytest.

Acceptance (G0): 5/5 edits written, gate hits its own key per edit, and
  (a) p(eos) at the gold boundary recovers to the same order of magnitude as
      the unedited baseline;
  (b) cap-hit <= 10% and median generation length < 150 at max_new_tokens=512;
  (c) training step count per edit == n_iter (fixed schedule, unchanged).
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

import torch
import torch.nn.functional as F

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from src.manifest import build_manifest, write_manifest  # noqa: E402
from src.readpath import keying  # noqa: E402
from src.readpath.prompting import hero_render  # noqa: E402
from src.stores import editing, model_host  # noqa: E402

RUN_ID = "g0_smoke"
MAX_NEW_TOKENS = 512  # hard decode budget (handbook §4.2)

# Five fictional facts (no real-knowledge conflicts). Probes are target-free by
# construction (checked at startup, same discipline as the workload lint).
ITEMS = [
    {
        "id": "f1",
        "stem": "The fictional city Zarithon is located in the region of",
        "target": " Vextaria",
        "key_prompt": "Which region contains the city Zarithon?",
        "probe": "Where is the fictional city Zarithon located?",
    },
    {
        "id": "f2",
        "stem": "The favorite poet of the fictional Meridian guild is",
        "target": " Oskan Vale",
        "key_prompt": "Who is the Meridian guild's favorite poet?",
        "probe": "Who does the fictional Meridian guild favor as a poet?",
    },
    {
        "id": "f3",
        "stem": "The signature color of the fictional Veltrane order is",
        "target": " deep teal",
        "key_prompt": "What color is associated with the Veltrane order?",
        "probe": "What is the signature color of the fictional Veltrane order?",
    },
    {
        "id": "f4",
        "stem": "The capital of the fictional island kingdom of Nuvora is",
        "target": " Pellenth",
        "key_prompt": "What is the capital city of Nuvora?",
        "probe": "What city serves as the capital of the fictional kingdom of Nuvora?",
    },
    {
        "id": "f5",
        "stem": "The founding year of the fictional Thessaly space colony is",
        "target": " 2187",
        "key_prompt": "In what year was the Thessaly space colony founded?",
        "probe": "When was the fictional Thessaly space colony founded?",
    },
]


# Reference items for §4.1 check (a): natural facts the BASE model completes
# and happily stops after — their boundary p(eos) is the "unedited baseline
# magnitude" the handbook compares against (fictional targets make the base
# model want to continue, so they are no reference).
NATURAL_ITEMS = [
    {"id": "n1", "stem": "The capital of France is", "target": " Paris"},
    {"id": "n2", "stem": "The chemical symbol for gold is", "target": " Au"},
]


def target_free(item: dict) -> bool:
    t = item["target"].strip().lower()
    return t not in item["probe"].lower() and t not in item["key_prompt"].lower()


def p_eos_at_gold_boundary(tok, hf_model, device, stem: str, target: str) -> float:
    """p(eos) that the model assigns to the position right after the gold
    target (teacher-forced, raw path). ~0 under the unpatched mask bug."""
    text = f"{stem}{target}"
    ids = tok(text, return_tensors="pt")["input_ids"].to(device)
    eos = tok.eos_token_id
    ids = torch.cat([ids, torch.tensor([[eos]], device=device)], dim=1)
    with torch.no_grad():
        logits = hf_model(input_ids=ids).logits
    # logits at position -2 predict the final token (the eos we appended)
    return F.softmax(logits[0, -2].float(), dim=-1)[eos].item()


def chat_boundary_p_eos(tok, hf_model, device, question: str, answer: str) -> float:
    """p(eot) at the end of a natural chat answer on the UNEDITED base — the
    deployment-relevant reference magnitude for check (a): Llama's eos is
    <|eot_id|>, which only fires after chat turns, so a raw-text natural fact
    is not a valid stop reference."""
    prefix = tok.apply_chat_template(
        [{"role": "user", "content": question}],
        tokenize=False, add_generation_prompt=True)
    ids = tok(prefix + answer, return_tensors=None)["input_ids"]
    ids = ids + [tok.eos_token_id]
    t = torch.tensor([ids], device=device)
    with torch.no_grad():
        logits = hf_model(input_ids=t).logits
    return F.softmax(logits[0, -2].float(), dim=-1)[tok.eos_token_id].item()


def main() -> int:
    import yaml

    with open(_REPO_ROOT / "configs" / "default.yaml") as f:
        cfg = yaml.safe_load(f)

    for item in ITEMS:
        assert target_free(item), f"target leaked into probe: {item['id']}"
    print(json.dumps({"event": "target_free_lint", "passed": len(ITEMS)}), flush=True)

    model = model_host.load_base()
    tok = model_host.tokenizer()
    adapter0 = None
    device = "cuda"
    threshold = model_host.hparams().hopfield_key_match_threshold
    n_iter = model_host.hparams().n_iter

    def hf() -> torch.nn.Module:
        m = model_host.current_model()
        return m.model if hasattr(m, "model") and hasattr(m, "edit_log") else m

    # --- baseline p(eos): natural facts (reference magnitude) + fictional items ---
    base_p_eos = {}
    for item in ITEMS:
        base_p_eos[item["id"]] = p_eos_at_gold_boundary(tok, model, device, item["stem"], item["target"])
    natural_p_eos = {
        it["id"]: chat_boundary_p_eos(tok, model, device, it["stem"] + "?", it["target"].strip())
        for it in NATURAL_ITEMS
    }
    natural_ref = statistics.median(natural_p_eos.values())
    print(json.dumps({"event": "baseline_p_eos", "fictional": base_p_eos,
                      "natural": natural_p_eos, "natural_ref": natural_ref}), flush=True)

    # --- 5 sequential edits (codebook stacks in one adapter) ---
    edits = []
    for item in ITEMS:
        res = editing.edit(
            model_host.current_model(),
            {
                "prompt": item["stem"],
                "target_new": item["target"],
                "key_prompts": [item["key_prompt"]],
            },
        )
        rec = {
            "id": item["id"],
            "edit_seconds": round(res["edit_seconds"], 1),
            "codebook_size": res["codebook_size"],
            "appended_key_indices": res["appended_key_indices"],
            "losses_len": len(res["wrapper"].losses),
            "loss_first": round(res["wrapper"].losses[0], 4),
            "loss_last": round(res["wrapper"].losses[-1], 4),
        }
        edits.append(rec)
        print(json.dumps({"event": "edit", **rec}), flush=True)
    model = model_host.current_model()

    # --- gate round-trip: each stem must hit the codebook above threshold ---
    adapter = model_host.edit_module()
    gates = []
    for item in ITEMS:
        sim, slot = keying.gate(item["stem"], hf_model=hf(), tok=tok, adapter=adapter)
        gates.append({"id": item["id"], "sim": round(sim, 4), "slot": slot,
                      "hit": bool(sim >= threshold)})
        print(json.dumps({"event": "gate", **gates[-1]}), flush=True)

    # --- §4.1 check (a): edited p(eos) at gold boundary recovers to the base
    # model's natural-completion magnitude (unpatched training leaves ~0) ---
    edited_p_eos = {}
    for item in ITEMS:
        edited_p_eos[item["id"]] = p_eos_at_gold_boundary(tok, hf(), device, item["stem"], item["target"])
    ratio_to_natural = {k: round(edited_p_eos[k] / max(natural_ref, 1e-9), 2)
                        for k in edited_p_eos}
    check_a = all(0.1 <= r <= 10.0 for r in ratio_to_natural.values()) \
        and min(edited_p_eos.values()) >= 0.01
    print(json.dumps({"event": "p_eos_check_a",
                      "natural_ref": round(natural_ref, 4),
                      "fictional_base": {k: round(v, 6) for k, v in base_p_eos.items()},
                      "edited": {k: round(v, 4) for k, v in edited_p_eos.items()},
                      "ratio_to_natural": ratio_to_natural, "pass": check_a}), flush=True)

    # --- §4.1 check (b): generation sanity at the 512 budget ---
    gens = []
    for item in ITEMS:
        rendered = hero_render(tok, item["probe"])
        enc = tok(rendered, return_tensors="pt").to(device)
        t0 = time.time()
        with torch.no_grad():
            out = model.generate(
                **enc, max_new_tokens=MAX_NEW_TOKENS, do_sample=False,
                pad_token_id=tok.eos_token_id,
            )
        gen_ids = out[0][enc["input_ids"].shape[1]:]
        n_gen = int(gen_ids.shape[0])
        text = tok.decode(gen_ids, skip_special_tokens=True)
        gens.append({
            "id": item["id"],
            "n_gen": n_gen,
            "cap_hit": n_gen >= MAX_NEW_TOKENS,
            "length_ratio": round(n_gen / MAX_NEW_TOKENS, 3),
            "gen_seconds": round(time.time() - t0, 1),
            "text_head": text[:160],
        })
        print(json.dumps({"event": "gen", **gens[-1]}), flush=True)
    cap_hit_rate = sum(g["cap_hit"] for g in gens) / len(gens)
    median_len = statistics.median(g["n_gen"] for g in gens)
    check_b = cap_hit_rate <= 0.10 and median_len < 150
    print(json.dumps({"event": "gen_check_b", "cap_hit_rate": cap_hit_rate,
                      "median_len": median_len, "pass": check_b}), flush=True)

    # --- §4.1 check (c): training step schedule unchanged ---
    check_c = all(e["losses_len"] == n_iter for e in edits)
    print(json.dumps({"event": "steps_check_c", "n_iter": n_iter,
                      "per_edit": [e["losses_len"] for e in edits], "pass": check_c}), flush=True)

    gate_all = all(g["hit"] for g in gates)
    verdict = {
        "edits_ok": len(edits) == 5,
        "gate_all_hit": gate_all,
        "check_a_p_eos": check_a,
        "check_b_generation": check_b,
        "check_c_steps": check_c,
        "G0_PASS": len(edits) == 5 and gate_all and check_a and check_b and check_c,
    }

    run_dir = _REPO_ROOT / "results" / RUN_ID
    manifest = build_manifest(RUN_ID, cfg, extra={"checks": verdict})
    write_manifest(run_dir, manifest)
    (run_dir / "report.json").parent.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.json").write_text(json.dumps({
        "items": ITEMS, "edits": edits, "gates": gates, "threshold": threshold,
        "natural_ref_p_eos": natural_ref,
        "fictional_base_p_eos": base_p_eos, "edited_p_eos": edited_p_eos,
        "ratio_to_natural": ratio_to_natural,
        "generations": gens, "cap_hit_rate": cap_hit_rate, "median_len": median_len,
        "max_new_tokens": MAX_NEW_TOKENS, "verdict": verdict,
    }, indent=2, ensure_ascii=False))
    print(json.dumps({"event": "verdict", **verdict}), flush=True)
    return 0 if verdict["G0_PASS"] else 1


if __name__ == "__main__":
    sys.exit(main())
