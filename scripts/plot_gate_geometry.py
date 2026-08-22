#!/usr/bin/env python3
"""Plot three-group hopfield-sim histograms, ROC/AUC, threshold table.

Reads results/gate_geometry/sims_multikey_{on,off}.jsonl (rsynced from pod).
Writes png/svg + auc.json + threshold_table.json next to the jsonl.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
IN = _ROOT / "results/gate_geometry"
BETAS = (0.70, 0.75, 0.80, 0.85, 0.90)
# Pre-registered decision rule (plan): separable iff AUC(oblique vs unrelated)
# >= 0.70 AND some beta has TPR>=0.70 and unrelated FPR<=0.10.
AUC_MIN = 0.70
TPR_MIN = 0.70
FPR_MAX = 0.10


def load_groups(path: Path) -> dict[str, list[float]]:
    g: dict[str, list[float]] = {"oblique": [], "twin": [], "unrelated": []}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        g[r["group"]].append(r["max_sim"])
    return g


def roc_auc(pos: list[float], neg: list[float]) -> tuple[np.ndarray, np.ndarray, float]:
    if not pos or not neg:
        return np.array([0.0, 1.0]), np.array([0.0, 1.0]), float("nan")
    scores = np.concatenate([np.asarray(pos), np.asarray(neg)])
    labels = np.concatenate([np.ones(len(pos)), np.zeros(len(neg))])
    order = np.argsort(-scores)
    labels = labels[order]
    tps = np.cumsum(labels)
    fps = np.cumsum(1.0 - labels)
    tpr = tps / max(tps[-1], 1.0)
    fpr = fps / max(fps[-1], 1.0)
    fpr = np.concatenate([[0.0], fpr, [1.0]])
    tpr = np.concatenate([[0.0], tpr, [1.0]])
    auc = float(np.trapezoid(tpr, fpr))
    return fpr, tpr, auc


def threshold_table(g: dict[str, list[float]]) -> dict:
    pos = g["oblique"]
    out = {}
    for b in BETAS:
        out[str(b)] = {
            "oblique_tpr": round(sum(s >= b for s in pos) / len(pos), 3) if pos else None,
            "twin_fpr": (round(sum(s >= b for s in g["twin"]) / len(g["twin"]), 3)
                         if g["twin"] else None),
            "unrelated_fpr": (round(sum(s >= b for s in g["unrelated"]) / len(g["unrelated"]), 3)
                              if g["unrelated"] else None),
        }
    return out


def decide(auc_unrel: float, table: dict) -> dict:
    feasible = [b for b, row in table.items()
                if row["oblique_tpr"] is not None and row["unrelated_fpr"] is not None
                and row["oblique_tpr"] >= TPR_MIN and row["unrelated_fpr"] <= FPR_MAX]
    separable = (auc_unrel >= AUC_MIN) and bool(feasible)
    return {
        "rule": f"AUC(oblique vs unrelated)>={AUC_MIN} and exists beta with "
                f"TPR>={TPR_MIN} and unrelated FPR<={FPR_MAX}",
        "auc_vs_unrelated": round(auc_unrel, 3) if auc_unrel == auc_unrel else None,
        "feasible_betas": feasible,
        "separable": separable,
        "recommend": ("per-key margin + quantile-calibrated gate" if separable
                      else "contrastive metric head (threshold family invalid)"),
    }


def _plot(g: dict, fpr_u, tpr_u, auc_u, fpr_t, tpr_t, auc_t, stem: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        print(f"matplotlib unavailable ({e}); skip png", flush=True)
        return
    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    bins = np.linspace(0, 1, 21)
    for name, color in (("oblique", "#1f77b4"), ("twin", "#ff7f0e"),
                        ("unrelated", "#2ca02c")):
        if g[name]:
            ax.hist(g[name], bins=bins, density=True, alpha=0.45,
                    label=f"{name} n={len(g[name])}", color=color)
    ax.set_xlabel("max Hopfield sim to designated keys")
    ax.set_ylabel("density")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(stem.parent / f"hist_three_group_{stem.name}.png", dpi=140)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(5.2, 5.0))
    ax.plot(fpr_u, tpr_u, label=f"oblique vs unrelated AUC={auc_u:.3f}")
    if auc_t == auc_t:
        ax.plot(fpr_t, tpr_t, label=f"oblique vs twin AUC={auc_t:.3f}")
    ax.plot([0, 1], [0, 1], ls="--", c="gray", lw=0.8)
    ax.set_xlabel("false positive rate")
    ax.set_ylabel("true positive rate")
    ax.legend(frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(stem.parent / f"roc_three_group_{stem.name}.png", dpi=140)
    plt.close(fig)


def main() -> int:
    auc_out = {}
    tables = {}
    decisions = {}
    for tag in ("off", "on"):
        path = IN / f"sims_multikey_{tag}.jsonl"
        if not path.exists():
            print(f"missing {path}", file=sys.stderr)
            continue
        g = load_groups(path)
        fpr_u, tpr_u, auc_u = roc_auc(g["oblique"], g["unrelated"])
        fpr_t, tpr_t, auc_t = roc_auc(g["oblique"], g["twin"])
        table = threshold_table(g)
        dec = decide(auc_u, table)
        dec["auc_vs_twin"] = None if auc_t != auc_t else round(auc_t, 3)
        auc_out[tag] = {"vs_unrelated": dec["auc_vs_unrelated"],
                        "vs_twin": dec["auc_vs_twin"],
                        "n": {k: len(v) for k, v in g.items()}}
        tables[tag] = table
        decisions[tag] = dec
        _plot(g, fpr_u, tpr_u, auc_u, fpr_t, tpr_t, auc_t, IN / tag)
        print(json.dumps({"tag": tag, **dec, "table": table}, indent=2))
    (IN / "auc.json").write_text(json.dumps(auc_out, indent=1) + "\n")
    (IN / "threshold_table.json").write_text(json.dumps(tables, indent=1) + "\n")
    (IN / "decision.json").write_text(json.dumps(decisions, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
