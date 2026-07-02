# Disposable Git Worktree Lifecycle Proof

`prove_disposable_worktree.py` exercises one bounded Git worktree lifecycle in
a synthetic temporary repository. It does not create a worktree for the plugin
checkout, invoke an agent, select a runner, or authorize a session.

## Run

```text
python .agent/checks/prove_disposable_worktree.py --repo . --format json
```

The command accepts no policy override. Its exact policy is
`.agent/policies/disposable-worktree-proof.json`.

## Fixture And Evidence

The fixture creates a temporary Git repository, commits one fixed file, and
creates a detached worktree at the exact committed `HEAD`. It then changes the
tracked file, adds one untracked file inside the detached worktree, and verifies
that the base checkout remains clean and unchanged.

Cleanup uses the exact bounded sequence:

```text
git worktree remove --force <temporary-worktree>
git worktree prune --expire now
```

The proof requires the temporary directory and Git worktree registration to be
removed while the base commit, branch set, tracked content, and status remain
unchanged. Git runs without a shell, and raw Git output or temporary paths are
not returned.

## Verified Scope

`disposable_git_worktree_lifecycle_fixture=verified_fixture` means only that
the fixed dirty detached-worktree lifecycle completed successfully in the
synthetic repository.

It does not prove:

- concurrent worktree lifecycle handling;
- implementation-runner disposable-worktree enforcement;
- cleanup after a host crash.

Those controls remain `not_proven`. The result is related evidence for runner
readiness, never satisfying evidence.

The next bounded component is documented in
`docs/agent-guides/disposable-worktree-preparation.md`. It creates a real
external worktree only when explicitly invoked, but still does not authorize
workspace use or prove a runner lifecycle.

## Failure Behavior

Missing Git, failed or unexpected Git commands, lifecycle invariant failures,
policy drift, and CLI policy overrides all fail closed. Temporary-directory
cleanup remains best effort after a fixture failure. Every result retains false
authorization and runner-selection fields.
