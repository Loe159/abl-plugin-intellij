#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: .agent/checks/tests-policy.sh <patch.diff>" >&2
  exit 1
fi

patch_path="$1"
python_bin="$(.agent/scripts/resolve-python.sh)"
"$python_bin" .agent/checks/diff_policy.py --patch "$patch_path"
