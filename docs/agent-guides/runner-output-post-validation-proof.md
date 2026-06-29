# Runner Output Post-Validation Proof

`prove_runner_output_post_validation.py` is a synthetic fixture for the future
implementation runner boundary. It exercises a tiny local wrapper that calls
`validate_implementation_result.validate_execution(...)` on captured output.

## Run

```text
python .agent/checks/prove_runner_output_post_validation.py \
  --repo . \
  --format json
```

Exit code `0` means the synthetic fixtures matched. Exit code `2` means a
fixture failed. Exit code `1` means policy, repository, runtime, or I/O error.
The CLI accepts no policy, command, runner, adapter, model, or network
override.

## Proven Fixture

The proof checks only that the synthetic wrapper:

- accepts a valid captured implementation result after validator invocation;
- rejects a session-identity mismatch after validator invocation;
- treats a bypass record with no validator invocation as non-compliant.

The readiness ledger records this as related evidence for
`runner_enforced_output_post_validation`; it does not satisfy that control.

## Honest Boundary

The fixture does not invoke an agent, launch a real implementation runner,
prove that every future runner path calls the validator, prove compatibility
with real model output, generate a patch, run checks, approve work, or publish.
