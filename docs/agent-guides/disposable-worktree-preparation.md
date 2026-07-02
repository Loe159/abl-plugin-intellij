# Disposable Implementation Worktree Preparation

`prepare_disposable_worktree.py` creates one detached, clean Git worktree at an
exact commit and writes a bounded external receipt. It is a deterministic
preparation step, not a runner, agent invocation, session authorization, or
cleanup service.

## Run

Use a clean source checkout whose `HEAD` is the exact requested base commit.
The target and receipt must not exist, and both parent directories must already
exist outside the source checkout.

```text
python .agent/checks/prepare_disposable_worktree.py \
  --repo <clean-source-checkout> \
  --base <40-character-lowercase-commit> \
  --target <external-absent-worktree-path> \
  --receipt <external-absent-receipt.json> \
  --format json
```

The CLI accepts no policy override. Its exact policy is
`.agent/policies/disposable-worktree-preparation.json`.

Exit code `0` means preparation and receipt writing succeeded, `2` means the
source failed a deterministic clean-state or base-match prerequisite, and `1`
means an input, Git, policy, postcondition, rollback, or I/O error.

## Preparation Contract

The command:

- accepts only an exact 40-character lowercase commit ID;
- requires the source checkout to be clean and at that exact commit;
- refuses targets and receipts inside the source checkout;
- refuses existing targets and receipts;
- runs Git without a shell and with bounded command timeouts;
- creates the target using `git worktree add --detach`;
- requires the target to be clean, detached, and at the exact base;
- requires source `HEAD`, branches, and status to remain unchanged;
- requires exactly one worktree registration to be added;
- writes a receipt that binds the exact preparer and policy bytes by SHA-256;
- removes its receipt and attempts bounded worktree rollback after any failure
  that occurs after creation.

Successful preparation necessarily changes the source repository's Git
worktree metadata. It also creates the external target and receipt. The receipt
therefore reports `source_git_metadata_changed=true` and
`cleanup_required=true`.

## Honest Boundary

The receipt always retains:

```text
authorized=false
agent_invocation_authorized=false
implementation_authorized=false
runner_selected=false
session_start_authorized=false
workspace_use_authorized=false
```

Preparation does not validate an implementation-session proposal, authorize
workspace use, enforce network or filesystem isolation, start a process, or
prove cleanup. SHA-256 binds exact bytes but is not a signature.

Validate the exact receipt and current workspace state with the separate
consumer-side command documented in
`docs/agent-guides/disposable-worktree-validation.md`. Validation success still
does not authorize workspace use.

The source repository is not locked across the operation. The command rechecks
state after writing the receipt, but it does not claim a cross-process or
cross-host race-free transaction. Rollback is best effort and reports a
sanitized failure if cleanup does not succeed.

## Cleanup

Cleanup remains an explicit destructive operator action. Use the bounded
command documented in
`docs/agent-guides/disposable-worktree-cleanup.md`; it requires the exact
preparation receipt, separately carried digest, and canonical workspace-path
confirmation. It refuses branches and divergent detached commits.

Do not treat successful preparation or controlled cleanup as evidence that a
future runner performs cleanup after success, failure, timeout, or host crash.
