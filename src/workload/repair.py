"""One-round lint repair (handbook §5 P1): rewrite leaking probes with the
leaked words passed as explicit forbidden terms. Exactly ONE round; if the
post-repair leak rate is still > 2% the caller must STOP and report."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.llm import client
from src.workload import lint

LEAK_RATE_STOP = 0.02

_REPAIR_PROMPT = """Rewrite this benchmark probe so it keeps the SAME question intent but no longer contains the forbidden words. The forbidden words are answer content — the probe must be answerable WITHOUT containing them.
Output STRICT JSON only.

Original probe: {probe}
Forbidden words (must NOT appear, case-insensitive, in the rewrite): {forbidden}

Rules: same question, different wording; natural English; do not use "you told me" / "as I said" / "my memory"; 1-2 sentences max.
JSON shape: {{"probe": "..."}}"""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def repair_round(users: list[dict], *, role: str = "gen") -> dict[str, Any]:
    """Rewrite every leaking probe text in place (single round). Returns stats."""
    scenarios: dict[str, dict] = {}
    for u in users:
        for sc in u.get("scenarios", []):
            scenarios[sc["id"]] = sc

    repaired = 0
    failed: list[dict] = []
    for u in users:
        for m in u["memories"]:
            for p in m["probes"]:
                if not p.get("text"):
                    continue
                leaks = lint.probe_leaks(m, p, scenarios)
                if not leaks:
                    continue
                # collect the actually-leaking words from the leak messages
                forbidden = sorted({w.strip("'") for l in leaks
                                    if "contains target" in l
                                    for w in [l.split("contains target")[-1].strip()]})
                prompt = (_REPAIR_PROMPT
                          .replace("{probe}", p["text"])
                          .replace("{forbidden}", ", ".join(f'"{w}"' for w in forbidden)))
                try:
                    rec = client.parse_json_block(
                        client.chat([{"role": "user", "content": prompt}],
                                    role=role, temperature=0.7, max_tokens=2048,
                                    meta={"step": "lint_repair", "user": u["user_id"]}))
                    new_text = (rec.get("probe") or "").strip()
                    if not new_text or any(_norm(w) in _norm(new_text) for w in forbidden):
                        failed.append({"memory": m["id"], "kind": p["kind"],
                                       "reason": "rewrite still leaks or empty"})
                        continue
                    p["text"] = new_text
                    repaired += 1
                except Exception as e:  # noqa: BLE001
                    failed.append({"memory": m["id"], "kind": p["kind"], "reason": str(e)})

    doc = {"users": users}
    post = lint.workload_leak_report(doc)
    return {"repaired": repaired, "repair_failures": failed,
            "post": {k: post[k] for k in ("probes", "violations", "rate")},
            "stop_condition": post["rate"] > LEAK_RATE_STOP}
