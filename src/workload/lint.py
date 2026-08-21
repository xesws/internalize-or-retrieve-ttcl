"""Target-free contamination lint (proposal §5.5 / handbook §4.2 red line).

Every probe text (QA variants, scenario text, key prompts) must NOT contain
the answer keywords of the memory it probes — a probe that leaks its target
word measures reading comprehension, not internalization. The lint is
case-insensitive with substring containment; answers and probes are
single-language English for now. Leak rate > 2% after one repair round is a
STOP condition (handbook §5 P1).
"""
from __future__ import annotations

import re
from typing import Any


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def probe_leaks(memory: dict, probe: dict, scenarios: dict[str, dict]) -> list[str]:
    """Return human-readable leak descriptions for one probe (empty = clean)."""
    target_words = [w for w in [m.strip() for m in probe.get("answer_keywords", [])] if w]
    target_words += [w for w in [memory.get("edit_target", "").strip()] if w]
    # de-duplicate, drop single chars
    target_words = sorted({w.lower() for w in target_words if len(w) > 1})
    if not target_words:
        return ["probe has no answer_keywords to lint against"]

    texts: list[tuple[str, str]] = []
    if probe.get("text"):
        texts.append(("probe.text", probe["text"]))
    if probe.get("scenario_id"):
        sc = scenarios.get(probe["scenario_id"])
        if sc is None:
            return [f"scenario {probe['scenario_id']} referenced but missing"]
        texts.append(("scenario.text", sc["text"]))

    leaks = []
    for field, text in texts:
        t = _norm(text)
        for w in target_words:
            if " " in w:
                # multi-word phrase: plain containment (cannot straddle words)
                if _norm(w) in t:
                    leaks.append(f"{field} contains target {w!r}")
            else:
                # single word: word-boundary match ("hat" must not fire in "what")
                if re.search(rf"\b{re.escape(w)}\b", t):
                    leaks.append(f"{field} contains target {w!r}")
    return leaks


def workload_leak_report(doc: dict) -> dict[str, Any]:
    """Lint every probe of every memory. Returns {rate, violations, by_kind}."""
    scenarios: dict[str, dict] = {}
    for user in doc.get("users", []):
        for sc in user.get("scenarios", []):
            scenarios[sc["id"]] = sc

    violations: list[dict] = []
    n_probes = 0
    by_kind: dict[str, int] = {}
    for user in doc.get("users", []):
        for mem in user.get("memories", []):
            for probe in mem.get("probes", []):
                n_probes += 1
                kind = probe.get("kind", "?")
                leaks = probe_leaks(mem, probe, scenarios)
                if leaks:
                    by_kind[kind] = by_kind.get(kind, 0) + 1
                    violations.append({
                        "memory": mem["id"], "kind": kind, "leaks": leaks,
                        "probe_text": probe.get("text") or probe.get("scenario_id"),
                    })
    rate = (len(violations) / n_probes) if n_probes else 0.0
    return {"probes": n_probes, "violations": len(violations),
            "rate": round(rate, 4), "by_kind": by_kind, "details": violations}


def lint_clean(doc: dict) -> bool:
    return workload_leak_report(doc)["violations"] == 0
