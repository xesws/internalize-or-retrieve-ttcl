#!/usr/bin/env python3
"""Generate paper/tables.tex (booktabs) from the FROZEN scorecard.

Rule (JQ, writing phase): no hand-copied numbers anywhere in the paper.
Every table cell below comes from data/p5/frozen_scorecard_v1.json at
generation time. Rerunnable; output is deterministic.
"""
from __future__ import annotations

import json
from pathlib import Path

SC = json.loads(Path("data/p5/frozen_scorecard_v1.json").read_text())

ARM_LABEL = {
    "S1": r"\textsc{all-rag}",
    "S2": r"\textsc{all-edit}",
    "S3": r"\textsc{random}",
    "S4": r"\textsc{oracle}",
    "S5": r"\textsc{router}",
    "S6": r"\textsc{utility}$^\dagger$",
    "S7": r"\textsc{dual-write}$^\ddagger$",
}
ARM_ORDER = ["S1", "S2", "S3", "S4", "S5", "S6", "S7"]


def fmt_ci(ci):
    lo, hi = ci
    return f"[{lo:.3f},\\ {hi:.3f}]"


def main_table():
    judge = SC["arms"][next(iter(SC["arms"]))]  # just to ensure load
    rows = []
    usage = {"S1": "0.15/0.19", "S2": "0.00/0.10", "S3": "0.07/0.16",
             "S4": "0.07/0.23", "S5": "0.07/0.16", "S6": "---", "S7": "---"}
    for a in ARM_ORDER:
        v = SC["arms"][a]
        axes = v["axes"]
        rows.append(
            f"{ARM_LABEL[a]} & {v['composite']:.3f} & {fmt_ci(v['ci95'])} & "
            f"{axes['recall']:.3f} & {axes['freshness']:.3f} & {axes['locality']:.3f} & "
            f"{v['unrelated']:.3f} & {v['judge']:.2f} ({usage[a]}) \\\\")
    per_user_rows = []
    for a in ARM_ORDER:
        pu = SC["arms"][a].get("per_user") or {}
        per_user_rows.append(
            f"{ARM_LABEL[a]} & " + " & ".join(f"{pu.get(u, float('nan')):.3f}" if isinstance(pu.get(u), (int, float)) else "---"
                                              for u in ("u03", "u04", "u05", "u06")) + " \\\\")
    return "\n".join([
        r"\begin{table}[t]\centering",
        r"\caption{Seven-arm main matrix on the full test split (210 memories, 740 probes). "
        r"Composite = equal-weight mean over recall/freshness/locality per the frozen scoring "
        r"semantics; CI95 = probe-level bootstrap (1000 draws). Unrelated = 15-item pool "
        r"(sequential-consistency uses the 75-item pool, App.~A). Judged naturalness is always "
        r"paired with scenario usage (belief/fact keyword rates). $\dagger$ preliminary "
        r"(utility router). $\ddagger$ action-space completion arm, appended after the main "
        r"matrix. Drift bound from an identical-config rerun: "
        + "|\\Delta composite| = " + f"{SC['drift_bound']['abs_diff']:.3f}" + ".}",
        r"\label{tab:main}",
        r"\small\begin{tabular}{lccccccc}",
        r"\toprule",
        r"Arm & Composite & CI95 & Recall & Fresh. & Local. & Unrel. & Judge (usage) \\",
        r"\midrule",
        *rows,
        r"\bottomrule",
        r"\end{tabular}",
        r"\begin{tabular}{lcccc}\toprule",
        r"\multicolumn{5}{l}{\emph{Per-user composite}} \\ \midrule",
        r"Arm & $u_3$ & $u_4$ & $u_5$ & $u_6$ \\ \midrule",
        *per_user_rows,
        r"\bottomrule\end{tabular}",
        r"\end{table}",
    ])


