"""Freeze workloads into data/workloads/ with a manifest (prompt hashes,
generator model, git sha). Frozen files are git-tracked small JSON; freezing
is refused when schema validation or the target-free lint fails (G1 gate)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.manifest import git_sha
from src.workload import lint, schema, split as split_mod
from src.workload.generator import turn_matches

_REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT_VERSION = "v1"
_PROMPTS = [
    "gen_persona_v1.md", "gen_sessions_v1.md", "gen_memory_v1.md",
    "gen_supersede_nearmiss_v1.md", "gen_scenario_v1.md", "gen_rebind_v1.md",
]


def prompt_hashes() -> dict[str, str]:
    out = {}
    for name in _PROMPTS:
        p = _REPO_ROOT / "prompts" / name
        out[name] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    return out


def finalize_user(user: dict) -> dict:
    """Strip generator-internal keys; keep hidden labels (oracle arm needs
    them; the system under test never reads the workload file directly)."""
    return {
        "user_id": user["user_id"],
        "n_sessions": user["n_sessions"],
        "memories": user["memories"],
        "scenarios": user["scenarios"],
    }


def freeze(
    users: list[dict],
    dev_user_ids: list[str],
    *,
    generator_model: str,
    version: str = "v1",
    out_dir: Path | None = None,
) -> dict[str, Any]:
    dev_doc, test_doc = split_mod.split_workload(users, dev_user_ids)
    split_mod.assert_persona_disjoint(dev_doc, test_doc)

    out = out_dir or (_REPO_ROOT / "data" / "workloads")
    out.mkdir(parents=True, exist_ok=True)
    meta = {
        "version": version,
        "generator_model": generator_model,
        "prompt_version": PROMPT_VERSION,
        "prompt_hashes": prompt_hashes(),
        "git_sha": git_sha(),
    }
    report: dict[str, Any] = {"meta": meta, "splits": {}}
    for name, doc in (("dev", dev_doc), ("test", test_doc)):
        full = {**meta, "split": name,
                "users": [finalize_user(u) for u in doc["users"]]}
        schema_errs = schema.validate_workload(
            {k: v for k, v in full.items() if k != "prompt_hashes"})
        mem_errs = []
        for u in full["users"]:
            for m in u["memories"]:
                mem_errs += [f"{m['id']}: {e}" for e in schema.validate_memory(m)]
            for sc in u["scenarios"]:
                mem_errs += [f"{sc['id']}: {e}" for e in schema.validate_scenario(sc)]
        lint_rep = lint.workload_leak_report(full)
        counts = schema.probe_counts(full)
        types = schema.memory_type_counts(full)
        mismatches = [m["id"] for u in full["users"] for m in u["memories"]
                      if not turn_matches(m)]
        if schema_errs or mem_errs or lint_rep["violations"] or mismatches:
            raise ValueError(
                f"{name}: refusing to freeze — schema_errors={schema_errs[:3]} "
                f"mem_errors={len(mem_errs)} lint_violations={lint_rep['violations']} "
                f"turn_mismatches={mismatches[:5]}")
        path = out / f"{name}_{version}.json"
        path.write_text(json.dumps(full, indent=1, ensure_ascii=False))
        report["splits"][name] = {
            "path": str(path), "users": len(full["users"]),
            "memories": types, "probes": counts,
            "lint": {k: lint_rep[k] for k in ("probes", "violations", "rate")},
            "turn_mismatches": len(mismatches),
        }
    (out / f"freeze_manifest_{version}.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False))
    return report
