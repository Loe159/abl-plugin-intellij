#!/usr/bin/env bash
# build-plugin.sh — Local build script for ABL plugin
# Usage: ./scripts/build-plugin.sh [--branch BRANCH] [--skip-tests] [--output-dir DIR]
#
# Used by:
#   - ABL Build agent (compilation check)
#   - ABL Tester agent (test run)
#   - Developers locally
#
# Outputs:
#   - build/distributions/*.zip  (plugin ZIP, installable in IntelliJ)
#   - build/reports/tests/       (test HTML reports)
#   - scripts/build-result.json  (machine-readable result for agents)

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
export JAVA_HOME
export PATH="$JAVA_HOME/bin:$PATH"

# ── Args ──────────────────────────────────────────────────────────────────────
BRANCH=""
SKIP_TESTS=false
ONLY_TESTS=false
OUTPUT_DIR=""
RESULT_FILE="$REPO_DIR/scripts/build-result.json"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch)    BRANCH="$2";      shift 2 ;;
    --skip-tests) SKIP_TESTS=true; shift   ;;
    --only-tests) ONLY_TESTS=true; shift   ;;
    --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

cd "$REPO_DIR"
chmod +x gradlew

# ── Checkout branch if requested ──────────────────────────────────────────────
if [ -n "$BRANCH" ]; then
  echo "→ Switching to branch: $BRANCH"
  git fetch origin
  git checkout "$BRANCH"
  git pull origin "$BRANCH"
fi

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
COMMIT=$(git rev-parse --short HEAD)

echo "→ Branch: $CURRENT_BRANCH ($COMMIT)"
echo "→ Java: $(java -version 2>&1 | head -1)"

START_TIME=$(date +%s)
TEST_STATUS="skipped"
TEST_FAILURES=""
BUILD_STATUS="skipped"
ZIP_PATH=""
ERROR_MSG=""

# ── Tests ─────────────────────────────────────────────────────────────────────
if [ "$SKIP_TESTS" = "false" ]; then
  echo ""
  echo "═══ Running tests ═══════════════════════════════════════════════════════"
  set +e
  ./gradlew test --no-daemon 2>&1 | tee /tmp/abl-test-output.txt
  TEST_EXIT=$?
  set -e

  if [ $TEST_EXIT -eq 0 ]; then
    TEST_STATUS="passed"
    echo "✅ Tests PASSED"
  else
    TEST_STATUS="failed"
    TEST_FAILURES=$(grep -E "FAILED|> Task :test FAILED|tests were unsuccessful" /tmp/abl-test-output.txt | head -20 || true)
    echo "❌ Tests FAILED"
    cat /tmp/abl-test-output.txt | tail -30
  fi
fi

# ── Build ─────────────────────────────────────────────────────────────────────
if [ "$ONLY_TESTS" = "false" ] && ([ "$SKIP_TESTS" = "true" ] || [ "$TEST_STATUS" = "passed" ]); then
  echo ""
  echo "═══ Building plugin ═════════════════════════════════════════════════════"
  set +e
  ./gradlew buildPlugin --no-daemon -x test 2>&1 | tee /tmp/abl-build-output.txt
  BUILD_EXIT=$?
  set -e

  if [ $BUILD_EXIT -eq 0 ]; then
    BUILD_STATUS="passed"
    ZIP_PATH=$(ls "$REPO_DIR/build/distributions/"*.zip 2>/dev/null | head -1 || true)
    if [ -n "$ZIP_PATH" ]; then
      ZIP_NAME=$(basename "$ZIP_PATH")
      ZIP_SIZE=$(du -sh "$ZIP_PATH" | cut -f1)
      echo "✅ Build PASSED → $ZIP_NAME ($ZIP_SIZE)"

      # Copy to output dir if specified
      if [ -n "$OUTPUT_DIR" ]; then
        mkdir -p "$OUTPUT_DIR"
        cp "$ZIP_PATH" "$OUTPUT_DIR/"
        echo "→ Copied to: $OUTPUT_DIR/$ZIP_NAME"
      fi
    fi
  else
    BUILD_STATUS="failed"
    ERROR_MSG=$(grep -E "error:|BUILD FAILED" /tmp/abl-build-output.txt | head -20 || true)
    echo "❌ Build FAILED"
    cat /tmp/abl-build-output.txt | tail -40
  fi
fi

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

# ── Write JSON result (for agents) ────────────────────────────────────────────
python3 - <<PYEOF
import json, os
result = {
  "branch": "$CURRENT_BRANCH",
  "commit": "$COMMIT",
  "duration_sec": $DURATION,
  "tests": {
    "status": "$TEST_STATUS",
    "failures": """$TEST_FAILURES""".strip().split("\n") if "$TEST_FAILURES" else []
  },
  "build": {
    "status": "$BUILD_STATUS",
    "zip_path": "$ZIP_PATH",
    "error": """$ERROR_MSG""".strip().split("\n") if "$ERROR_MSG" else []
  }
}
with open("$RESULT_FILE", "w") as f:
    json.dump(result, f, indent=2)
print("→ Result saved to: $RESULT_FILE")
PYEOF

# ── Final summary ─────────────────────────────────────────────────────────────
echo ""
echo "═══ Summary ═════════════════════════════════════════════════════════════"
echo "Branch:  $CURRENT_BRANCH ($COMMIT)"
echo "Tests:   $TEST_STATUS"
echo "Build:   $BUILD_STATUS"
echo "Time:    ${DURATION}s"
[ -n "$ZIP_PATH" ] && echo "Output:  $ZIP_PATH"

# Exit code: 0=all good, 1=tests failed, 2=build failed
if [ "$TEST_STATUS" = "failed" ]; then exit 1; fi
if [ "$BUILD_STATUS" = "failed" ]; then exit 2; fi
exit 0
