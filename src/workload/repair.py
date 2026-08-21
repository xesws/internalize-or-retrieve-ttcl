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


_QA_KINDS = {"qa_immediate", "qa_delayed", "qa_paraphrase"}


def repair_round(users: list[dict], *, role: str = "gen", max_attempts: int = 3) -> dict[str, Any]:
    """Rewrite every leaking probe text in place (single repair ROUND; each
    probe may take up to ``max_attempts`` rewrites within the round). QA-family
    probes that still leak fall back to the memory's clean qa_immediate text;
    others are reported as residuals (freeze will refuse if any remain)."""
    scenarios: dict[str, dict] = {}
    for u in users:
        for sc in u.get("scenarios", []):
            scenarios[sc["id"]] = sc

    repaired = 0
    fallbacks = 0
    failed: list[dict] = []

    def try_rewrite(u, m, p, forbidden) -> str | None:
        prompt = (_REPAIR_PROMPT
                  .replace("{probe}", p["text"])
                  .replace("{forbidden}", ", ".join(f'"{w}"' for w in forbidden)))
        for attempt in range(max_attempts):
            try:
                rec = client.parse_json_block(
                    client.chat([{"role": "user", "content": prompt}],
                                role=role, temperature=0.7, max_tokens=2048,
                                meta={"step": "lint_repair", "user": u["user_id"]}))
            except Exception:  # noqa: BLE001 — retry within the round
                continue
            new_text = (rec.get("probe") or "").strip()
            if new_text and not any(_norm(w) in _norm(new_text) for w in forbidden):
                return new_text
        return None

    for u in users:
        for m in u["memories"]:
            clean_qa = next((p["text"] for p in m["probes"]
                             if p["kind"] == "qa_immediate" and not lint.probe_leaks(
                                 m, p, scenarios)), None)
            for p in m["probes"]:
                if not p.get("text"):
                    continue
                leaks = lint.probe_leaks(m, p, scenarios)
                if not leaks:
                    continue
                forbidden = sorted({w.strip("' ") for l in leaks
                                    if "contains target" in l
                                    for w in [l.split("contains target")[-1].strip()]})
                new_text = try_rewrite(u, m, p, forbidden)
                if new_text:
                    p["text"] = new_text
                    repaired += 1
                elif p["kind"] in _QA_KINDS and clean_qa and p["kind"] != "qa_immediate":
                    p["text"] = clean_qa
                    p["repaired_via_fallback"] = True
                    fallbacks += 1
                else:
                    failed.append({"memory": m["id"], "kind": p["kind"],
                                   "reason": "still leaking after repair round"})

    doc = {"users": users}
    post = lint.workload_leak_report(doc)
    return {"repaired": repaired, "fallbacks": fallbacks, "repair_failures": failed,
            "post": {k: post[k] for k in ("probes", "violations", "rate")},
            "stop_condition": post["rate"] > LEAK_RATE_STOP}
