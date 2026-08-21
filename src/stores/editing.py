"""Thin wrapper over the vendored HoReN editing backend (ported from the
prototype's editing.py; ``PROV_KEY_PROMPTS`` renamed to ``key_prompts``).

HoReN is a pre-existing external dependency (impl of arXiv 2605.08143); it is
NEVER reimplemented here. This module only adapts our memory objects to HoReN's
API and appends the multi-key chat aliases (proposal §4.2).
"""
from __future__ import annotations

import time
from typing import Any

from src.readpath.keying import compute_key
from src.stores import model_host


def edit(model: Any, memory: Any, *, key_mode: str = "chat") -> dict:
    """Apply ONE HoReN edit onto the resident ``model``; return the installed
    adapter + timing.

    ``memory``: a pre-split request dict ``{"prompt": stem, "target_new":
    target, "key_prompts": [answer-free aliases, optional]}`` (extra keys are
    ignored by HoReN's tokenizer).

    ``key_mode``:
      - ``"chat"`` (default): after the edit, APPEND query-span-isolated chat
        keys (the hero render of the stem + each key_prompt) that reuse the
        same trained value, so the codebook serves BOTH the raw path and the
        chat path — the multi-key write of proposal §4.2.
      - ``"raw"``: legacy — keep only HoReN's native raw key.
    """
    from horen_backend.models.horen.editor import HOREN
    from horen_backend.models.horen.horen_main import apply_horen_to_model

    request = memory if isinstance(memory, dict) else {"prompt": memory.text, "target_new": ""}
    tok = model_host.tokenizer()
    hp = model_host.hparams()

    # Sequential editing: after the first edit the resident model IS the HOREN
    # wrapper. apply_horen_to_model expects the underlying HF model (it
    # traverses model.model.layers…), so unwrap one level — else HOREN.__init__
    # fails to find the layer and, unwrapped, add_key APPENDS into the SAME
    # codebook so N edits stack instead of nesting wrappers.
    hf_model = model.model if isinstance(model, HOREN) else model

    t0 = time.time()
    wrapper, reset_fn = apply_horen_to_model(hf_model, tok, [request], hp)
    edit_seconds = time.time() - t0

    adapter = model_host.edit_module()  # the now-installed HopfieldAdapter
    appended_key_indices: list[int] = []
    if key_mode == "chat":
        appended_key_indices = _append_chat_keys(
            wrapper,
            adapter,
            tok,
            [request["prompt"], *request.get("key_prompts", [])],
        )

    model_host.register_edit_module(adapter, edited_model=wrapper)

    return {
        "adapter": adapter,
        "wrapper": wrapper,
        "reset": reset_fn,
        "edit_seconds": edit_seconds,
        "codebook_size": wrapper.get_codebook_size(),
        "appended_key_indices": appended_key_indices,
    }


def _append_chat_keys(wrapper: Any, adapter: Any, tok: Any, prompts: list[str]) -> list[int]:
    """Append query-span chat keys that reuse the value row HoReN just trained.

    Keeps the native raw key intact. Additional answer-free canonical prompts
    are retrieval aliases for the same value (useful for separating
    near-colliding personal-belief queries). Returns appended row indices.
    """
    import torch

    v_idx = wrapper.edit_log["chosen_key"]  # the just-trained value/label row
    appended: list[int] = []
    seen: set[str] = set()
    for prompt in prompts:
        prompt = (prompt or "").strip()
        key = prompt.lower()
        if not prompt or key in seen:
            continue
        seen.add(key)

        chat_key = compute_key(prompt, templated=True, hf_model=wrapper.model, tok=tok, adapter=adapter)
        appended.append(int(adapter.keys.shape[0]))
        adapter.keys = torch.cat([adapter.keys, chat_key.to(adapter.keys.dtype)], dim=0)
        if getattr(adapter, "adapter_mode", None) == "value":
            adapter.values = torch.nn.Parameter(
                torch.cat([adapter.values, adapter.values[v_idx : v_idx + 1]], dim=0),
                requires_grad=adapter.values.requires_grad,
            )
        elif getattr(adapter, "adapter_mode", None) == "lora":
            adapter.lora_A = torch.nn.Parameter(
                torch.cat([adapter.lora_A, adapter.lora_A[v_idx : v_idx + 1]], dim=0),
                requires_grad=adapter.lora_A.requires_grad,
            )
            adapter.lora_B = torch.nn.Parameter(
                torch.cat([adapter.lora_B, adapter.lora_B[v_idx : v_idx + 1]], dim=0),
                requires_grad=adapter.lora_B.requires_grad,
            )
        adapter.key_labels.append(adapter.key_labels[v_idx])
    return appended
