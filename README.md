# TTCL Campaign Repo

Engineering sandbox for the NeurIPS 2026 TTCL Workshop submission
"Internalize or Retrieve: Online Memory Placement for Test-Time Continual
Learning Agents".

- Scientific spec: `docs/ttcl_proposal_report.md` (single source of truth)
- Engineering spec: `docs/dev_handbook_v1.0.md` (currently v1.1, see its changelog)
- Agent behavior: `AGENTS.md`

Layout follows dev handbook section 3.1: `src/` (workload, stores, router,
readpath, arms, evalx), `third_party/horen` (editing backend, patched per
handbook section 4.1), `spikes/` (GPU smoke, not run in CI), `tests/` (CPU
only), `configs/` and `prompts/` (frozen, versioned), `data/workloads/`
(frozen small JSON, git-tracked), `results/` (never in git; the Mac is the
master copy of every run).
