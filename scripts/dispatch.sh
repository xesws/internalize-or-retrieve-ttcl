#!/usr/bin/env bash
# Start a run on the pod inside tmux (dev handbook §6.1 step 3).
# usage: dispatch.sh <run_id> <command...>
# Preconditions enforced here: pod repo is on the latest commit with a clean
# working tree (smoke runs may relax this; official runs must not).
set -euo pipefail
RUN_ID="${1:?usage: dispatch.sh <run_id> <command...>}"
shift
POD_HOST="${POD_HOST:-internalize-or-retrieve}"
REPO_DIR='$HOME/internalize-or-retrieve-ttcl'
CMD="$*"

ssh "${POD_HOST}" "set -e; cd ${REPO_DIR} && \
  git pull --ff-only && \
  test -z \"\$(git status --porcelain)\" && \
  mkdir -p results/${RUN_ID}/logs && \
  tmux new -d -s ${RUN_ID} \"bash -lc '${CMD} 2>&1 | tee results/${RUN_ID}/logs/run.log; echo EXIT=\\\$? >> results/${RUN_ID}/logs/run.log'\" && \
  echo \"started run ${RUN_ID} in tmux\""
