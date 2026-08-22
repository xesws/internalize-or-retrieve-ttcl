#!/usr/bin/env python3
"""Anonymized submission export (JQ ruling 2026-08-22; AGENTS.md section 7).

Builds exports/memplace_v2/ with:
  repo/       anonymized code+data copy (no results/, no .env, no internal
              stage reports; scrubbed of codename-breaking strings)
  supplementary/  frozen tables (tex), frozen scorecard, freeze manifests,
              verbatim prompt appendix, workload spec (anonymized copy)
  ANON_CHECK.md  grep audit over EVERY exported file (must be 0 hits)

Codename: MEMPLACE (placeholder; JQ may rename). The working repo keeps its
real identity — only the export is anonymized.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "exports" / "memplace_v2"
CODENAME = "MEMPLACE"

# identity-breaking patterns (case-insensitive) — from AGENTS.md §7 +
# handbook §6.0 coordinates
PATTERNS = [
    r"engram", r"xesws", r"aiehackathon", r"tangyiq", r"internalize-or-retrieve",
    r"69\.30\.85\.213", r"22113", r"runpod", r"hf_[A-Za-z0-9]+", r"sk-kimi-\S+",
    r"980b8def\S+", r"sk-a2128\S+", r"qty20010619",
]
COMPILED = [re.compile(p, re.IGNORECASE) for p in PATTERNS]

REPO_KEEP = [
    "src", "scripts", "tests", "prompts", "configs", "data/p2", "data/p3",
    "data/p4", "data/p5", "data/workloads", "third_party/horen", "spikes",
    "pyproject.toml", ".env.example", "README.md",
]
SUPP_FILES = [
    "paper/main.tex", "paper/tables.tex", "paper/appendix.tex",
    "paper/appendix_tables.tex", "paper/numbers.tex", "paper/refs.bib",
    "paper/neurips_2026.sty",
    "data/p5/frozen_scorecard_v1.json", "data/p5/s8_frozen_v1.json",
    "data/p5/analysis_frozen_v1.json",
    "data/p3/freeze_v1.1.json", "data/p3/freeze_v1.json",
    "docs/workload_spec_v1.0.md", "docs/claims_traceability_v1.0.md",
]
PROMPTS = [
    "gen_persona_v1.md", "gen_sessions_v1.md", "gen_memory_v1.md",
    "gen_supersede_nearmiss_v1.md", "gen_scenario_v1.md", "gen_rebind_v1.md",
    "router_v1.md", "planner_v1.md", "judge_v1.md", "unrelated_gen_v1.md",
]
SCRUB_PAIRS = [
    ("Internalize or Retrieve: Online Memory Placement for Test-Time Continual Learning Agents",
     f"{CODENAME}: Online Memory Placement for Test-Time Continual Learning Agents"),
    ("internalize-or-retrieve-ttcl", "memplace"),
    ("Internalize or Retrieve", CODENAME),
]


def scrub_text(text: str, rel: str, fixes: list[str]) -> str:
    for pat in COMPILED:
        text = pat.sub("[REDACTED]", text)
    for old, new in SCRUB_PAIRS:
        if old in text:
            fixes.append(f"{rel}: replaced identity string")
            text = text.replace(old, new)
    return text


def copy_scrubbed(src: Path, dst: Path, fixes: list[str]) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        for f in sorted(src.rglob("*")):
            if not f.is_file():
                continue
            if "__pycache__" in f.parts or f.suffix in {".pyc", ".pyo"}:
                continue
            if f.name == "anonymize_export.py":
                continue
            rel = f.relative_to(ROOT)
            target = dst / f.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                text = f.read_text()
            except UnicodeDecodeError:
                shutil.copy2(f, target)
                continue
            new = scrub_text(text, str(rel), fixes)
            target.write_text(new)
    else:
        text = src.read_text()
        dst.write_text(scrub_text(text, str(src), fixes))


def audit(base: Path) -> tuple[int, list[str]]:
    hits: list[str] = []
    for f in sorted(base.rglob("*")):
        if not f.is_file() or f.name in {"ANON_CHECK.md", "anonymize_export.py"}:
            continue
        try:
            text = f.read_text()
        except UnicodeDecodeError:
            continue
        for pat, name in zip(COMPILED, PATTERNS):
            for m in pat.finditer(text):
                hits.append(f"{f.relative_to(base)}: /{name}/ -> ...{text[max(0, m.start()-30):m.end()+30]!r}...")
    return len(hits), hits


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    fixes: list[str] = []

    # repo copy
    for item in REPO_KEEP:
        copy_scrubbed(ROOT / item, OUT / "repo" / item, fixes)
    # README note
    (OUT / "repo" / "ANONYMIZATION.md").write_text(
        "This artifact is an anonymized export (double-blind submission). "
        f"The system is referred to as {CODENAME}. Internal campaign "
        "documents, results journals, and credentials are excluded by design.\n")
    # supplementary
    for f in SUPP_FILES:
        copy_scrubbed(ROOT / f, OUT / "supplementary" / Path(f).name, fixes)
    (OUT / "supplementary" / "prompts_verbatim").mkdir(parents=True, exist_ok=True)
    for p in PROMPTS:
        src = ROOT / "prompts" / p
        if src.exists():
            copy_scrubbed(src, OUT / "supplementary" / "prompts_verbatim" / p, fixes)

    n_hits, hits = audit(OUT)
    report = [
        "# Anonymization audit (auto-generated)",
        "",
        f"Export: exports/memplace_v2 · Codename: {CODENAME} · Date: 2026-08-22",
        "",
        f"**Identity-pattern hits after scrubbing: {n_hits}** "
        "(`PASS` requires 0)",
        "",
        "Patterns checked: " + ", ".join(f"`/{p}/`" for p in PATTERNS),
        "",
        "Scrub fixes applied: " + (f"{len(fixes)}" if fixes else "0"),
        *fixes[:20],
    ]
    if hits:
        report += ["", "## HITS (must be fixed before submission):"]
        report += [f"- {h}" for h in hits[:40]]
    (OUT / "ANON_CHECK.md").write_text("\n".join(report) + "\n")
    print(f"export written: {OUT}")
    print(f"identity hits: {n_hits} ({'PASS' if n_hits == 0 else 'FAIL'})")
    return 0 if n_hits == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
