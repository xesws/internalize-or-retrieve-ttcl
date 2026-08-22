#!/usr/bin/env python3
"""S7 loss decomposition (JQ ruling 2026-08-22, zero GPU, journal-level).

Splits the S7 deficit into two components:
  1. conflict pollution: per-item scores on the 438 conflict-flagged QA rows
     vs non-conflict rows in the same arm (same scoring matrix);
  2. capacity saturation: S7 vs S2 edit-side accounting — edit count,
     final codebook rows (per edits.jsonl), per-edit seconds; both arms edit
     ALL 210 memories, so any row difference must be explained.
Output: results/analysis/s7_decomposition.json (+ prints). Frozen numbers
untouched — this is analysis only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.evalx import scorecard  # noqa: E402


def load_arm(prefix: str, arm: str):
    rows = []
    for d in Path("results").glob(f"{prefix}_{arm}_u*"):
        f = d / "items.jsonl"
        if f.exists():
            rows += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    return [r for r in rows if r.get("arm") == arm]


def qa_score(rows):
    sel = [r for r in rows if r["kind"] in ("qa_immediate", "qa_delayed", "qa_paraphrase")]
    if not sel:
        return None, 0
    hits = sum(1 for r in sel if any(scorecard._word_hit(k, r.get("answer", ""))
                                     for k in r.get("answer_keywords", [])))
    return round(hits / len(sel), 3), len(sel)


def edits_stats(arm: str):
    per, total_s, rows_final = [], 0.0, 0
    for d in Path("results").glob(f"p3_{arm}_u*"):
        f = d / "edits.jsonl"
        if not f.exists():
            continue
        recs = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
        # a crashed dispatch can leave a partial prefix from an aborted stream
        # (fresh-model restart shows as codebook_size falling back); keep only
        # the LAST contiguous segment — the completed run
        restart = 0
        for i in range(1, len(recs)):
            if recs[i]["codebook_size"] <= recs[i - 1]["codebook_size"]:
                restart = i
        recs = recs[restart:]
        per.append({"user": d.name.split("_")[-1], "n_edits": len(recs),
                    "total_seconds": round(sum(r["edit_seconds"] for r in recs), 1),
                    "final_codebook_rows": recs[-1]["codebook_size"] if recs else 0,
                    "mean_edit_seconds": round(
                        sum(r["edit_seconds"] for r in recs) / len(recs), 2) if recs else 0})
        total_s += sum(r["edit_seconds"] for r in recs)
        rows_final = max(rows_final, recs[-1]["codebook_size"] if recs else 0)
    return {"per_user": per, "n_edits_total": sum(p["n_edits"] for p in per),
            "total_edit_seconds": round(total_s, 1),
            "final_codebook_rows_range": [min((p["final_codebook_rows"] for p in per), default=0),
                                          max((p["final_codebook_rows"] for p in per), default=0)]}


def main() -> int:
    matrix = scorecard.load_matrix()
    s7 = load_arm("p3", "S7")
    conflict_rows = [r for r in s7 if r.get("s7_conflict")]
    plain_rows = [r for r in s7 if not r.get("s7_conflict")]

    # component 1: conflict pollution (QA rows only, same-arm contrast)
    c_score, c_n = qa_score(conflict_rows)
    p_score, p_n = qa_score(plain_rows)
    # reference: S2 (same edit-side, no retrieval pollution) on its QA rows
    s2 = load_arm("p3", "S2")
    s2_score, s2_n = qa_score(s2)
    s1 = load_arm("p3", "S1")
    s1_score, s1_n = qa_score(s1)

    # component 2: capacity accounting S7 vs S2. S2 journaled no edits.jsonl
    # (per-edit journal was S7-only), so S2's counts are computed ANALYTICALLY
    # from the frozen workload (S2 also edits all memories): expected rows per
    # user = 1 placeholder + sum(1 raw + (#unique chat prompts)) per memory.
    s7_edits = edits_stats("S7")
    test = json.loads(Path("data/workloads/test_v1.1.json").read_text())
    s2_per = []
    for u in test["users"]:
        rows = 1
        for m in u["memories"]:
            n_prompts = len({p.strip().lower() for p in
                             ([m["edit_stem"]] + m.get("key_prompts", [])) if p and p.strip()})
            rows += 1 + n_prompts
        s2_per.append({"user": u["user_id"], "n_edits": len(u["memories"]),
                       "final_codebook_rows": rows})
    s2_edits = {
        "per_user": s2_per,
        "n_edits_total": sum(p["n_edits"] for p in s2_per),
        "note": "S2 edit counts computed analytically from test_v1.1 (no per-edit journal for S2); "
                "S7 journal final rows compared against this expectation",
        "final_codebook_rows_range": [min(p["final_codebook_rows"] for p in s2_per),
                                      max(p["final_codebook_rows"] for p in s2_per)],
    }
    rows_match = all(
        s7u["final_codebook_rows"] == s2u["final_codebook_rows"]
        for s7u, s2u in zip(sorted(s7_edits["per_user"], key=lambda x: x["user"]),
                            sorted(s2_edits["per_user"], key=lambda x: x["user"])))
    row_diff_note = None
    if not rows_match:
        row_diff_note = "S7 journal rows differ from the analytic expectation — see per_user detail"

    out = {
        "component1_conflict_pollution": {
            "S7_conflict_rows_qa": {"score": c_score, "n": c_n},
            "S7_plain_rows_qa": {"score": p_score, "n": p_n},
            "gap": round((p_score or 0) - (c_score or 0), 3),
            "reference_S2_qa": {"score": s2_score, "n": s2_n},
            "reference_S1_qa": {"score": s1_score, "n": s1_n},
        },
        "component2_capacity": {
            "S7": s7_edits, "S2_analytic": s2_edits,
            "rows_match_expectation": rows_match,
            "capacity_config_identical": True,  # same hparams/adapter for every arm
            "journal_fragment_disclosed": (
                "p3_S7_u03/edits.jsonl carries one prefix line from the aborted "
                "run_p3s7b dispatch (u03-m000, 5.0s) before the completed rerun; "
                "the analysis keeps only the last contiguous segment. items.jsonl "
                "is unaffected (212 unique keys, all from the completed stream; "
                "frozen composite untouched)"),
            "row_diff_note": row_diff_note,
        },
        "locality_context": {
            "S7_near_miss": next(v["score"] for k, v in
                                 json.load(open("results/p3_scorecard.json"))["main"]["S7"]["per_cell"].items()
                                 if k == "factxnear_miss"),
            "S2_near_miss": next(v["score"] for k, v in
                                 json.load(open("results/p3_scorecard.json"))["main"]["S2"]["per_cell"].items()
                                 if k == "factxnear_miss"),
        },
    }
    Path("results/analysis").mkdir(parents=True, exist_ok=True)
    Path("results/analysis/s7_decomposition.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
