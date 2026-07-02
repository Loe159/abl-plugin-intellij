#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: .agent/scripts/publish-draft-pr.sh <publish_draft_pr.py args...>" >&2
  exit 1
fi

python_bin="$(.agent/scripts/resolve-python.sh)"
"$python_bin" .agent/checks/publish_draft_pr.py "$@"
