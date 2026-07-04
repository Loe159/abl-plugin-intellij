# Implementation Invocation Preflight

`build_implementation_invocation_preflight.py` builds one deterministic
external preflight package from an exact implementation-session proposal and a
valid implementation-session approval-validation result. It does not select a
runner, invoke an agent, start a session, mutate the repository, or authorize
publication.

This step exists to keep the boundary before execution explicit: all known
proposal, workspace, approval, and runner-readiness evidence can be assembled
for review without pretending that a session is already safe to launch.

## Run

Carry the proposal, disposable-worktree receipt, and approval-receipt SHA-256
digests separately from their files:

```text
python .agent/checks/build_implementation_invocation_preflight.py \
  --repo <clean-source-checkout> \
  --proposal <external-path>/implementation-session-proposal.json \
  --proposal-sha256 <expected-proposal-sha256> \
  --workspace <prepared-external-worktree> \
  --worktree-receipt <external-path>/disposable-worktree-receipt.json \
  --worktree-receipt-sha256 <expected-worktree-receipt-sha256> \
  --approval-receipt <external-session-approval-receipt.json> \
  --approval-receipt-sha256 <expected-approval-receipt-sha256> \
  --output <external-path>/implementation-invocation-preflight.json \
  --format json
```

Exit code `0` means the preflight package was produced, `2` means a
deterministic precondition blocked it, and `1` means a tool, input, policy, or
I/O error. The CLI accepts no policy, proposal, approval, or readiness override.

## Validation Scope

The builder:

- requires the output path to be external, outside the prepared workspace, and
  absent before the run;
- validates the exact implementation-session approval receipt through
  `validate_implementation_session_approval.py`;
- requires `valid=true` from that approval validation, including current
  runner-readiness success;
- verifies the proposal digest and checks identity against the validation
  result;
- binds the preflight script, policy, proposal validator, approval validator,
  runner-readiness checker, and related policies by SHA-256;
- checks for high-confidence secret signatures in the assembled source data;
- rechecks approval validation, repository state, and policy bindings before
  writing the package.

Every result and package retains:

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

`produced=true` means only that the current local evidence was assembled into a
bounded package. It is not runner selection, sandbox enforcement, workspace
confinement, timeout enforcement, model invocation, output capture, cleanup
assurance, or authorization to start.

In the current pilot checkout, real preflight production can proceed when the
implementation-session approval validation passes with the current
runner-readiness report recorded by session approval validation. In the local
pilot, `controls_ready=false` remains acceptable evidence when it is explicitly
bound into the approval and preflight records; it is not promoted to sandbox
enforcement or invocation authorization.

The independent consumer-side validation is documented in
`docs/agent-guides/implementation-invocation-preflight-validation.md`. Its
`valid=true` result still does not select a runner, invoke an agent, or start a
session.
