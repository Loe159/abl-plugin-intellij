# Local Read-Only Command Adapter

`local_read_only.py` runs one explicit local command against a prepared
read-only stage bundle, captures stdout as an external response file, and
immediately validates that response with `validate_stage_output.py`.

It is a command wrapper, not an authorization gate. It does not apply the
response into the run, approve an artifact, publish anything, select a model, or
prove provider sandboxing.

## Run

Build a context bundle first with `build_stage_context.py` or
`manual_read_only.py prepare`, and carry the reported bundle SHA-256 separately.
Then run:

```text
python .agent/adapters/local_read_only.py \
  --repo . \
  --bundle <external-context-bundle.json> \
  --bundle-sha256 <trusted-builder-sha256> \
  --response <external-absent-response.md> \
  -- <command that prints one stage artifact to stdout>
```

The adapter passes the bundle JSON on stdin and also sets
`AGENT_CONTEXT_BUNDLE` to the bundle path. The command runs with the repository
root as its working directory so a local model CLI can inspect the checkout.
The adapter checks the Git-visible worktree before and after execution and
rejects the run if the command changes tracked or untracked files, including
when the command exits non-zero or times out. This is detection, not rollback:
the adapter removes the captured response when present, but any repository
mutation must still be cleaned by the operator.

## Output

The JSON envelope always includes:

```text
adapter=local-read-only-command
mode=read-only
run_mutated=false
response_applied=false
authorized=false
network_authorized=false
publication_authorized=false
```

`command_invoked=true` means the local child process was started. It does not
mean model invocation, network access, or provider billing was authorized by the
workflow. If stdout is structurally valid for the stage, the nested validation
result reports `accepted=true`.

## Limits

The adapter bounds wall-clock time and captured stdout/stderr, requires external
bundle and response paths, refuses to overwrite an existing response, and
validates the final response. It still cannot prove:

- provider credential descendant noninheritance;
- operating-system network isolation;
- that a provider CLI ignored untrusted task text;
- that the produced research, plan, compaction, or review is correct;
- that the response should be applied to the run.

Use `apply_stage_output.py` separately for the operator-confirmed copy step.
