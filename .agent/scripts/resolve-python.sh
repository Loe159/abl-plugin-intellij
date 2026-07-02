#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${PYTHON:-}" ]]; then
  printf '%s\n' "$PYTHON"
  exit 0
fi

for candidate in python python3 py; do
  if command -v "$candidate" >/dev/null 2>&1; then
    printf '%s\n' "$candidate"
    exit 0
  fi
done

echo "python interpreter not found; set PYTHON or install python/python3/py" >&2
exit 127
