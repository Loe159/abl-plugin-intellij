# Disposable Worktree Receipt Validation

`validate_disposable_worktree.py` independently validates one exact preparation
receipt against the current source checkout and disposable worktree. It is
read-only and does not authorize workspace use, invoke an agent, start a
session, or clean up the worktree.

## Run

Carry the expected receipt SHA-256 separately from the receipt file:

```text
python .agent/checks/validate_disposable_worktree.py \
  --source <clean-source-checkout> \
  --workspace <prepared-external-worktree> \
  --receipt <external-receipt.json> \
  --receipt-sha256 <expected-sha256> \
  --format json
```

The CLI accepts no policy override. Its exact policy is
`.agent/policies/disposable-worktree-validation.json`.

Exit code `0` means the receipt and current state are valid, `2` means a
deterministic rule rejected them, and `1` means an input, policy, Git, parsing,
or I/O error.

## Validation Scope

The validator:

- verifies the separately supplied receipt digest before parsing;
- requires the exact receipt schema and false authorization fields;
- compares source path, workspace path, base commit, and all declared
  preparation invariants with the fixed contract;
- compares the receipt's preparer and preparation-policy bindings with trusted
  repository bytes;
- requires the source checkout to remain clean and at the receipt base;
- requires the workspace to remain clean, detached, and at the receipt base;
- requires the workspace to be exactly registered as a detached worktree of
  the source repository;
- rejects a separate clone even when it is clean, detached, and at the same
  commit;
- rechecks the receipt, source, workspace, and validator bindings before
  returning success.

Every result retains:

```text
authorized=false
agent_invocation_authorized=false
implementation_authorized=false
runner_selected=false
session_start_authorized=false
workspace_use_authorized=false
```

## Honest Boundary

`valid=true` means only that the exact receipt matches the observed source and
workspace state during this validation. It does not authorize use, prove
runtime isolation, reserve or lock the workspace, start supervision, or prove
future cleanup.

The validator is a separate consumer-side command, but it reuses versioned Git
observation helpers from the preparer. It is not a cryptographically
independent implementation. SHA-256 binds exact bytes but is not a signature.

The source repository and workspace may change immediately after validation.
A future consumer must validate again immediately before use, then separately
verify explicit authorization and enforce all required runtime controls.

When the workspace is no longer needed, use the destructive operator action
documented in `docs/agent-guides/disposable-worktree-cleanup.md`. Cleanup uses
the preparation receipt directly and has separate preconditions; successful
read-only validation neither requests nor authorizes cleanup.
