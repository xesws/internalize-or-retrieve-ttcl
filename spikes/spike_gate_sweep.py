"""Gate threshold dev sweep (handbook §4.2 red line): one pass, pick once.

Loads the backbone, edits the dev P2-selection stream (all 20 memories,
S2-style), then measures — at thresholds {0.75, 0.80, 0.85, 0.90} —
  own_hit  : gate fires on each memory's stem + key prompts (should fire)
  false_fire: gate fires on the frozen unrelated pool (should not fire)
Pre-registered decision rule: if 0.85 satisfies own_hit >= 0.95 and
false_fire <= 0.05, KEEP 0.85; otherwise pick the largest threshold that
satisfies both; if none does, report and stop (handbook: no silent tuning).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

import yaml  # noqa: E402

from src.evalx.unrelated import UNRELATED_POOL  # noqa: E402
from src.readpath import keying  # noqa: E402
from src.stores import editing, model_host  # noqa: E402

THRESHOLDS = [0.75, 0.80, 0.85, 0.90]


def main() -> int:
    sel = json.loads((_REPO_ROOT / "data" / "p2" / "selection.json").read_text())
    cfg = yaml.safe_load((_REPO_ROOT / "configs" / "default.yaml").read_text())

    model = model_host.load_base()
    tok = model_host.tokenizer()
    for m in sel["memories"]:
        editing.edit(model_host.current_model(), {
            "prompt": m["edit_stem"], "target_new": m["edit_target"],
            "key_prompts": m["key_prompts"]})
        model = model_host.current_model()

    adapter = model_host.edit_module()
    hf = model_host.current_model().model

    own_texts = []
    for m in sel["memories"]:
        own_texts += [m["edit_stem"]] + list(m["key_prompts"][:1])
    own_sims = [keying.gate(t, hf_model=hf, tok=tok, adapter=adapter)[0]
                for t in own_texts]
    unrel_sims = [keying.gate(u["q"], hf_model=hf, tok=tok, adapter=adapter)[0]
                  for u in UNRELATED_POOL]

    table = {}
    for thr in THRESHOLDS:
        own = sum(1 for s in own_sims if s >= thr) / len(own_sims)
        ff = sum(1 for s in unrel_sims if s >= thr) / len(unrel_sims)
        table[thr] = {"own_hit": round(own, 3), "false_fire": round(ff, 3)}

    ok = lambda t: table[t]["own_hit"] >= 0.95 and table[t]["false_fire"] <= 0.05  # noqa: E731
    if ok(0.85):
        chosen = 0.85
    else:
        candidates = [t for t in THRESHOLDS if ok(t)]
        chosen = max(candidates) if candidates else None

    report = {"thresholds": table, "chosen": chosen,
              "rule": "keep 0.85 if it satisfies (own>=0.95, false<=0.05); else largest satisfying; else STOP",
              "n_own": len(own_sims), "n_unrelated": len(unrel_sims),
              "config_gate_value": cfg["gate"]["hopfield_key_match_threshold"]}
    print(json.dumps(report, indent=1))
    out = _REPO_ROOT / "results" / "gate_sweep"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=1))
    return 0 if chosen is not None else 1


if __name__ == "__main__":
    sys.exit(main())
