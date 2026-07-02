# Session Start Consumption Validation

`validate_implementation_session_start_consumption.py` independently validates
one exact local consumption marker. It is read-only and does not invoke an
agent, select a runner, mutate the workspace, or consume another authorization.

## Run

Pass the complete authorization inputs plus the marker and its separately
carried SHA-256:

```text
python .agent/checks/validate_implementation_session_start_consumption.py \
  --repo <clean-source-checkout> \
  --proposal <external-path>/implementation-session-proposal.json \
  --proposal-sha256 <expected-proposal-sha256> \
  --workspace <prepared-external-worktree> \
  --worktree-receipt <external-path>/disposable-worktree-receipt.json \
  --worktree-receipt-sha256 <expected-worktree-receipt-sha256> \
  --approval-receipt <external-session-approval-receipt.json> \
  --approval-receipt-sha256 <expected-approval-receipt-sha256> \
  --preflight <external-path>/implementation-invocation-preflight.json \
  --preflight-sha256 <expected-preflight-sha256> \
  --authorization-receipt <external-start-authorization.json> \
  --authorization-receipt-sha256 <expected-authorization-receipt-sha256> \
  --consumption-marker <external-start-authorization.json.consumed.json> \
  --consumption-marker-sha256 <expected-marker-sha256> \
  --format json
```

The validator checks the digest before parsing, canonical JSON, exact schema,
false authorization fields, marker identity, the derived adjacent path,
producer bindings, current authorization validity, and final state drift.

## Honest Boundary

`valid=true` proves only current local consistency. The marker is not signed,
tamper resistant, or shared across hosts. Validation neither invokes an agent
nor proves atomic coupling between consumption and a later launch.

Use `docs/agent-guides/implementation-launch-readiness.md` for the final
read-only agreement check between invocation readiness and this marker.
