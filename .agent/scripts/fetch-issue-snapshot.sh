#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 6 ]]; then
  echo "usage: .agent/scripts/fetch-issue-snapshot.sh --repo <repo> --issue <number> --normalization <external-normalization.json> --package <external-absent-package.json> [--github-repo owner/name] [--format text|json]" >&2
  exit 1
fi

python_bin="$(.agent/scripts/resolve-python.sh)"
"$python_bin" .agent/checks/fetch_github_issue_snapshot.py "$@"
