# Implementation Quality Gate

`run_implementation_quality_gate.py` is the controlled Windows execution
boundary after independent validation of a candidate-ready implementation
patch receipt.

It runs exactly:

```text
gradlew.bat ktlintCheck detekt --offline --no-daemon --console=plain
gradlew.bat test --offline --no-daemon --console=plain
gradlew.bat verifyPlugin --offline --no-daemon --console=plain
```

The explicit `cmd.exe` invocation uses `shell=false`. The child environment is
reconstructed from a small allowlist, and the policy records
`network_requested=false`. Gradle offline mode is a dependency-resolution
constraint, not proof of operating-system network isolation.

The bounded launcher rejects local Windows App Execution Alias executables
under `AppData\Local\Microsoft\WindowsApps` for both `COMSPEC` and direct
command execution.

On Windows the allowlist includes `SYSTEMDRIVE`, `ALLUSERSPROFILE`, and
`PROGRAMDATA`. These non-secret platform paths prevent WindowsApps children
from resolving `%SystemDrive%\ProgramData` relative to the implementation
workspace.

The synthetic mechanism proof uses the regular interpreter under `sys.prefix`
instead of the Windows App Execution Alias. This keeps the fixture from
starting package-cache work outside the bounded child-process observation.

The caller must provide an existing external `--gradle-user-home`. The
executor refuses to spawn Gradle unless that cache already contains the exact
8.11.1 wrapper distribution. This prevents the wrapper bootstrap from
attempting a download before Gradle can interpret `--offline`. The external
cache is operational mutable state, not immutable provenance evidence.

## Preconditions

The executor accepts the exact result, expected session, retained patch, patch
receipt, and expected patch-receipt SHA-256 used by
`validate_implementation_patch_receipt.py`. It refuses to start unless that
validator returns both:

```text
valid=true
patch_candidate_ready=true
```

An empty or policy-blocked patch cannot reach Gradle.

## Runtime Bounds

Each fixed command has a 900-second limit. The full sequence has an
1800-second limit. Combined stdout and stderr are captured concurrently with a
2 MiB bound; raw output is not written into the receipt.

On timeout or output overflow, the executor requests:

```text
taskkill /PID <root-pid> /T /F
```

If that command fails, it directly kills and reaps the root process as a
fallback. That fallback does not prove descendant cleanup. The receipt records
both outcomes.

The three commands stop after the first failure. A failed gate still writes a
bounded external receipt with later commands marked `not_run`.

## Receipt

The external canonical JSON receipt binds:

- the exact implementation session identity;
- patch and patch-receipt digests;
- fixed command IDs and Gradle tasks;
- return code, timeout, output-limit, cleanup, duration, and bounded-output
  digests for each executed command;
- the trusted executor, policy, wrapper, and validator bytes.

The executor checks that the Git-visible workspace state is unchanged after
the commands. Gradle may still create ignored build or cache files; this is
not a byte-for-byte filesystem immutability claim.

## Receipt Validation

Validate the exact receipt independently with:

```text
python .agent/checks/validate_implementation_quality_gate.py \
  --repo <trusted-source-checkout> \
  --result <external-path>/result.json \
  --expected-session <external-path>/expected-session.json \
  --patch <external-path>/patch.diff \
  --patch-receipt <external-path>/patch-validation.json \
  --patch-receipt-sha256 <expected-patch-receipt-sha256> \
  --quality-gate-receipt <external-path>/quality-gate.json \
  --quality-gate-receipt-sha256 <expected-quality-gate-receipt-sha256> \
  --gradle-user-home <external-existing-cache> \
  --format json
```

The validator revalidates the candidate patch, exact receipt digest, command
order and fail-fast semantics, runtime bounds, current Gradle cache, and
trusted producer bytes. A correctly described failed gate may be `valid=true`
with `quality_gate_passed=false`.

The text summaries list the full non-authorizing field family inherited from
the implementation-result contract:

```text
authorized=false
agent_invocation_authorized=false
implementation_authorized=false
repository_mutation_authorized=false
network_authorized=false
publication_authorized=false
runner_selected=false
session_start_authorized=false
implementation_approved=false
```

The receipt contains output byte counts and digests, not raw build logs. The
validator therefore checks internal consistency and current bindings but
cannot authenticate the historical origin of those output digests.

## Mechanism Proof

```text
python .agent/checks/prove_implementation_quality_gate.py \
  --repo . \
  --format json
```

The proof runs harmless Python fixtures for bounded dual-stream capture,
timeout, and output overflow. It does not run Gradle or validate a candidate.

Run the separate receipt-validation proof:

```text
python .agent/checks/prove_implementation_quality_gate_validation.py \
  --repo . \
  --format json
```

It accepts exact passed and failed synthetic receipts and rejects rehashed
command substitution. It does not run Gradle.

## Honest Boundary

The current readiness status is:

```text
implementation_quality_gate_execution=related_evidence_only
quality_gate_receipt_validation=satisfied
```

The first control cannot become satisfied until the exact executor completes
the real Gradle commands for a candidate-ready patch and that evidence is
consumed by the readiness model with a scope strong enough to authenticate the
execution evidence. Receipt validation is independently enforced, but it does
not authenticate historical build output.

On June 18, 2026, a disposable README-only candidate completed all three
command groups through this exact executor using the existing external Gradle
cache. The resulting external receipt SHA-256 was
`7b1ffd7408a76818e1c76aa2549fd3408759ff5785358219fc7dea73cd64dbd8`.
The receipt passes independent current-state validation. This remains a manual
local rehearsal rather than a durable authenticated execution source, so it
does not satisfy `implementation_quality_gate_execution`.

Even a passed and independently validated quality gate would not approve the
patch, authenticate a reviewer, authorize merge or publication, invoke an
agent, or prove network isolation.
