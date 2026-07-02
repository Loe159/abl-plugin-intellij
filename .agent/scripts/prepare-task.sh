#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  elif command -v python.exe >/dev/null 2>&1; then
    PYTHON_BIN="python.exe"
  else
    echo "prepare-task.sh: python interpreter not found; set PYTHON=/path/to/python" >&2
    exit 127
  fi
fi

if [[ $# -lt 1 ]]; then
  echo "usage: .agent/scripts/prepare-task.sh init --repo <repo> --input <normalized-task.json> --run <external-run> --receipt <external-receipt.json> [--format text|json]" >&2
  echo "       .agent/scripts/prepare-task.sh queue-list --repo <repo> [--queue <external-queue.json>] [--format text|json]" >&2
  echo "       .agent/scripts/prepare-task.sh fetch-check --repo <repo> --issue <number> --normalization <external-normalization.json> --package <external-package.json> --normalized-input <external-normalized.json> --approval-receipt <external-approval.json> --approver <id> [--format text|json]" >&2
  echo "       .agent/scripts/prepare-task.sh approve-init --repo <repo> --package <external-package.json> --normalized-input <external-normalized.json> --approval-receipt <external-approval.json> --approver <id> --confirm <phrase> --run <external-run> --initialization-receipt <external-init.json> [--format text|json]" >&2
  echo "       .agent/scripts/prepare-task.sh task-check --repo <repo> --run <external-run> --receipt <external-init.json> --receipt-sha256 <sha256> --approval-receipt <external-task-approval.json> --approver <id>" >&2
  echo "       .agent/scripts/prepare-task.sh task-approve --repo <repo> --run <external-run> --receipt <external-init.json> --receipt-sha256 <sha256> --approval-receipt <external-task-approval.json> --approver <id> --confirm <phrase>" >&2
  exit 1
fi

command="$1"
shift

if [[ "$command" == --* ]]; then
  "$PYTHON_BIN" .agent/checks/initialize_portable_run.py "$command" "$@"
  exit $?
fi

case "$command" in
  init)
    "$PYTHON_BIN" .agent/checks/initialize_portable_run.py "$@"
    ;;
  queue-list)
    "$PYTHON_BIN" .agent/checks/list_github_approved_issues.py "$@"
    ;;
  fetch-check|approve-init)
    "$PYTHON_BIN" .agent/checks/prepare_github_task.py "$command" "$@"
    ;;
  task-check)
    "$PYTHON_BIN" .agent/checks/approve_task.py check "$@"
    ;;
  task-approve)
    "$PYTHON_BIN" .agent/checks/approve_task.py approve "$@"
    ;;
  *)
    echo "prepare-task.sh: unknown command: $command" >&2
    exit 2
    ;;
esac
