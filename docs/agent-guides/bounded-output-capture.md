# Bounded Output Capture

`isolated_process.py` now captures child `stdout` and `stderr` concurrently
through fixed-size chunks and a bounded internal queue. The combined retained
output has an exact byte ceiling. Crossing that ceiling fails closed: the
direct child is terminated and no partial captured bytes are returned.

`prove_bounded_output_capture.py` exercises the exact launcher with two
harmless fixtures:

- a dual-stream child that emits 49,152 bytes on each stream;
- an excessive-output child that attempts to emit 262,144 bytes.

## Run

```text
python .agent/checks/prove_bounded_output_capture.py \
  --repo . \
  --format json
```

Exit code `0` means both fixtures matched the exact local enforcement contract.
Exit code `2` means a fixture failed closed. Exit code `1` means a policy,
runtime, input, or I/O error. No command, policy, limit, or launcher override
is accepted.

## Enforced Scope

The exact launcher:

- reads both streams concurrently without a shell;
- stores output only up to the combined configured ceiling;
- bounds queued chunks and reports a conservative capture-memory ceiling;
- applies the process deadline even if the child closes both streams early;
- kills and reaps the direct child after timeout or excessive output;
- returns complete output only when both streams reach EOF within policy.

The readiness ledger therefore marks `bounded_output_capture=satisfied`.

## Honest Boundary

Byte-safe capture alone does not prove that a future implementation response
follows a result schema, refers to the approved task, contains no secret,
yields an acceptable patch, or passes deterministic checks.

The separate exact result contract is documented in
`docs/agent-guides/implementation-result-validation.md`. Even with that
contract, `runner_enforced_output_post_validation` remains
`missing_evidence` until a real implementation runner proves that every
captured result is passed through it.

The proof covers one direct child and the current platform. It does not prove
arbitrary descendant-tree cleanup, cross-platform equivalence, network
isolation, tool allowlisting, or model-turn enforcement.
