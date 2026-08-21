"""CPU tests for the frozen scoring semantics matrix + scorecard."""
import pytest

from src.evalx import scorecard


def test_matrix_complete_and_wellformed():
    m = scorecard.load_matrix()
    for t in scorecard.MEMORY_TYPES:
        for k in scorecard.PROBE_KINDS:
            assert m[t][k]["axis"], f"{t}x{k} missing axis"
            assert "in_composite" in m[t][k]


def test_transient_never_in_recall_composite():
    m = scorecard.load_matrix()
    for k in scorecard.PROBE_KINDS:
        cell = m["transient"][k]
        assert not (cell["axis"] == "recall"), "transient must never enter the recall axis"
        if cell["axis"] in ("recall", "freshness", "locality"):
            assert cell["in_composite"] is False or cell["axis"] != "recall"


def test_transient_delayed_is_reverse_scored():
    item = {"memory_type": "transient", "kind": "qa_delayed",
            "answer": "You said you're feeling foggy and under-caffeinated.",
            "answer_keywords": ["foggy under-caffeinated", "foggy"]}
    m = scorecard.load_matrix()
    assert scorecard.score_item(item, m) == 0.0  # asserting the stale state = failure
    item2 = dict(item, answer="Nothing in particular — you didn't mention anything this morning.")
    assert scorecard.score_item(item2, m) == 1.0


def test_word_boundary_not_substring():
    m = scorecard.load_matrix()
    item = {"memory_type": "fact", "kind": "qa_immediate",
            "answer": "What a lovely morning.", "answer_keywords": ["hat"]}
    assert scorecard.score_item(item, m) == 0.0  # "hat" inside "what" is NOT a hit
    item["answer"] = "You keep a wide-brimmed hat by the door."
    assert scorecard.score_item(item, m) == 1.0


def test_near_miss_exclusive_scoring():
    m = scorecard.load_matrix()
    base = {"memory_type": "fact", "kind": "near_miss",
            "answer_keywords": ["kitchen drawer"], "twin_keywords": ["ruth"]}
    assert scorecard.score_item({**base, "answer": "It's in the kitchen drawer."}, m) == 1.0
    assert scorecard.score_item({**base, "answer": "The kitchen drawer — or with Ruth."}, m) == 0.5
    assert scorecard.score_item({**base, "answer": "Ruth has it."}, m) == 0.0


def test_aggregate_composite_and_session_scoped():
    m = scorecard.load_matrix()
    items = [
        {"memory_type": "belief", "kind": "qa_immediate", "answer": "tea, always tea",
         "answer_keywords": ["tea"]},                        # recall 1
        {"memory_type": "fact", "kind": "qa_delayed", "answer": "no idea",
         "answer_keywords": ["blue heron bakehouse"]},        # recall 0
        {"memory_type": "fact", "kind": "supersede_new", "answer": "Coffee by Design now",
         "answer_keywords": ["coffee by design", "coffee"], "old_keywords": ["tandem coffee"]},  # freshness 1
        {"memory_type": "transient", "kind": "qa_delayed", "answer": "all good today",
         "answer_keywords": ["foggy"]},                        # freshness 1 (no assertion)
        {"memory_type": "transient", "kind": "qa_immediate", "answer": "you feel foggy",
         "answer_keywords": ["foggy"]},                        # session_scoped 1, excluded
        {"memory_type": "fact", "kind": "near_miss", "answer": "kitchen drawer",
         "answer_keywords": ["kitchen drawer"], "twin_keywords": ["ruth"]},  # locality 1
    ]
    agg = scorecard.aggregate(items, m)
    assert agg["per_axis"]["recall"] == {"n": 2, "score": 0.5}
    assert agg["per_axis"]["freshness"] == {"n": 2, "score": 1.0}
    assert agg["per_axis"]["locality"] == {"n": 1, "score": 1.0}
    assert agg["composite"] == pytest.approx((0.5 + 1.0 + 1.0) / 3, abs=0.01)  # rounded to 3dp
    assert agg["session_scoped"]["n"] == 1 and agg["session_scoped"]["score"] == 1.0
    assert scorecard.old_value_residual(items) == 0.0


def test_old_value_residual_detects_lingering():
    m = scorecard.load_matrix()
    items = [
        {"memory_type": "fact", "kind": "supersede_new",
         "answer": "Coffee by Design now, though I still swing by Tandem Coffee",
         "answer_keywords": ["coffee by design", "coffee"], "old_keywords": ["tandem coffee"]},
    ]
    # own hit AND old hit -> new value correct but old value lingers
    assert scorecard.old_value_residual(items) == 1.0
