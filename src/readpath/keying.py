"""Query-span-isolated key extraction for HoReN retrieval (ported verbatim in
logic from the prototype's keying.py; only the prompt dependency was swapped to
the neutral ``readpath.prompting``).

The HoReN retrieval key is a layer-29 hidden state of the input's forward pass.
At edit time HoReN keys on the RAW stem; at chat inference the prompt is wrapped
in a fixed scaffold, so the read key must be pooled over ONLY the user-turn
(query) token rows — the identical slice on both write and read. This module
reuses the adapter's own ``_pool_span`` / ``_select_query`` / ``_query`` so
write/read/gate never diverge.
"""
from __future__ import annotations

from typing import Any, Optional, Tuple

import torch
import torch.nn.functional as F

from .prompting import hero_render


def query_span_in_rendered(tok: Any, rendered: str, text: str) -> Tuple[int, int]:
    """(start, end) inclusive token indices of the user-turn ``text`` within an
    already-rendered chat string, via offset_mapping. Special/role tokens have
    empty offset spans and are excluded; tokens overlapping the query char span
    are kept (robust to BPE merges and double-BOS)."""
    enc = tok(rendered, return_offsets_mapping=True)
    offsets = enc["offset_mapping"]
    char_start = rendered.rindex(text)  # the user-turn occurrence
    char_end = char_start + len(text)
    idxs = [
        i
        for i, (cs, ce) in enumerate(offsets)
        if ce > cs and cs < char_end and ce > char_start
    ]
    if not idxs:
        raise ValueError(f"could not locate query span for text={text!r}")
    return idxs[0], idxs[-1]


def locate_query_span(tok: Any, text: str, *, templated: bool) -> Tuple[int, int]:
    """Query-span indices for ``text``: in the hero render (templated=True) or
    over the whole raw prompt (templated=False)."""
    if templated:
        return query_span_in_rendered(tok, hero_render(tok, text), text)
    ids = tok(text)["input_ids"]
    special = set(getattr(tok, "all_special_ids", []) or [])
    start = 0
    while start < len(ids) - 1 and ids[start] in special:
        start += 1
    return start, len(ids) - 1


def compute_key(
    text: str,
    *,
    templated: bool,
    hf_model: Any,
    tok: Any,
    adapter: Any,
) -> torch.Tensor:
    """Extract the (optionally normalized) retrieval key [1, D] for ``text``.

    One forward of ``hf_model`` over the (raw or hero-templated) text; captures
    the down_proj input via a forward_pre_hook on ``adapter``; pools it through
    the adapter's OWN extractor. ``adapter_mode='none'`` during the forward
    makes it a pure capture with no match/inject/state mutation.
    """
    if templated:
        rendered = hero_render(tok, text)
        enc = tok(rendered, return_tensors="pt").to(adapter.device)
        span: Optional[Tuple[int, int]] = query_span_in_rendered(tok, rendered, text)
    else:
        enc = tok(text, return_tensors="pt").to(adapter.device)
        span = None

    captured: dict = {}

    def _pre_hook(_module, args):
        captured["x"] = args[0]

    handle = adapter.register_forward_pre_hook(_pre_hook)
    old_mode = adapter.adapter_mode
    adapter.adapter_mode = "none"
    try:
        with torch.no_grad():
            hf_model(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"])
    finally:
        adapter.adapter_mode = old_mode
        handle.remove()

    x = captured["x"]
    if span is not None:
        key = adapter._pool_span(x, span[0], span[1])
    else:
        key = adapter._select_query(x, x.shape[1] - 1)
    if adapter.normalize_codebook_keys:
        key = F.normalize(key, p=2, dim=-1)
    return key  # [1, D]


def score(read_key: torch.Tensor, write_key: torch.Tensor, adapter: Any) -> float:
    """Max retrieval score of ``read_key`` against a codebook seeded as
    [random_placeholder, write_key], via the adapter's own ``_query`` — the
    production gate function. Float32 for clean diagnostics."""
    saved = adapter.keys
    placeholder = saved[0:1].float()
    codebook = torch.cat([placeholder, write_key.float()], dim=0)
    adapter.keys = codebook
    try:
        sims = adapter._query(read_key.float())
    finally:
        adapter.keys = saved
    return sims.max().item()


def gate(text: str, *, hf_model: Any, tok: Any, adapter: Any) -> Tuple[float, int]:
    """HoReN deferral gate for ``text`` against the INSTALLED codebook:
    returns (sim, slot) where sim is the max normalized-Hopfield score — the
    value compared to ``hopfield_key_match_threshold`` at inference — and slot
    is the argmax codebook row (for attribution back to the memory)."""
    rk = compute_key(text, templated=True, hf_model=hf_model, tok=tok, adapter=adapter)
    scores = adapter._query(rk)
    return scores.max().item(), int(scores.argmax().item())
