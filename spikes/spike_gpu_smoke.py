"""GPU smoke spike (dev handbook P0): load backbone on GPU, one forward, one
512-cap generation, report VRAM / length / cap-hit. Run on the pod only; never
part of pytest (tests/ is CPU-only)."""
from __future__ import annotations

import json
import sys

import torch

MODEL_ID = "meta-llama/Llama-3.1-8B-Instruct"
MAX_NEW_TOKENS = 512  # hard decode budget, handbook §4.2


def main() -> int:
    from transformers import AutoModelForCausalLM, AutoTokenizer

    assert torch.cuda.is_available(), "CUDA unavailable — this spike is pod-only"
    device = "cuda"
    tok = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, torch_dtype=torch.bfloat16, device_map=device
    )
    model.eval()

    msgs = [{"role": "user", "content": "Reply with the single word: pong"}]
    prompt = tok.apply_chat_template(
        msgs, tokenize=False, add_generation_prompt=True
    )
    inputs = tok(prompt, return_tensors="pt").to(device)
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            pad_token_id=tok.eos_token_id,
        )
    gen_ids = out[0][inputs["input_ids"].shape[1]:]
    n_gen = int(gen_ids.shape[0])
    text = tok.decode(gen_ids, skip_special_tokens=True)
    cap_hit = n_gen >= MAX_NEW_TOKENS
    vram = torch.cuda.max_memory_allocated() / 2**30

    report = {
        "model": MODEL_ID,
        "gpu": torch.cuda.get_device_name(0),
        "torch": torch.__version__,
        "generated_tokens": n_gen,
        "cap_hit": cap_hit,
        "length_ratio": round(n_gen / MAX_NEW_TOKENS, 3),
        "peak_vram_gib": round(vram, 2),
        "text_head": text[:120],
    }
    print(json.dumps(report, indent=2))
    return 0 if not cap_hit else 1


if __name__ == "__main__":
    sys.exit(main())
