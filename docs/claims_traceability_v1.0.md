# Claims-to-table traceability v1.0

Paper: *Internalize or Retrieve* (MEMPLACE). Every quantitative claim in `paper/main.tex` maps to a generated macro in `paper/numbers.tex` and/or a table cell from `scripts/paper_tables.py`. Sources are `data/p5/frozen_scorecard_v1.json` (untouched after G5) plus the JQ-authorized appendices `data/p5/s8_frozen_v1.json` and `data/p5/analysis_frozen_v1.json`. No prose number is typed by hand.

Regenerate: `python3 scripts/paper_macros.py && python3 scripts/paper_tables.py`.

## Claim 1 — conditional benefit (pressure on)

| Claim in prose | Macro / table | Frozen source |
|---|---|---|
| Router composite 0.612 vs oracle 0.639 | `\SfiveComp`, `\SfourComp`; Table~\ref{tab:main} | `arms.S5/S4.composite` |
| Gap 0.027 inside drift 0.025 | `\GapOracleRouter`, `\DriftBound` | `S4-S5`; `drift_bound.abs_diff` |
| Lead over better extreme 0.102 = 4× drift | `\LeadExtremes`, `\DriftMultiple` | `S5 - max(S1,S2)` |
| All-retrieve / all-internalize / random / dual-write composites | `\SoneComp` `\StwoComp` `\SthreeComp` `\SsevenComp`; Table~\ref{tab:main} | `arms.S1/S2/S3/S7` |
| Dual-write is worst; deficit not conflict-local | Table~\ref{tab:s7}; `\SsevenEditRef` `\SsevenRagRef` | `s7_decomposition` + `analysis.s7_refs` |
| Fact recall in weights is the low band | Table~\ref{tab:failure} Edit/Fact cells | `results/p3_scorecard.json` failure matrix |

## Claim 2 — lifecycle signal, not editing per se

| Claim in prose | Macro / table | Frozen source |
|---|---|---|
| Pressure-off: S1 recall 0.631 overtakes S5 0.568 | `\SoneOffRecall`, `\SfiveOffRecall`; Table~\ref{tab:pressure-off} | `pressure_off.S1/S5` |
| Router residual edge without pressure is freshness | `\SfiveOffFresh` vs `\SoneOffFresh` | `pressure_off` axes |
| S8 competitive: on 0.618 / off 0.731 | `\SeightOnComp`, `\SeightOffComp`; Table~\ref{tab:pressure-off} S8 rows | `s8_frozen_v1.json` |
| S8 freshness at oracle level | `\SeightOnAxFreshness` = `\SfourFresh` = 0.724 | S8 axes vs S4 |
| S8 locality lag vs oracle | `\SeightOnLocal` vs `\SfourLocal` | S8 on locality vs S4 |
| S6 ≈ S1, fails to recover oracle | `\SsixComp` vs `\SoneComp`; Table~\ref{tab:main} utility row | `arms.S6` |
| Dual-write collapses both channels | `\SsevenComp`; Table~\ref{tab:s7} | `arms.S7` + decomposition |

## Anatomy numbers (Results § failure anatomy)

| Claim | Macro / table | Source |
|---|---|---|
| 22 misroutes, all fact→belief | `\NMisroutes`; Table~\ref{tab:misroute} | `misroutes` |
| Misrouted QA recall 0.272 | `\MisrouteRecall` | `analysis.misroute.mean_qa_recall` |
| Supersede-new: 12 old / 7 new / 2 other / 2 no-hit of 23 | `\SupOld` `\SupNew` `\SupOther` `\SupNoHit` `\SupTotal`; Table~\ref{tab:supersede} | `supersede_attribution.classes` |
| Transient trigger 0.367–0.400, own-slot 0.367, assert 0.1 | `\TransientTrigger` `\TransientOwnSlot` `\TransientAssert` | `analysis.transient` |
| Scenario probes in [0.85,0.90): 53/52 of 72; fire 0.042/0.083 | `\HistBandSfour` `\HistBandSfive` `\HistProbeN` `\FireRateSfour` `\FireRateSfive` | `analysis.scenario_histogram` |
| Seqcheck base 0.973; S2 end 0.893–0.933 after 47–58 edits | `\SeqBase` `\SeqStwoEndMin` `\SeqStwoEndMax` `\SeqPoolN`; Appendix Table~\ref{tab:seqcheck} | `seqcheck` |
| Gate 0.85 false-fire 0.267; 0.90 selected | `\GateFalseFireEightFive`; Appendix Table~\ref{tab:gate} | `gate_sweep` |
| Workload size 4 users / 210 memories / 740 probes | `\TestUsers` `\TestMemories` `\TestProbes` | paper_macros constants matching freeze v1.1 |
| Injection ablation n=19, null | `\AblationN` | `analysis.ablation_injection` (from `results/p4/ablation_injection.json`) |

## What the paper does *not* claim (traceability of non-claims)

- S5 > S4 on N=210: **not claimed**; gap is inside drift, CIs overlap.
- Parametric elicitation empirically beats text-injection: **not claimed**; n=`\AblationN` null; retained on design grounds.
- Hot-swap serving: architecture description only.
- Editing per se is the lifecycle signal: **retracted in Claim 2 after S8**; value is replaceable-record management.
- Mechanism for dual-write collapse or trigger≠assertion: out of scope; numbers only.

## Regeneration checklist

1. Do not edit `data/p5/frozen_scorecard_v1.json`.
2. Append-only freezes (`s8_frozen_v1.json`, `analysis_frozen_v1.json`) require JQ authorization.
3. `python3 scripts/paper_macros.py` → `paper/numbers.tex`.
4. `python3 scripts/paper_tables.py` → `paper/tables.tex`, `paper/appendix_tables.tex`.
5. Prose in `paper/main.tex` may cite macros and `\ref{tab:*}` only.
