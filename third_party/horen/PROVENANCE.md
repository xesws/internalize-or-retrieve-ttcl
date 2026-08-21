# Vendored HoReN backend

- Upstream: HoReN (arXiv 2605.08143), EasyEdit-style trim, as vendored by the
  AIEHackathon prototype at commit `5ee64839aa2a2e672fbae419a3783693aaf9f7df`
  (branch `main`, 2026-08-21).
- Ported scope (minimal live edit path only): `horen_backend/models/horen/*`
  (editor, hparams, main, utils) + `horen_backend/util/{hparams,edit_timer}.py`
  + `hparams/HOREN/llama3.1-8b.yaml`. The EasyEdit zoo (`rome/`, `memit/`,
  `melo/`, experiments, ZsRE data) was deliberately NOT ported.
- Deviations from upstream (everything else is byte-identical):
  1. Top-level package dir renamed `src/` -> `horen_backend/` to avoid a Python
     package-name collision with this repo's own `src/` package. All relative
     imports inside are unchanged (same depth).
  2. `hparams/HOREN/llama3.1-8b.yaml`: `model_name` switched from an absolute
     RunPod cache path to the HF hub id `meta-llama/Llama-3.1-8B-Instruct`.
     No editing hyperparameter modified (handbook §4.2 lock).
  3. `horen_backend/models/horen/utils.py`: PATCHED per dev handbook §4.1
     (Llama pad/eos mask fix). See the two `PATCH (ttcl §4.1)` markers in that
     file. This is the mandatory first patch after porting; violating it
     invalidates all Llama edit arms.
- Empty `__init__.py` files replace the upstream star-importing root init to
  keep the EasyEdit zoo out of the import graph.
