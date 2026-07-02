#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: .agent/scripts/run-stage.sh <research|plan|compact-progress|review|implement> [stage args...]" >&2
  exit 1
fi

stage="$1"
shift
python_bin="$(.agent/scripts/resolve-python.sh)"

case "$stage" in
  research|plan|compact-progress|review)
    "$python_bin" .agent/checks/build_stage_context.py --stage "$stage" "$@"
    ;;
  implement)
    "$python_bin" .agent/checks/build_supervised_runner_invocation.py "$@"
    ;;
  *)
    echo "run-stage.sh: unknown stage: $stage" >&2
    exit 2
    ;;
esac
