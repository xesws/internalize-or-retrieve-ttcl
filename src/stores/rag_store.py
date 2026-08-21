"""Local lexical RAG store with pressure semantics (proposal §5.2).

Pure-python BM25 — the pod holds no paid keys, so retrieval never calls an
embedding API. Pressure knobs (configs/pressure_v2.yaml):
  top_k          — cap on retrieved hits per query
  budget         — max live entries; inserting beyond evicts the OLDEST
  distractors    — extra non-answer documents seeded into the store
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

_STOP = {"the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is",
         "are", "my", "me", "i", "you", "your", "it", "its", "at", "by",
         "with", "from", "her", "his", "their", "she", "he", "they"}


def _tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9'-]+", text.lower()) if w not in _STOP]


class RagStore:
    def __init__(self, *, top_k: int = 3, budget: int | None = None):
        self.top_k = top_k
        self.budget = budget
        self.entries: list[dict[str, Any]] = []  # {id, text, order}
        self._order = 0
        self.evicted: list[str] = []

    # --- writes ---------------------------------------------------------------
    def add(self, entry_id: str, text: str) -> None:
        self.entries.append({"id": entry_id, "text": text, "order": self._order})
        self._order += 1
        if self.budget is not None:
            while len(self.entries) > self.budget:
                gone = self.entries.pop(0)  # oldest-first eviction
                self.evicted.append(gone["id"])

    def supersede(self, old_id: str, new_id: str, new_text: str) -> None:
        """Lifecycle replace: drop the old entry, insert the new one."""
        self.entries = [e for e in self.entries if e["id"] != old_id]
        self.add(new_id, new_text)

    def seed_distractors(self, docs: list[dict[str, str]]) -> None:
        for d in docs:
            self.add(d["id"], d["text"])

    # --- reads ----------------------------------------------------------------
    def _bm25_scores(self, query: str) -> list[tuple[float, dict]]:
        q = _tokens(query)
        if not self.entries:
            return []
        n = len(self.entries)
        doc_toks = [_tokens(e["text"]) for e in self.entries]
        df: Counter = Counter()
        for toks in doc_toks:
            df.update(set(toks))
        avgdl = sum(len(t) for t in doc_toks) / n
        k1, b = 1.5, 0.75
        scores = []
        for e, toks in zip(self.entries, doc_toks):
            tf = Counter(toks)
            s = 0.0
            for term in q:
                if term not in tf:
                    continue
                idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
                s += idf * tf[term] * (k1 + 1) / (tf[term] + k1 * (1 - b + b * len(toks) / avgdl))
            scores.append((s, e))
        return scores

    def query(self, text: str) -> list[dict[str, Any]]:
        """Top-k hits (highest BM25 first, ties by recency)."""
        scored = self._bm25_scores(text)
        scored.sort(key=lambda se: (-se[0], -se[1]["order"]))
        return [dict(e, score=round(s, 3)) for s, e in scored[: self.top_k]]

    def live_ids(self) -> set[str]:
        return {e["id"] for e in self.entries}

    def stats(self) -> dict[str, Any]:
        return {"live": len(self.entries), "evicted": len(self.evicted),
                "evicted_ids": list(self.evicted)}
