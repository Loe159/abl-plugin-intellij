#!/usr/bin/env bash
set -euo pipefail

STAGE="$1"
PROMPT_FILE="$2"
OUTPUT_DIR="$3"

mkdir -p "$OUTPUT_DIR"

case "$STAGE" in
  research)
    codex exec \
      --sandbox read-only \
      --ask-for-approval never \
      --output "$OUTPUT_DIR/research.md" \
      "$(cat "$PROMPT_FILE")"
    ;;

  plan)
    codex exec \
      --sandbox read-only \
      --ask-for-approval never \
      --output "$OUTPUT_DIR/plan.md" \
      "$(cat "$PROMPT_FILE")"
    ;;

  implement)
    codex exec \
      --sandbox workspace-write \
      --ask-for-approval never \
      --output "$OUTPUT_DIR/summary.md" \
      "$(cat "$PROMPT_FILE")"
    ;;
esac