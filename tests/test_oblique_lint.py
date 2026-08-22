"""Lexical-bridge lint for oblique diagnostic texts (no GPU, no embedder)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.gen_oblique_dev import forbidden_for, lexical_bridge


def test_target_word_is_a_bridge():
    mem = {
        "canonical": "Favorite café is Tandem Coffee on A Street.",
        "edit_target": " Tandem Coffee",
        "probes": [{"answer_keywords": ["tandem coffee", "tandem"]}],
    }
    forbidden = forbidden_for(mem)
    assert lexical_bridge("Meet me at Tandem Coffee before the meeting.", forbidden)
    assert not lexical_bridge(
        "Help me pick a quiet place to sit for ten minutes before a stressful appointment.",
        forbidden,
    )


def test_clean_text_passes():
    mem = {
        "canonical": "The user is a vegetarian.",
        "edit_target": " vegetarian",
        "probes": [{"answer_keywords": ["vegetarian"]}],
    }
    assert not lexical_bridge("Draft a grocery list for dinner this week.", forbidden_for(mem))
