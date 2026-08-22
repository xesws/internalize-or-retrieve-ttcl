# Claims-to-table traceability v1.1 (final)

Paper: *Internalize or Retrieve* (MEMPLACE). Numbers still come only from `paper/numbers.tex` macros and generated tables. `data/p5/frozen_scorecard_v1.json` untouched.

v1.1 (2026-08-22): Claim 2 wording **final** (JQ-approved); pressure narrative repositioned; budget-severity scan withdrawn; S8 axis table added (App.~C).

Regenerate: `python3 scripts/paper_macros.py && python3 scripts/paper_tables.py && python3 scripts/analysis_s8_axes.py`.

## Budget-severity scan — withdrawn

Never started (no GPU journals, no tmux, no CLI flag). Reason, recorded verbatim:

> 库容量在真实部署中以万计，条目级驱逐在本工作负载规模下不构成有意义的机制。

## Claim 2 — old vs new (final)

**Old (checklist v1.2, pre-S8 rewrite):** 三证合一——pressure-off 消融 (S1 recall 反超)、S6 否定、S7 压垮；「放置决策的价值住在生命周期轴上」；未区分替换/丢弃与编辑，未写容量现实。

**New (final, `paper/main.tex` Claim 2):** Lifecycle value lives in **replace and drop**, not editing per se. Type-aware single-store with replacement is the strong default at this scale; internalization shows no composite advantage; S8 vs S5 is well-posed because both run the same replace/drop lifecycle and deployed codebook/retrieval capacity is tens of thousands of records.

Status: **final**.

## Claim 1 — persistence stress test (reframed, numbers unchanged)

Same macros as v1.0 (`\SfiveComp` vs `\SfourComp`, gap, drift). Prose no longer reads the budgeted store as a deployment capacity model.

## Pressure-narrative edit log

| Location | Change |
|---|---|
| Abstract | Main reading = real-capacity / S8 default; internalization has no composite advantage; budgeted matrix is a persistence stress test |
| Intro evaluation sentence | Real-capacity setting + stress test, not “explicit budget pressure” as the selling point |
| Claim 1 title | “conditional benefit” → “persistence stress test” |
| Claim 2 | Approved expansion (replace+drop, capacity, no composite advantage) |
| Setup ¶ Retrieval pressure | top-$k$ + distractors = read-side noise (deployment); eviction = persistence stress test; pressure-off = main reading, not ablation |
| §4.1 | Now real-capacity (former pressure-off subsection, promoted) |
| §4.2 S8 | Strong default; eviction exposure labeled stress-test; App.~C for slices |
| §4.3 | Now persistence stress test (former main matrix) |
| Limitations | Future work trains on replace/drop, not eviction as a deployment target |
| `tab:main` caption | Stress-test label; pointer to `tab:pressure-off` |
| `tab:pressure-off` caption | Real-capacity vs stress test; off is the main reading |

## S8 axis table (App.~C)

Source: `data/p5/s8_axis_decomp_frozen_v1.json` (checksum vs `s8_frozen_v1.json` on S8-on axes: pass).

| Slice | n | Finding |
|---|---|---|
| Five columns S4/S5/S8 × on/off | — | S4-off `not_run`. S8-off strongest composite. Unrelated = 1.000 all scored cells |
| belief×supersede old/new | `\BeliefSliceN` (=0) | Empty; pairs fall on facts |
| belief×near-miss | 0 | Empty |
| fact×supersede-new | 23 | S8-on matches oracle (0.783); S8-off 0.826 |
| fact×near-miss | `\FactNearMissN` | Stress-test locality gap S8 0.639 vs oracle/router 0.694; closes off (both 0.833) |

## Regeneration checklist

1. Do not edit `frozen_scorecard_v1.json`.
2. Append-only freezes require JQ authorization (this round: `s8_axis_decomp_frozen_v1.json`).
3. Prose: macros and `\ref{tab:*}` only.
