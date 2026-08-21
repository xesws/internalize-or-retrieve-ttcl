"""Scorecard per the frozen scoring semantics matrix (configs/scoring_v1.yaml).

The G2 composite is computed ONLY through this module; the matrix is the
single source of truth for (memory_type x probe_kind) -> (axis, direction,
scoring rule). Cost and attribution axes are reported, never composited.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
MEMORY_TYPES = ("belief", "fact", "transient")
PROBE_KINDS = (
    "qa_immediate", "qa_delayed", "qa_paraphrase", "free_scenario",
    "supersede_old", "supersede_new", "near_miss",
)
_COMPOSITE_AXES = ("recall", "freshness", "locality")


def load_matrix(path: str | Path | None = None) -> dict[str, dict[str, dict]]:
    p = Path(path) if path else _REPO_ROOT / "configs" / "scoring_v1.yaml"
    doc = yaml.safe_load(p.read_text())
    matrix = doc["matrix"]
    # completeness invariant: 3 types x 7 kinds, no undefined cells
    for t in MEMORY_TYPES:
        assert t in matrix, f"matrix missing type {t}"
        for k in PROBE_KINDS:
            cell = matrix[t].get(k)
            assert isinstance(cell, dict) and "axis" in cell and "scoring" in cell, (
                f"matrix cell {t}x{k} undefined or incomplete")
            assert cell["axis"] in _COMPOSITE_AXES + ("session_scoped", "na")
            assert cell["scoring"] in ("keyword_hit", "keyword_assert", "keyword_exclusive")
    return matrix


def _word_hit(keyword: str, answer: str) -> bool:
    a = re.sub(r"\s+", " ", answer.lower())
    k = re.sub(r"\s+", " ", keyword.strip().lower())
    if not k:
        return False
    if " " in k:
        return k in a
    return re.search(rf"\b{re.escape(k)}\b", a) is not None


def score_item(item: dict[str, Any], matrix: dict) -> float:
    """Score ONE evaluated probe item -> float in [0, 1].

    item fields: memory_type, kind, answer, answer_keywords (own expected
    words), twin_keywords (near-miss twin's words, optional).
    """
    cell = matrix[item["memory_type"]][item["kind"]]
    answer = item.get("answer", "")
    kws = item.get("answer_keywords") or []
    rule = cell["scoring"]
    if cell["axis"] == "na":
        return 0.0  # zero weight; caller should not have such items anyway
    if rule == "keyword_hit":
        return 1.0 if any(_word_hit(k, answer) for k in kws) else 0.0
    if rule == "keyword_assert":
        # REVERSE: asserting the stale content is the failure
        return 0.0 if any(_word_hit(k, answer) for k in kws) else 1.0
    if rule == "keyword_exclusive":
        twin = item.get("twin_keywords") or []
        own = any(_word_hit(k, answer) for k in kws)
        tw = any(_word_hit(k, answer) for k in twin)
        if own and not tw:
            return 1.0
        if own and tw:
            return 0.5
        return 0.0
    raise ValueError(f"unknown scoring rule {rule}")


def aggregate(items: list[dict[str, Any]], matrix: dict | None = None) -> dict[str, Any]:
    """Aggregate evaluated items into axis scores + the G2 composite.

    Returns {per_axis: {axis: {n, score}}, composite, counts: {...}}.
    session_scoped items are scored and reported but never composited.
    """
    matrix = matrix or load_matrix()
    buckets: dict[str, list[float]] = {ax: [] for ax in _COMPOSITE_AXES}
    session_scoped: list[float] = []
    skipped_na = 0
    per_cell: dict[tuple, dict] = {}

    for item in items:
        cell = matrix[item["memory_type"]][item["kind"]]
        if cell["axis"] == "na":
            skipped_na += 1
            continue
        s = score_item(item, matrix)
        key = (item["memory_type"], item["kind"])
        c = per_cell.setdefault(key, {"n": 0, "sum": 0.0})
        c["n"] += 1
        c["sum"] += s
        if cell["axis"] == "session_scoped":
            session_scoped.append(s)
        elif cell["in_composite"]:
            buckets[cell["axis"]].append(s)

    per_axis = {
        ax: {"n": len(v), "score": round(sum(v) / len(v), 3) if v else None}
        for ax, v in buckets.items()
    }
    available = [per_axis[ax]["score"] for ax in _COMPOSITE_AXES if per_axis[ax]["score"] is not None]
    composite = round(sum(available) / len(available), 3) if available else None
    return {
        "per_axis": per_axis,
        "composite": composite,
        "session_scoped": {"n": len(session_scoped),
                           "score": round(sum(session_scoped) / len(session_scoped), 3)
                           if session_scoped else None},
        "skipped_na": skipped_na,
        "per_cell": {f"{t}x{k}": {"n": v["n"], "score": round(v["sum"] / v["n"], 3)}
                     for (t, k), v in sorted(per_cell.items())},
    }


def old_value_residual(items: list[dict[str, Any]]) -> float | None:
    """Residual rate: fraction of supersede_new answers that still contain the
    OLD value's keywords (proposal §5.4 旧值残留率; reported, not composited)."""
    hits = [it for it in items if it["kind"] == "supersede_new" and it.get("old_keywords")]
    if not hits:
        return None
    leaked = sum(1 for it in hits
                 if any(_word_hit(k, it.get("answer", "")) for k in it["old_keywords"]))
    return round(leaked / len(hits), 3)
