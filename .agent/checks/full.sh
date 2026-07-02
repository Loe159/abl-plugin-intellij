#!/usr/bin/env bash
set -euo pipefail

if [[ -x ./gradlew ]]; then
  ./gradlew ktlintCheck detekt test build verifyPlugin
elif [[ -f ./gradlew.bat ]]; then
  ./gradlew.bat ktlintCheck detekt test build verifyPlugin
else
  echo "full.sh: Gradle wrapper not found" >&2
  exit 1
fi
