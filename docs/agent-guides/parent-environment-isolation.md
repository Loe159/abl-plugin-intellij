# Parent Environment Isolation

`isolated_process.py` is the first concrete runtime primitive for the
supervised implementation runner. It starts one child process without a shell
and constructs the child environment from an exact allowlist instead of
inheriting the parent environment.

`prove_parent_environment_isolation.py` exercises that exact launcher with a
harmless isolated Python child. The fixture adds synthetic markers under six
sensitive variable names and verifies that none of those names reaches the
child.

## Run

```text
python .agent/checks/prove_parent_environment_isolation.py \
  --repo . \
  --format json
```

Exit code `0` means the exact local launcher enforced the bounded parent
environment contract. Exit code `2` means the proof did not match. Exit code
`1` means a policy, input, runtime, or I/O error. The CLI accepts no policy,
environment, command, or launcher override.

## Enforced Launcher Contract

The launcher:

- requires an absolute existing executable;
- rejects local Windows App Execution Alias executables under
  `AppData\Local\Microsoft\WindowsApps`;
- requires an existing working directory;
- uses `shell=false` and closed standard input;
- reconstructs the child environment from ten named platform variables;
- adds three fixed non-secret runtime variables;
- enforces a bounded direct-child timeout up to the supervised runner's
  current adapter timeout ceiling;
- captures both output streams under an exact retained-byte ceiling.

The proof reports variable names, counts, booleans, and output digests. It does
not emit or compare the synthetic marker values.

## Honest Boundary

The readiness ledger now marks
`parent_environment_credential_isolation=satisfied` for this exact launcher.
It separately keeps
`provider_credential_descendant_noninheritance=related_evidence_only`.

This distinction matters: clearing the environment before starting Codex does
not prove that a credential deliberately supplied to Codex, loaded from a file,
or obtained from an operating-system credential store cannot reach commands
spawned later by the model. The proof also does not enforce filesystem scope,
network isolation, a tool allowlist, model turns, worktree cleanup, or agent
invocation. Output-capture enforcement is proved separately in
`docs/agent-guides/bounded-output-capture.md`.

The isolated-process policy allows a maximum 600-second direct-child timeout so
the supervised runner's `adapter_timeout_seconds=600.0` can reach the launcher
without being rejected by policy mismatch. This is a direct-child bound, not a
complete implementation-session deadline or arbitrary process-tree timeout.

`local_implementation_adapter.py` also reconstructs the environment for its
direct child command with the same allowlist. The bounded proof
`.agent/checks/prove_local_adapter_environment_filter.py` verifies that
synthetic provider API-key variables do not reach that direct child or one
spawned descendant command. This is related evidence only for
provider-credential descendant noninheritance because it is environment-only:
it does not block credentials loaded from files, operating-system credential
stores, or credentials deliberately passed through provider-specific channels.
