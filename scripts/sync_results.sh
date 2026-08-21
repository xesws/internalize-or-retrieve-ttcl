#!/usr/bin/env bash
# Sync one run's results from the pod to the Mac (dev handbook v1.1 §6.1 step 3).
# rsync ONLY — no S3. The Mac copy is the master copy.
set -euo pipefail
RUN_ID="${1:?usage: sync_results.sh <run_id>}"
POD_HOST="${POD_HOST:-internalize-or-retrieve}"
REMOTE_DIR="~/internalize-or-retrieve-ttcl/results/${RUN_ID}/"

mkdir -p "results/${RUN_ID}"
rsync -avz --partial "${POD_HOST}:${REMOTE_DIR}" "results/${RUN_ID}/"
echo "synced results/${RUN_ID} -> Mac (master copy)"
