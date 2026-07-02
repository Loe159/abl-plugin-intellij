# Implementation Session Approval Validation

`validate_implementation_session_approval.py` independently validates one exact
implementation-session approval receipt. It is read-only and does not select a
runner, invoke an agent, start a session, mutate the repository, or authorize
publication.

This check exists so a later consumer can reject stale, rehashed, or
overclaiming session-approval receipts before any invocation design is even
considered.

## Run

Carry the proposal SHA-256, disposable-worktree receipt SHA-256, and approval
receipt SHA-256 separately from their files:

```text
python .agent/checks/validate_implementation_session_approval.py \
  --repo <clean-source-checkout> \
  --proposal <external-path>/implementation-session-proposal.json \
  --proposal-sha256 <expected-proposal-sha256> \
  --workspace <prepared-external-worktree> \
  --worktree-receipt <external-path>/disposable-worktree-receipt.json \
  --worktree-receipt-sha256 <expected-worktree-receipt-sha256> \
  --approval-receipt <external-session-approval-receipt.json> \
  --approval-receipt-sha256 <expected-approval-receipt-sha256> \
  --format json
```

Exit code `0` means the receipt is currently valid, `2` means a deterministic
rule rejected it, and `1` means a tool, input, policy, or I/O error. The CLI
accepts no policy, proposal, or readiness override.

## Validation Scope

The validator:

- checks the separately supplied approval-receipt digest before trusting the
  receipt content;
- requires an exact receipt schema and all authorization, runner-selection,
  and session-start fields to remain false;
- revalidates the exact implementation-session proposal with the supplied
  prepared workspace and disposable-worktree receipt;
- reruns runner-readiness assessment and requires `controls_ready=true`;
- recalculates the exact approval confirmation digest;
- compares approval-control bindings with trusted local bytes;
- requires repository `HEAD` and clean worktree state to still match;
- rechecks receipt bytes, repository state, and validator bindings before
  returning success.

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

`valid=true` means only that the exact approval receipt currently matches the
exact proposal, prepared workspace receipt, runner-readiness report, and local
validation policy. It is not human authentication, runner selection, sandbox
enforcement, workspace confinement, timeout enforcement, output capture,
cleanup assurance, or permission to invoke an agent.

In the current pilot checkout, real validation is expected to fail for receipts
that depend on runner readiness until required runner controls have satisfying
enforcement evidence.
