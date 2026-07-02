#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: .agent/scripts/classify-task.sh <external-run-directory>" >&2
  exit 1
fi

run_dir="$1"
python_bin="$(.agent/scripts/resolve-python.sh)"
"$python_bin" .agent/checks/classify_task_route.py --run "$run_dir" --format json
