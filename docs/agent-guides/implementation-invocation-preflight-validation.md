# Implementation Invocation Preflight Validation

`validate_implementation_invocation_preflight.py` independently validates one
exact implementation-invocation preflight package. It is read-only and does not
select a runner, invoke an agent, start a session, mutate the repository, or
authorize publication.

This check exists so a later consumer can reject stale, rehashed, or
overclaiming preflight packages before any runner-selection or invocation
design is considered.

## Run

Carry the proposal, disposable-worktree receipt, approval-receipt, and preflight
SHA-256 digests separately from their files:

```text
python .agent/checks/validate_implementation_invocation_preflight.py \
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
  --format json
```

Exit code `0` means the preflight is currently valid, `2` means a deterministic
rule rejected it, and `1` means a tool, input, policy, or I/O error. The CLI
accepts no policy, proposal, approval, preflight, or readiness override.

## Validation Scope

The validator:

- checks the separately supplied preflight digest before trusting content;
- requires an exact schema and all authorization, runner-selection, and
  session-start fields to remain false;
- revalidates the exact implementation-session approval receipt;
- requires the current approval validation to be `valid=true`;
- verifies proposal, disposable-worktree receipt, and approval-receipt records
  against current bytes;
- recalculates preflight policy bindings from trusted local bytes;
- checks for high-confidence secret signatures in the preflight package;
- rechecks preflight bytes, approval validation, repository state, and validator
  bindings before returning success.

Every result retains:

```text
authorized=false
agent_invocation_authorized=false
implementation_authorized=false
repository_mutation_authorized=false
network_authorized=false
publication_authorized=false
runner_selected=false
session_start_authorized=false
```

## Honest Boundary

`valid=true` means only that the exact preflight package currently matches the
exact proposal, prepared workspace receipt, approval receipt, runner-readiness
state, and local validation policy. It is not runner selection, sandbox
enforcement, workspace confinement, timeout enforcement, model invocation,
output capture, cleanup assurance, or permission to start.

In the current pilot checkout, real validation is expected to fail for
preflights that depend on runner readiness until required runner controls have
satisfying enforcement evidence.

The explicit readiness check is documented in
`docs/agent-guides/implementation-invocation-readiness.md`. It requires current
runner-selection and session-start readiness plus an exact independently
validated start-authorization receipt. A valid preflight alone remains
insufficient.
