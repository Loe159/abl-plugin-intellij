#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: .agent/scripts/validate-patch.sh <patch.diff> [--repo <repo> --base <commit>] [--format text|json]" >&2
  exit 1
fi

python_bin="$(.agent/scripts/resolve-python.sh)"
"$python_bin" .agent/checks/diff_policy.py --patch "$@"
