# Implementation Session Proposal Validation

`validate_implementation_session.py` independently validates one exact
supervised implementation proposal against the clean source checkout and the
prepared disposable workspace a future runner would consume. It does not
authorize or start a session.

This check is separate from proposal building because repository state, trusted
prompt bytes, policies, or proposal content may change after the proposal is
created.

## Run

Carry the expected proposal SHA-256 and disposable-worktree preparation receipt
SHA-256 separately from their files:

```text
python .agent/checks/validate_implementation_session.py \
  --repo <clean-source-checkout> \
  --proposal <external-path>/implementation-session-proposal.json \
  --proposal-sha256 <expected-sha256> \
  --workspace <prepared-external-worktree> \
  --worktree-receipt <external-path>/disposable-worktree-receipt.json \
  --worktree-receipt-sha256 <expected-receipt-sha256> \
  --format json
```

The proposal must be an external regular file, not a symbolic link. Exit code
`0` means the proposal is currently valid, `2` means a deterministic rule
rejected it, and `1` means a tool, input, policy, or I/O error. The CLI accepts
no policy or prompt override.

## Validation Scope

The validator:

- checks the separately supplied proposal digest before parsing;
- requires exact proposal fields and false authorization metadata;
- reconstructs and independently validates the embedded handoff and its digest;
- compares identity, prompt, policy bindings, workspace contract,
  capabilities, budgets, and external controls using type-sensitive equality;
- revalidates the prepared disposable worktree against its exact receipt and
  compares the proposal's prepared-workspace record with current validation;
- compares workspace policies with the trusted validator repository;
- requires exact base commit and a clean workspace;
- rejects high-confidence secret signatures;
- rechecks proposal bytes, prompt, prepared workspace, workspace policies,
  trusted policies, `HEAD`, and worktree state immediately before returning
  success.

Every result retains:

```text
authorized=false
agent_invocation_authorized=false
implementation_authorized=false
repository_mutation_authorized=false
network_authorized=false
publication_authorized=false
session_start_authorized=false
```

## Honest Boundary

`valid=true` means only that the exact proposal currently matches the exact
workspace, prepared-worktree receipt, and trusted local contract. It is not
authorization, a sandbox, a cross-process lock, proof of future confinement to
that workspace, or enforcement of network, tool, time, cleanup, or turn
restrictions.

A separate consumer-side command is useful for temporal separation, but it
shares versioned validation helpers and policies with the builder. It is not a
cryptographically independent implementation.

A future runner must call this validation again immediately before consuming a
proposal, then separately verify authorization and enforce the declared
controls. Validation success must never be treated as permission to invoke an
agent.