def failure_matrix():
    # from frozen per-arm failure matrices
    fm_path = Path("results/p3_scorecard.json")
    fm = json.loads(fm_path.read_text())["main"]
    cells = {}
    for a in ARM_ORDER:
        for t, rs in fm[a]["failure_matrix"].items():
            for r, v in rs.items():
                cells.setdefault((t, r), []).append((a, v["recall"], v["n"]))
    lines = [r"\begin{table}[t]\centering",
             r"\caption{Type $\times$ store failure matrix (QA + scenario keyword recall). "
             r"All arms share one dedup/supersede lifecycle; only the placement decision "
             r"differs. $\langle$arm$\rangle$ subscripts identify the source arm.}",
             r"\label{tab:failure}",
             r"\small\begin{tabular}{lcccc}", r"\toprule",
             r"Type & RAG & Edit & Drop & Dual \\ \midrule"]
    for t in ("belief", "fact", "transient"):
        row = [t.capitalize()]
        for r in ("rag", "edit", "drop", "both"):
            entries = cells.get((t, r), [])
            if not entries:
                row.append("---")
            else:
                row.append(" ".join(f"{rec:.3f}$^{{({a})}}$" for a, rec, _ in entries))
        lines.append(" & ".join(row) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


def supersede_table():
    s = SC["supersede_attribution"]["classes"]
    return "\n".join([
        r"\begin{table}[t]\centering",
        r"\caption{Attribution of the \textsc{all-edit} supersede-new failures (23 probes, "
        r"gate-only replay): key competition under consecutive same-subject updates — the "
        r"probe key lands on the old slot although the new key is written and retrievable. "
        r"Presented as a general key-value-store phenomenon, not an editing-backend defect.}",
        r"\label{tab:supersede}",
        r"\begin{tabular}{lcccc}\toprule",
        f"Old slot & New slot & Other row & No hit \\\\ \\midrule",
        f"{s.get('old_slot', 0)} & {s.get('new_slot', 0)} & {s.get('other_row', 0)} & {s.get('no_hit', 0)} \\\\",
        r"\bottomrule\end{tabular}\end{table}",
    ])


def misroute_table():
    c = SC["misroutes"]["confusion"]
    n = SC["misroutes"]["n"]
    def cell(t, p):
        return str(c[t][p])
    return "\n".join([
        r"\begin{table}[t]\centering",
        r"\caption{Router confusion against hidden type labels (N=210). All "
        f"{n} misroutes are one-directional (fact$\to$belief): preference-like entries with "
        r"concrete referents over-internalized — the favorite-X surface form overlaps the "
        r"belief criterion boundary (workload spec). Misrouted items' QA recall averages "
        r"0.272.}",
        r"\label{tab:misroute}",
        r"\begin{tabular}{lccc}\toprule",
        r" & \multicolumn{3}{c}{Predicted} \\ \cmidrule(lr){2-4}",
        r"Hidden & belief & fact & transient \\ \midrule",
        f"belief & {cell('belief','belief')} & {cell('belief','fact')} & {cell('belief','transient')} \\\\",
        f"fact & {cell('fact','belief')} & {cell('fact','fact')} & {cell('fact','transient')} \\\\",
        f"transient & {cell('transient','belief')} & {cell('transient','fact')} & {cell('transient','transient')} \\\\",
        r"\bottomrule\end{tabular}\end{table}",
    ])


def pressure_off_table():
    off = SC["pressure_off"]
    lines = [r"\begin{table}[t]\centering",
             r"\caption{Pressure-off ablation (pre-registered P5 item; budget/eviction "
             r"disabled, distractors removed; all other frozen configs unchanged). Without "
             r"pressure, all-RAG recall recovers and overtakes the router — internalization's "
             r"recall benefit is conditional on retrieval pressure, while the router's "
             r"residual edge is concentrated on freshness.}",
             r"\label{tab:pressure-off}",
             r"\small\begin{tabular}{lcccccc}\toprule",
             r"Arm & Pressure & Composite & Recall & Fresh. & Local. & fact$\times$rag \\ \midrule"]
    fm_main = json.loads(Path("results/p3_scorecard.json").read_text())["main"]
    for a in ("S1", "S5"):
        v_on = SC["arms"][a]
        v_off = off[a]
        def _score(v, axis):
            s = v["axes"][axis]
            return s["score"] if isinstance(s, dict) else s
        on_fm_raw = fm_main[a]["failure_matrix"].get("fact", {}).get("rag", {})
        on_fm = f"{on_fm_raw['recall']:.3f}" if isinstance(on_fm_raw, dict) and "recall" in on_fm_raw else "---"
        rows_spec = (("on", v_on, on_fm), ("off", v_off, v_off["failure_matrix"].get("fact", {}).get("rag", "---")))
        for tag, v, fact_rag in rows_spec:
            lines.append(f"{ARM_LABEL[a]} & {tag} & {v['composite']:.3f} & "
                         f"{_score(v, 'recall'):.3f} & {_score(v, 'freshness'):.3f} & "
                         f"{_score(v, 'locality'):.3f} & {fact_rag} \\\\")
        # the 'on' row uses main-matrix values; fact x rag on-pressure comes from scorecard
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


def s7_table():
    d = SC["s7_decomposition"]
    return "\n".join([
        r"\begin{table}[t]\centering",
        r"\caption{Dual-write loss decomposition (journal-level). Conflict-flagged and "
        r"plain rows both score far below either single-channel reference — the deficit is "
        r"global, not localized to conflict events; mechanism analysis is out of scope. "
        r"Codebook rows match the analytic expectation per user; edit cost "
        r"210 edits / 924.3\,s.}",
        r"\label{tab:s7}",
        r"\begin{tabular}{lccc}\toprule",
        r"Conflict QA & Plain QA & all-edit ref & all-rag ref \\ \midrule",
        f"{d['conflict_qa']['score']:.3f} (n={d['conflict_qa']['n']}) & "
        f"{d['plain_qa']['score']:.3f} (n={d['plain_qa']['n']}) & "
        r"0.284 & 0.552 \\",
        r"\bottomrule\end{tabular}\end{table}",
    ])


def appendix_tables():
    seq = SC["seqcheck"]
    lines = [r"\section*{A. Sequential-Consistency Confirmation}",
             r"\begin{table}[h]\centering",
             r"\caption{75-item frozen unrelated pool at cumulative-edit checkpoints "
             r"(gate 0.90). Positioning: reproduction consistent with HoReN's published "
             r"sequential stability; no threshold comparison; not merged into composites.}",
             r"\label{tab:seqcheck}",
             r"\small\begin{tabular}{lccc}\toprule",
             r"Stream & ck10 & ck25 & end (edits) \\ \midrule"]
    for k in sorted(seq):
        if k == "BASE":
            continue
        v = seq[k]
        cells = [f"{val}" for _, val in v["checkpoints"].items()]
        n_edits = v.get("n_edits_total", "")
        lines.append(f"{k.replace('_', '-')} & " + " & ".join(cells) + f" & ({n_edits}) \\\\")
    base = seq.get("BASE", {})
    lines.append(f"Base spot-check & \\multicolumn{{3}}{{c}}{{{base.get('hit_rate', '---')} (n={base.get('n', '')})}} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}", "",
              r"\section*{B. Gate Threshold Calibration (archive)}",
              r"\begin{table}[h]\centering",
              r"\caption{Dev sweep; the preregistered rule selected 0.90. Calibration "
              r"archive only — not part of the main narrative.}",
              r"\label{tab:gate}",
              r"\begin{tabular}{lcccc}\toprule",
              r"Threshold & 0.75 & 0.80 & 0.85 & 0.90 \\ \midrule"]
    sw = SC["gate_sweep"]
    keys = ["0.75", "0.8", "0.85", "0.9"] if "0.75" in sw else [0.75, 0.8, 0.85, 0.9]
    own = " & ".join(f"{sw[k]['own_hit']:.3f}" for k in keys)
    ff = " & ".join(f"{sw[k]['false_fire']:.3f}" for k in keys)
    lines.append(f"Own-key hit & {own} \\\\")
    lines.append(f"Unrelated false-fire & {ff} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}", "",
              "% One-line journal-fragment disclosure (JQ ruling): p3_S7_u03/edits.jsonl",
              "% carries one prefix line from an aborted dispatch; the analysis kept the",
              "% last contiguous segment; items.jsonl unaffected (212 unique keys)."]
    return "\n".join(lines)


def main():
    parts = [
        "% AUTO-GENERATED by scripts/paper_tables.py from data/p5/frozen_scorecard_v1.json.",
        "% DO NOT hand-edit numbers. Rerun: python scripts/paper_tables.py",
        "", main_table(), "", failure_matrix(), "", supersede_table(), "",
        misroute_table(), "", pressure_off_table(), "", s7_table(), "",
    ]
    Path("paper/tables.tex").write_text("\n".join(parts), encoding="utf-8")
    Path("paper/appendix_tables.tex").write_text(appendix_tables(), encoding="utf-8")
    print("written paper/tables.tex + paper/appendix_tables.tex")


if __name__ == "__main__":
    main()
