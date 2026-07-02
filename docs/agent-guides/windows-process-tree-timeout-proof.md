# Windows Process-Tree Timeout Proof

`prove_windows_process_tree_timeout.py` exercises one fixed Windows process
tree and verifies its cleanup with the installed `taskkill` primitive. It does
not invoke Codex, run a model, select a runner, or authorize a session.

## Run

```text
python .agent/checks/prove_windows_process_tree_timeout.py --repo . --format json
```

The command accepts no policy override. Its exact policy is
`.agent/policies/windows-process-tree-timeout-proof.json`.

## Fixture And Evidence

The harmless fixture creates a two-level sleeping tree:

```text
root Python process
  child Python process
    grandchild Python process
```

All three processes use Python isolated mode, disable site imports and bytecode
writes, run without a shell, and perform only bounded sleeping and process
creation. The root reports the child and grandchild PIDs through one bounded
pipe; no files or network are used.

Before cleanup, the proof opens Windows synchronization handles for the exact
child and grandchild process objects and requires both to be running. After the
root exceeds the configured timeout, it executes exactly:

```text
taskkill /PID <root-pid> /T /F
```

The proof requires a zero `taskkill` result, reaps the root, and requires both
pre-opened descendant handles to become signaled within the cleanup bound. Raw
`taskkill` output and executable paths are not returned.

## Verified Scope

`windows_taskkill_two_level_process_tree_timeout_fixture=verified_fixture`
means only that the fixed two-level tree was observed running and then fully
terminated by the exact Windows `taskkill /T /F` procedure in the current
environment.

It does not prove:

- cleanup of every arbitrary process tree or adversarial descendant;
- cross-platform process-tree cleanup;
- process creation timeout;
- the complete implementation-session wall-clock timeout.

Those controls remain `not_proven`. The implementation-session proposal is not
changed or promoted by this result.

## Failure Behavior

Unsupported platforms, missing `taskkill`, invalid descendant identity,
descendants that are not observed running, early root completion, non-zero
`taskkill`, cleanup timeout, unsignaled descendant handles, exceeded duration,
policy drift, and CLI policy overrides all fail closed.

Best-effort fixture cleanup runs on failure. The sleeping fixture also exits on
its own after ten seconds if the operating-system cleanup primitive fails.
