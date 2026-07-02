#!/usr/bin/env bash
set -euo pipefail

if [[ -x ./gradlew ]]; then
  ./gradlew ktlintCheck detekt test
elif [[ -f ./gradlew.bat ]]; then
  ./gradlew.bat ktlintCheck detekt test
else
  echo "fast.sh: Gradle wrapper not found" >&2
  exit 1
fi
