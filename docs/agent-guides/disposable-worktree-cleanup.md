# Controlled Disposable Worktree Cleanup

`cleanup_disposable_worktree.py` removes one exact prepared disposable
worktree after explicit confirmation of its canonical path. It may discard
uncommitted changes, so it is a deliberately destructive operator action, not
a runner lifecycle service or automatic cleanup mechanism.

## Run

Carry the preparation receipt SHA-256 separately and pass the exact canonical
workspace path twice: once as the target and once as the explicit
confirmation.

```text
python .agent/checks/cleanup_disposable_worktree.py \
  --source <clean-source-checkout> \
  --workspace <prepared-external-worktree> \
  --receipt <external-preparation-receipt.json> \
  --receipt-sha256 <expected-preparation-receipt-sha256> \
  --cleanup-receipt <external-absent-cleanup-receipt.json> \
  --confirm-workspace <exact-canonical-workspace-path> \
  --format json
```

The CLI accepts no policy override. Its exact policy is
`.agent/policies/disposable-worktree-cleanup.json`.

Exit code `0` means cleanup and cleanup-receipt writing succeeded, `2` means a
deterministic precondition rejected cleanup without removing the workspace,
and `1` means an input, policy, Git, I/O, or post-cleanup evidence error.

## Destructive Contract

Before removal, the command:

- verifies the separately carried preparation-receipt digest;
- requires the exact preparation-receipt schema, identity, invariants, false
  authorization fields, and trusted bindings;
- requires both workspace and preparation receipt to remain outside the source,
  and the preparation receipt to remain outside the workspace;
- requires a clean source checkout still at the preparation base;
- requires the workspace to be exactly registered with that source;
- requires the workspace to remain detached and at the preparation base;
- refuses a branch or a divergent detached commit;
- allows uncommitted tracked and untracked workspace changes;
- requires `--confirm-workspace` to equal the canonical workspace path;
- requires an absent cleanup-receipt path outside source and workspace;
- rechecks receipt, source, workspace, and cleanup bindings immediately before
  removal.

The command then runs only:

```text
git -C <source> worktree remove --force <workspace>
```

It does not run broad `git worktree prune`. After removal it requires the
workspace directory and exact registration to be absent, all other worktree
registrations to remain unchanged, source `HEAD`, branches, and status to
remain unchanged, and the preparation receipt to remain byte-for-byte intact.

The cleanup receipt binds the exact cleanup command, imported helper, and
policy bytes, the preparation-receipt SHA-256, whether uncommitted changes were
discarded, and the verified postconditions.

## Honest Boundary

Explicit path confirmation permits only this exact destructive cleanup
attempt. It does not authorize an implementation session, agent invocation,
workspace use, publication, or any broader workflow action. Every result and
cleanup receipt retains those authorization fields as false.

The command intentionally refuses a workspace with a branch or detached commit
different from the preparation base, because removing it could hide committed
work. Preserve any required implementation patch or other evidence before
cleanup; this command does not create one.

There is no transaction spanning Git removal and cleanup-receipt writing. If
Git removal succeeds but receipt writing or final evidence validation fails,
the command returns an error and states that cleanup already completed. It
cannot restore discarded changes. The preparation receipt remains preserved,
but it is evidence of preparation, not evidence of cleanup.

This command does not prove cleanup after timeout, agent failure, concurrent
mutation, process termination, or host crash. It is intentionally not a
runner-readiness evidence source.

Validate the exact cleanup receipt and current absent-workspace state with the
separate read-only consumer documented in
`docs/agent-guides/disposable-worktree-cleanup-validation.md`. Validation
success still does not prove an automated lifecycle or authorize anything.
