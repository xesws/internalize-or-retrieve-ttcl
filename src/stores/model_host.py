"""Resident backbone + hot-swappable edit module (ported from the prototype's
serving/model_host.py @ main 5ee64839; codebook persistence and HTTP concerns
stripped — arms persist adapters explicitly when needed).

The edit module is a HoReN ``HopfieldAdapter`` installed in place of the
``inner_params`` submodule (llama-3.1-8b: ``model.layers[29].mlp.down_proj``).
The base ``nn.Linear`` it wraps stays frozen, so hot-swap is a single
``setattr`` toggling the submodule between the adapter (edit active) and the
original Linear (base behaviour).
"""
from __future__ import annotations

import os
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

# --- make the vendored HoReN importable as top-level package ``horen_backend`` ------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOREN_ROOT = _REPO_ROOT / "third_party" / "horen"
if str(_HOREN_ROOT) not in sys.path:
    sys.path.insert(0, str(_HOREN_ROOT))

_DEFAULT_HPARAMS = str(_HOREN_ROOT / "hparams" / "HOREN" / "llama3.1-8b.yaml")

# module-level resident state
_S: dict = {
    "model": None,      # current inference model (HF model, or HOREN wrapper after an edit)
    "tok": None,
    "hparams": None,
    "parent": None,     # parent module of the inner_params target (the mlp)
    "attr": None,       # attribute name on the parent (e.g. "down_proj")
    "original": None,   # the pristine nn.Linear captured at load (== adapter.layer)
    "adapter": None,    # the installed HopfieldAdapter, once an edit is applied
    "inference_lock": threading.RLock(),  # guards request-boundary swaps
}


def load_base(hparams_path: str = _DEFAULT_HPARAMS) -> Any:
    """Load the backbone once, resident on cuda; resolve the inner_params
    submodule so it can later be hot-swapped. Returns the HF model."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from horen_backend.models.horen.horen_hparams import HORENHyperParams
    from horen_backend.models.horen.utils import brackets_to_periods, parent_module

    hparams = HORENHyperParams.from_hparams(hparams_path)
    dtype = torch.bfloat16 if getattr(hparams, "bf16", False) else torch.float32
    model = AutoModelForCausalLM.from_pretrained(hparams.model_name, torch_dtype=dtype)
    model.to(f"cuda:{hparams.device}")
    tok = AutoTokenizer.from_pretrained(hparams.model_name)
    # pad=eos alias is SAFE here: after the §4.1 patch nothing masks labels by
    # pad id (attention_mask only), and generate() wants a pad_token_id.
    tok.pad_token_id = tok.eos_token_id

    # resolve the inner_params target exactly as HOREN.__init__ does
    name = hparams.inner_params[0]
    if name.endswith((".weight", ".bias")):
        name = name.rsplit(".", 1)[0]
    parent = parent_module(model, brackets_to_periods(name))
    attr = name.rsplit(".", 1)[-1]

    _S.update(
        model=model, tok=tok, hparams=hparams,
        parent=parent, attr=attr, original=getattr(parent, attr), adapter=None,
    )
    return model


def current_model() -> Any:
    """The live model used for inference (HOREN wrapper after an edit, else base)."""
    return _S["model"]


@contextmanager
def inference_session():
    """Hold the serving slot stable for one request-level decode/attribution
    section. Editors acquire this lock only for promotion."""
    with _S["inference_lock"]:
        yield


def swap_edit_module(m: Optional[Any]) -> None:
    """Hot-swap: install edit module ``m`` at the inner_params submodule; pass
    ``None`` to restore the base nn.Linear. Zero-downtime — one setattr."""
    parent, attr = _S["parent"], _S["attr"]
    if parent is None:
        raise RuntimeError("load_base() must be called before swap_edit_module().")
    setattr(parent, attr, _S["original"] if m is None else m)


def ensure_horen_wrapper() -> Any:
    """Ensure the resident model handle is the HoReN wrapper, whose ``.generate``
    sets ``key_id`` on the hot-swapped adapter for correct retrieval at decode."""
    from horen_backend.models.horen.editor import HOREN

    model = _S["model"]
    if model is None:
        raise RuntimeError("load_base() must be called before ensure_horen_wrapper().")
    if isinstance(model, HOREN):
        return model
    wrapper = HOREN(config=_S["hparams"], model=model)
    _S["model"] = wrapper
    return wrapper


# --- accessors ---------------------------------------------------------------------------
def tokenizer() -> Any:
    return _S["tok"]


def hparams() -> Any:
    return _S["hparams"]


def edit_module() -> Any:
    """The submodule currently at the inner_params slot (the HopfieldAdapter
    after an edit)."""
    return getattr(_S["parent"], _S["attr"])


def recorded_adapter() -> Any:
    return _S["adapter"]


def edit_active() -> bool:
    parent = _S["parent"]
    if parent is None:
        return False
    return _S["adapter"] is not None and getattr(parent, _S["attr"]) is _S["adapter"]


def register_edit_module(adapter: Any, edited_model: Any = None) -> None:
    """Record the installed adapter and (optionally) switch the resident model
    to the HOREN wrapper."""
    with _S["inference_lock"]:
        _S["adapter"] = adapter
        if edited_model is not None:
            _S["model"] = edited_model
