#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: .agent/scripts/collect-metrics.sh <check|record|validate> [record_run_metrics.py args...]" >&2
  exit 1
fi

python_bin="$(.agent/scripts/resolve-python.sh)"
"$python_bin" .agent/checks/record_run_metrics.py "$@"
