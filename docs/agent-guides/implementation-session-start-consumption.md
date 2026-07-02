# Implementation Session Start Authorization Consumption

`consume_implementation_session_start_authorization.py` adds a local exclusive
consumption boundary after independent validation of one exact session-start
authorization receipt. It does not invoke an agent, select a runner, mutate the
workspace, or authorize network or publication access.

## Run

```text
python .agent/checks/consume_implementation_session_start_authorization.py \
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
  --format json
```

The consumer appends `.consumed.json` to the authorization receipt path,
validates the exact authorization, then creates the marker exclusively.
Concurrent local consumers may validate, but only one can create the marker.

Validate the resulting marker independently with the procedure in
`docs/agent-guides/implementation-session-start-consumption-validation.md`.

## Honest Boundary
The marker keeps all authorization fields false and rejects ordinary local
replay.

The marker is not tamper resistant, cross-host, or protected by a shared replay
registry. The step does not prove that a runner invokes an agent after
consumption.
