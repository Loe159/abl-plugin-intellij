# Direct Child Wall-Clock Timeout Proof

`prove_wall_clock_timeout.py` exercises one deliberately narrow operational
control with harmless fixed fixtures. It proves that the current Python wrapper
can time out, kill, and reap one direct child process after that process has
successfully spawned.

It does not invoke Codex, run a model, select a runner, or authorize a session.

## Run

```text
python .agent/checks/prove_wall_clock_timeout.py --repo . --format json
```

The command accepts no policy override. Its exact policy is
`.agent/policies/wall-clock-timeout-proof.json`.

The proof runs two fixed children with the current Python executable:

- a fast control that must finish normally;
- a sleeping child that must exceed the 0.5-second wait, receive a direct
  `kill`, and be reaped within the bounded cleanup period.

Both children use Python isolated mode, disable site imports and bytecode
writes, receive no stdin, discard stdout and stderr, and run without a shell.
The scripts contain no file, network, subprocess, credential, or model access.

## Verified Scope

`post_spawn_direct_child_timeout=verified_fixture` means only that both fixed
fixtures matched their expected observations in the current environment and
within the configured observed bound.

The timer begins only after process creation returns. Successful reaping proves
that the direct child terminated; it does not inspect or certify a process
tree.

Every run leaves these broader controls at `not_proven`:

- `process_spawn_timeout`;
- `descendant_process_tree_timeout`;
- `implementation_session_wall_clock_timeout`.

The implementation-session proposal is not changed or promoted by this proof.
A future runner still needs a separately verified process-tree strategy,
session-level deadline, failure cleanup, output capture, and independent
validation.

The next bounded experiment is documented in
`docs/agent-guides/windows-process-tree-timeout-proof.md`. It verifies one
fixed two-level Windows tree and still does not promote the
implementation-session timeout.

## Failure Behavior

Spawn errors, a sleeping child that finishes before the timeout, failed kill or
reap, an exceeded observation bound, policy drift, and CLI policy overrides all
fail closed. Failure never selects a runner or authorizes invocation.
