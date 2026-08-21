#!/usr/bin/env bash
# Pod environment setup (dev handbook §6.1 step 2).
# Installs deps, logs into HF (HF_TOKEN is the ONLY credential allowed on the
# pod per handbook v1.1 §1 — paid API keys stay Mac-side), downloads the
# Llama-3.1-8B-Instruct backbone, then runs CPU tests and the GPU smoke spike.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -z "${HF_TOKEN:-}" ]; then
    echo "ERROR: HF_TOKEN is not set. Export it before running pod_setup.sh." >&2
    exit 1
fi

echo "== pip deps =="
# RunPod system Python is PEP 668 managed; container context makes the
# override safe (no OS packages depend on this interpreter's site-packages).
PIPFLAGS="--break-system-packages"
python3 -m pip install --quiet --upgrade pip $PIPFLAGS
# torch ships with the RunPod image; only install if missing
python3 -c "import torch" 2>/dev/null || python3 -m pip install --quiet $PIPFLAGS torch
python3 -m pip install --quiet $PIPFLAGS -e ".[gpu,dev]" "huggingface_hub[cli]"

echo "== HF login (HF_TOKEN only) =="
huggingface-cli login --token "$HF_TOKEN" 2>/dev/null \
  || hf auth login --token "$HF_TOKEN"

echo "== backbone download: meta-llama/Llama-3.1-8B-Instruct =="
python3 - <<'EOF'
from huggingface_hub import snapshot_download
snapshot_download(
    "meta-llama/Llama-3.1-8B-Instruct",
    ignore_patterns=["original/*", "*.pth"],
)
print("backbone download ok")
EOF

echo "== CPU tests =="
python3 -m pytest -q tests

echo "== GPU smoke =="
python3 spikes/spike_gpu_smoke.py

echo "pod setup complete"
