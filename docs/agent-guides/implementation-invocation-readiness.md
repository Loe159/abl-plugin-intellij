# Implementation Invocation Readiness

`check_implementation_invocation_readiness.py` checks whether an exact
implementation-invocation preflight may be treated as ready to invoke. It is
read-only and does not select a runner, invoke an agent, start a session, mutate
the repository, or authorize publication.

The checker can consume one independently validated exact session-start
authorization receipt. Without that receipt it returns
`invocation_ready=false`. In the current checkout, real readiness is still
expected to remain false because required runner controls lack satisfying
enforcement evidence.

## Run

Carry the proposal, disposable-worktree receipt, approval-receipt, and preflight
SHA-256 digests separately from their files:

```text
python .agent/checks/check_implementation_invocation_readiness.py \
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

Exit code `0` means every declared readiness gate and the exact authorization
receipt currently validate. Exit code `2` means a deterministic gate is
missing or invalid. Exit code `1` means a tool, input, policy, or I/O error.
The CLI accepts no policy, proposal, approval, preflight, authorization, or
readiness override.

## Readiness Scope

The checker:

- validates the exact preflight through
  `validate_implementation_invocation_preflight.py`;
- reports whether that preflight is currently valid;
- checks runner-selection readiness through
  `check_implementation_runner_selection.py`;
- checks session-start readiness through
  `check_implementation_session_start.py`;
- validates an exact session-start authorization receipt when supplied;
- binds the readiness checker, preflight validator, approval validator,
  runner-readiness checker, and their policies by SHA-256;
- returns `invocation_ready=false` unless every required gate exists and passes.

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

This checker is a refusal boundary, not a launch mechanism. It makes the current
gap explicit: a valid preflight and selectable runner candidate are still only
evidence, not permission to start.

`invocation_ready=true` is reachable only when fixture or future real runner
evidence satisfies every declared control and an exact authorization receipt
validates. It remains a read-only readiness result: it does not invoke an agent
or prevent authorization replay. Atomic consumption and execution remain
responsibilities of the still-missing enforced runner.
