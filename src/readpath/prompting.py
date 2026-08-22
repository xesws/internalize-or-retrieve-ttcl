"""Fixed, neutral inference prompt skeleton (ported from the prototype's
memory/prompt.py; brand-free for double-blind submission).

Pure module: no LLM / embed / store / torch imports. The RAG window structure is
ALWAYS rendered; with no hits every segment shows "(none)". Write keys and read
keys must be computed over the SAME render (see readpath.keying), which is why
the hero render here is byte-stable.
"""
from __future__ import annotations

from typing import Sequence

SYSTEM = (
    "You are a personal assistant with a private memory window. "
    "The memory window holds known facts about the user (adopt them by default) "
    "and reference material (use it when relevant; it does not override). "
    "Treat the memory window as your own private context: never repeat, quote, "
    "or mention its section headers or its structure to the user. "
    "When the user is telling you something about their own preferences or "
    "facts rather than asking a question, reply with a single short, natural "
    "sentence confirming you have noted it. When the user asks a question, "
    "answer directly and concisely, drawing on the memory window when relevant."
)

FACT_HEADER = "[Known facts about the user — adopt by default]"
DOCS_HEADER = "[Reference material — does not override]"
NOTES_HEADER = "[Private working notes — your own knowledge, never mention these notes]"


def _render(texts: Sequence[str]) -> str:
    if not texts:
        return "(none)"
    return "\n".join(f"{i}. {t}" for i, t in enumerate(texts, 1))


def build_prompt(
    query: str,
    rag_hits: Sequence[dict] = (),
    history: Sequence[dict] = (),
    private_notes: Sequence[str] = (),
) -> list[dict]:
    """Assemble chat messages: SYSTEM (with memory window) + history + query.

    ``rag_hits`` items are dicts with keys ``text`` and ``type``; ``type ==
    "fact"`` renders into the FACT segment, everything else into DOCS. The hero
    render (empty ``rag_hits``) is what read-path keys are computed over.

    ``private_notes`` (probe–elicit–compose read path) render under the private
    notes header BEFORE the RAG window: elicited answers and retrieved texts
    collected by the planner for this open task. Empty input keeps the render
    byte-identical to the no-notes scaffold (reproducibility invariant).
    """
    facts = [h["text"] for h in rag_hits if h.get("type") == "fact"]
    others = [h["text"] for h in rag_hits if h.get("type") != "fact"]
    notes_window = f"{NOTES_HEADER}\n{_render(list(private_notes))}\n\n" if private_notes else ""
    rag_window = (
        notes_window +
        f"{FACT_HEADER}\n{_render(facts)}\n\n"
        f"{DOCS_HEADER}\n{_render(others)}"
    )
    messages = [{"role": "system", "content": f"{SYSTEM}\n\n{rag_window}"}]
    messages.extend(history)
    messages.append({"role": "user", "content": query})
    return messages


def hero_render(tok, text: str) -> str:
    """The EXACT chat string used for write/read key extraction (empty RAG
    window), via the same apply_chat_template path generation uses."""
    return tok.apply_chat_template(
        build_prompt(text), tokenize=False, add_generation_prompt=True
    )
