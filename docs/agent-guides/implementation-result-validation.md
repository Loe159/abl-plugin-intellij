# Implementation Result Validation

`validate_implementation_result.py` validates one bounded captured result from a
future supervised implementation adapter. It does not invoke an agent, inspect
whether workspace edits are correct, generate a patch, run checks, publish, or
authorize any later action.

The portable result is one canonical UTF-8 JSON object followed by one newline.
Its exact schema lives at
`.agent/schemas/implementation-result.schema.json`.

## Contract

The result must:

- match the expected issue, risk, base commit, workspace, runner, preflight,
  and session-start authorization receipt digests;
- use one of `completed`, `blocked`, or `failed`;
- use the policy-defined next action for that status;
- contain one bounded single-line summary;
- declare whether the workspace changed;
- keep patch generation, deterministic checks, publication, and network
  requests false;
- arrive through a completed, zero-exit, reaped capture with no kill request,
  exact stream byte counts, and empty `stderr`;
- contain no configured high-confidence secret signature.

A valid `blocked` or `failed` result remains useful protocol evidence but is
not implementation-candidate-ready. A valid `completed` result is candidate
ready only when it declares a workspace change. That means only that the
deterministic patch-generation stage may inspect the workspace next.

## Manual Validation

The CLI consumes a captured result file and a trusted expected-session JSON
object:

```text
python .agent/checks/validate_implementation_result.py \
  --result <external-path>/result.json \
  --expected-session <external-path>/expected-session.json \
  --format json
```

An optional `--stderr` file must be empty. The manual CLI constructs capture
metadata for the supplied files; it does not prove those files came from a real
runner. A future enforced runner must call `validate_execution(...)` with the
actual bounded capture record.

Run the adversarial proof:

```text
python .agent/checks/prove_implementation_result_validation.py \
  --repo . \
  --format json
```

## Honest Boundary

The readiness ledger marks
`implementation_result_contract_validation=satisfied`. It keeps
`runner_enforced_output_post_validation=missing_evidence` because no
implementation runner yet proves that every invocation calls this validator.

An implementation result still cannot approve its own edits. The next
deterministic stages are documented in
`docs/agent-guides/implementation-patch-post-validation.md`; it generates a
complete patch, applies diff policy, and classifies risk, and in
`docs/agent-guides/implementation-patch-post-validation-validation.md`; it
independently checks the retained receipt against current state. Required
quality checks and human review remain later boundaries.
