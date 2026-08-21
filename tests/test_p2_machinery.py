"""CPU tests: P2 selection constraints + RAG store pressure semantics."""
import json
from pathlib import Path

import pytest

from src.arms.selection import select_p2
from src.stores.rag_store import RagStore


DEV = json.loads(Path("data/workloads/dev_v1.1.json").read_text())


def test_selection_meets_frozen_rules():
    sel = select_p2(DEV, seed=42)
    assert sel["n"] == 20
    assert sel["counts"]["belief"] >= 6
    assert sel["chains"] >= 1
    assert sel["near_miss_pairs"] >= 1
    # stream coherence: sorted by session
    sessions = [m["session_idx"] for m in sel["memories"]]
    assert sessions == sorted(sessions)


def test_selection_deterministic():
    a, b = select_p2(DEV, seed=42), select_p2(DEV, seed=42)
    assert a["memory_ids"] == b["memory_ids"]


def test_rag_store_topk_and_ranking():
    s = RagStore(top_k=2)
    s.add("a", "The user keeps a spare umbrella in the hallway closet.")
    s.add("b", "The user's dentist is Dr Feld at Bayside Dental.")
    s.add("c", "The user keeps the spare car key in the kitchen drawer.")
    hits = s.query("Where is the spare car key kept?")
    assert [h["id"] for h in hits] == ["c", "a"]  # relevance first, then recency
    assert all(set(h) >= {"id", "text", "score"} for h in hits)


def test_rag_store_budget_evicts_oldest():
    s = RagStore(top_k=5, budget=3)
    for i in range(5):
        s.add(f"m{i}", f"fact number {i} about the user")
    assert s.live_ids() == {"m2", "m3", "m4"}
    assert s.evicted == ["m0", "m1"]


def test_rag_store_supersede_replaces():
    s = RagStore(top_k=5)
    s.add("old", "Favorite cafe is Tandem Coffee on A Street")
    s.supersede("old", "new", "Favorite cafe is Coffee by Design on Fore Street")
    assert "old" not in s.live_ids() and "new" in s.live_ids()
    hits = s.query("favorite cafe")
    assert hits[0]["id"] == "new"


def test_distractor_competition():
    s = RagStore(top_k=2)
    s.seed_distractors([{"id": "d1", "text": "Dentist appointment on March 14th"},
                        {"id": "d2", "text": "Book club meets the second Tuesday"},
                        {"id": "d3", "text": "Dentist checkup every six months"}])
    s.add("real", "The user's dentist is Dr Feld")
    hits = s.query("Who is the user's dentist?")
    ids = [h["id"] for h in hits]
    assert len(ids) == 2 and "real" in ids
