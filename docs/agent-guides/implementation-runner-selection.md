# Implementation Runner Selection

`check_implementation_runner_selection.py` checks whether the fixed pilot
runner candidate may be selected. It is read-only and does not select that
runner, invoke an agent, start a session, mutate the repository, or authorize
publication.

The current candidate is `codex-cli-disposable-worktree`. The checker requires
a currently valid invocation preflight and current runner controls ready before
returning `runner_selection_ready=true`.

## Run

Carry the proposal, disposable-worktree receipt, approval-receipt, and preflight
SHA-256 digests separately from their files:

```text
python .agent/checks/check_implementation_runner_selection.py \
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

Exit code `0` means the candidate is selectable under the exact current policy,
`2` means a deterministic precondition blocked selection, and `1` means a tool,
input, policy, or I/O error. The CLI accepts no runner, policy, proposal,
approval, preflight, or readiness override.

## Honest Boundary

`runner_selection_ready=true` means only that the fixed candidate passed the
read-only selection preconditions. It still retains:

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

The checker does not produce a selection receipt and does not make invocation
ready by itself. The separate session-start readiness gate is documented in
`docs/agent-guides/implementation-session-start.md`, and even that gate still
does not authorize a launch.
