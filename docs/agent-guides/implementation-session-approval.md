# Implementation Session Proposal Approval

`approve_implementation_session.py` records a local approval for one exact
validated implementation-session proposal. It does not select a runner, invoke
an agent, start a session, mutate the repository, or authorize publication.

This gate exists so a later invocation design cannot rely on vague consent like
"run the agent". The approver must bind to the exact proposal bytes, prepared
worktree receipt, runner-readiness report, approval controls, and external
receipt path.

## Preconditions

The approval policy currently requires:

- a valid implementation-session proposal from
  `validate_implementation_session.py`;
- the same prepared disposable worktree and receipt inputs used to validate
  that proposal;
- a current `assess_runner_readiness.py` report whose SHA-256 is bound into
  the exact approval receipt;
- repository `HEAD` equal to the proposal base commit;
- a clean source checkout;
- an external absent approval receipt path outside the checkout and prepared
  workspace.

In the current pilot checkout, runner readiness is expected to remain
`controls_ready=false`. That fact is recorded in the receipt and later
validation, but it no longer blocks the local pilot approval by itself. The
approval still does not select a runner, authorize invocation, prove sandbox
enforcement, or hide the unready controls.

## Two-Step Procedure

Carry the proposal SHA-256 and disposable-worktree receipt SHA-256 separately
from their files, then request the exact confirmation:

```text
python .agent/checks/approve_implementation_session.py check \
  --repo <clean-source-checkout> \
  --proposal <external-path>/implementation-session-proposal.json \
  --proposal-sha256 <expected-proposal-sha256> \
  --workspace <prepared-external-worktree> \
  --worktree-receipt <external-path>/disposable-worktree-receipt.json \
  --worktree-receipt-sha256 <expected-worktree-receipt-sha256> \
  --approval-receipt <external-absent-session-approval-receipt.json> \
  --format json
```

If `check` reports `approvable=true`, review the proposal, workspace, and
runner-readiness evidence, then pass the phrase unchanged:

```text
python .agent/checks/approve_implementation_session.py approve \
  --repo <clean-source-checkout> \
  --proposal <external-path>/implementation-session-proposal.json \
  --proposal-sha256 <expected-proposal-sha256> \
  --workspace <prepared-external-worktree> \
  --worktree-receipt <external-path>/disposable-worktree-receipt.json \
  --worktree-receipt-sha256 <expected-worktree-receipt-sha256> \
  --approval-receipt <same-external-absent-session-approval-receipt.json> \
  --approver <local-approver-id> \
  --confirm "<exact-required-confirmation>" \
  --format json
```

Exit code `0` means `check` found an approvable exact proposal or `approve`
wrote the approval receipt. Exit code `2` means a deterministic rule blocked
approval. Exit code `1` means a tool, input, policy, or I/O error.

## Receipt

The approval receipt records:

- the exact proposal SHA-256;
- the exact disposable-worktree preparation receipt SHA-256;
- the runner-readiness report SHA-256;
- the confirmation SHA-256 and local approver declaration;
- issue, risk, and base commit;
- exact approval-control bindings.

Every result and receipt retains:

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

`session_proposal_approved=true` means only that a local approver accepted the
exact proposal candidate while the configured preconditions matched. It is not
authentication, runner selection, sandbox enforcement, network isolation,
workspace confinement, timeout enforcement, output capture, cleanup assurance,
or permission to invoke an agent.

The receipt is not a cryptographic signature. A stronger identity mechanism and
a separate invocation authorization design remain future work.

The independent consumer-side validation is documented in
`docs/agent-guides/implementation-session-approval-validation.md`. Its
`valid=true` result still does not authorize or start a session.
