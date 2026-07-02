# Implementation Session Start

`check_implementation_session_start.py` checks whether the current
implementation preflight has enough validated local evidence to reach the
session-start boundary. It is read-only and does not start a session, select a
runner, invoke an agent, mutate the repository, or authorize publication.

The checker requires `check_implementation_runner_selection.py` to report
`runner_selection_ready=true`. It may then report `session_start_ready=true`,
but that means only that the pre-start prerequisites are currently coherent.
An exact explicit start-authorization gate now exists separately. This
readiness checker does not consume its receipt, so the result still records
`missing_authorizations=["session_start_authorization"]`.

## Run

Carry the proposal, disposable-worktree receipt, approval-receipt, and preflight
SHA-256 digests separately from their files:

```text
python .agent/checks/check_implementation_session_start.py \
  --repo <clean-source-checkout> \
  --proposal <external-path>/implementation-session-proposal.json \
  --proposal-sha256 <expected-proposal-sha256> \
  --workspace <prepared-external-worktree> \
  --worktree-receipt <external-path>/disposable-worktree-receipt.json \
  --worktree-receipt-sha256 <expected-worktree-receipt-sha256> \
  --approval-receipt <external-session-approval-receipt.json> \
  --approval-receipt-sha256 <expected-approval-receipt-sha256> \
  --preflight <external-path>/implementation-invocation-preflight.json \
  --preflight-sha256 <expected-preflight-sha256> \
  --format json
```

Exit code `0` means the pre-start evidence is ready under the exact current
policy, `2` means a deterministic precondition blocked it, and `1` means a
tool, input, policy, or I/O error. The CLI accepts no runner, policy, proposal,
approval, preflight, readiness, or authorization override.

## Honest Boundary

`session_start_ready=true` is not permission to start. It still retains:

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

The checker does not produce a start receipt, select the runner, execute the
implementation prompt, capture output, enforce runtime controls, or perform
cleanup. It proves only the pre-authorization boundary. The separate exact
authorization and validation procedures are documented in
`docs/agent-guides/implementation-session-start-authorization.md` and
`docs/agent-guides/implementation-session-start-authorization-validation.md`.
