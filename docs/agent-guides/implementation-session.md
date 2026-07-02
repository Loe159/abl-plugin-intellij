# Supervised Implementation Session Proposal

`build_implementation_session.py` converts one exact implementation handoff
into a deterministic proposal for a later supervised writing session. It does
not authorize, create, or start that session.

The proposal exists so that a later human decision can bind to explicit scope,
capabilities, budgets, trusted policy versions, and expected external controls
instead of vaguely authorizing "an agent".

## Fixed Pilot Contract

The repository policy in `.agent/policies/implementation-session.json`
currently requires:

- a designated disposable Git worktree, clean at the exact handoff base;
- a valid disposable-worktree preparation receipt, carried with a separate
  SHA-256 digest and revalidated before proposal output;
- repository reads, repository file writes, and local commands only;
- no network, external-service write, run write, handoff write, publication,
  Git index write, commit, or branch operation;
- at most 12 turns and 30 minutes;
- the existing diff-policy limits of 12 files and 500 changed lines;
- external complete-patch generation, diff-policy validation, patch-risk
  classification, disposable-worktree validation, focused tests, and human
  implementation review.

The static supervised-write prompt is
`.agent/prompts/implementation/implement.md`. It is validated separately from
the read-only research and planning prompt contract.

## Build

Carry the handoff SHA-256 and disposable-worktree preparation receipt SHA-256
separately from their files, then use external handoff, receipt, workspace, and
output paths:

```text
python .agent/checks/build_implementation_session.py \
  --repo <clean-source-checkout> \
  --handoff <external-path>/implementation-handoff.json \
  --handoff-sha256 <expected-sha256> \
  --workspace <prepared-external-worktree> \
  --worktree-receipt <external-path>/disposable-worktree-receipt.json \
  --worktree-receipt-sha256 <expected-receipt-sha256> \
  --output <external-path>/implementation-session-proposal.json \
  --format json
```

Exit code `0` means the proposal was produced, `2` means a deterministic
precondition blocked it, and `1` means a tool, input, policy, or I/O error. The
CLI accepts no policy or prompt override.

## Validation

Before producing output, the builder:

- verifies the separately supplied handoff digest before parsing;
- rejects handoff symlinks, authorization injection, malformed or inconsistent
  manifests, invalid embedded artifacts, missing plan-approval receipt
  digest, and non-approved plans;
- requires clean repository state and exact base commit;
- validates the prepared disposable worktree against its exact preparation
  receipt and requires the same base commit as the handoff;
- binds the exact implementation prompt and critical repository policies by
  SHA-256;
- refuses when workspace policy bytes differ from the trusted builder
  repository;
- checks for high-confidence secret signatures;
- rechecks handoff, repository, prepared workspace, prompt, and policy bindings
  before writing;
- emits deterministic JSON no larger than 150,000 bytes.

Every result and proposal retains:

```text
authorized=false
agent_invocation_authorized=false
implementation_authorized=false
repository_mutation_authorized=false
network_authorized=false
publication_authorized=false
session_start_authorized=false
```

## Honest Boundary

The proposal describes intended controls; it does not enforce them. It can
confirm that one prepared worktree currently matches its receipt, but it cannot
confine a later runner to that workspace, disable network access, stop a
process after 30 minutes, limit model turns, prevent tools from writing, clean
up after failure, or authenticate a human. SHA-256 binds exact bytes but is not
a signature, and an actor controlling both a file and its expected digest
remains inside the trust boundary.

A future runner must independently validate the proposal, enforce workspace and
tool restrictions, capture outputs, and stop on budget or policy violations.
Explicit authorization must bind to that exact proposal and exact workspace;
it must remain separate from invocation.

The independent consumer-side validation is documented in
`docs/agent-guides/implementation-session-validation.md`. Its `valid=true`
result still does not authorize or start the session.

The exact local approval gate is documented in
`docs/agent-guides/implementation-session-approval.md`. It can write a receipt
only after proposal validation and runner-readiness success, but that receipt
still does not select a runner, invoke an agent, or start a session.

The approval receipt validator is documented in
`docs/agent-guides/implementation-session-approval-validation.md`. A later
preflight package may consume its `valid=true` result, but validation still
does not select a runner, invoke an agent, or start a session.

The non-authorizing preflight package is documented in
`docs/agent-guides/implementation-invocation-preflight.md`. It assembles
current proposal, workspace, approval, and runner-readiness evidence for review
while keeping runner selection and session start false.

The preflight validator is documented in
`docs/agent-guides/implementation-invocation-preflight-validation.md`. It can
reject stale or overclaiming preflight packages, but its `valid=true` result
still does not select a runner, invoke an agent, or start a session.

The explicit invocation-readiness check is documented in
`docs/agent-guides/implementation-invocation-readiness.md`. The current
checkout is expected to return `invocation_ready=false` because runner
enforcement evidence remains incomplete. The exact start-authorization receipt
is a separate required input.

The runner-selection readiness check is documented in
`docs/agent-guides/implementation-runner-selection.md`. It can confirm that the
fixed pilot runner candidate is selectable, but it still keeps
`runner_selected=false`.

The session-start readiness check is documented in
`docs/agent-guides/implementation-session-start.md`. It can confirm that the
pre-start evidence reaches the launch boundary, but it still keeps
`session_start_authorized=false` and records the missing start authorization.
The later authorization gate and validator are documented in
`docs/agent-guides/implementation-session-start-authorization.md`.

Before selecting a runner, use the metadata-only audit documented in
`docs/agent-guides/local-runner-audit.md`. Its observations deliberately do not
promote any declared control to enforced.

The bounded experiment in
`docs/agent-guides/disposable-worktree-proof.md` verifies one dirty detached
worktree lifecycle in a synthetic temporary repository. It does not prove that
an implementation runner creates, confines, or cleans up its workspace.

The deterministic preparation step in
`docs/agent-guides/disposable-worktree-preparation.md` can create one exact
external detached worktree and receipt. The proposal builder now consumes that
receipt as a validation precondition, but preparation itself still does not
authorize this proposal, invoke an agent, enforce runtime controls, or clean up
the workspace.

The separate receipt validator in
`docs/agent-guides/disposable-worktree-validation.md` can confirm that the
prepared worktree still matches its exact receipt. The proposal builder and
proposal validator both call this check, but its `valid=true` result still does
not authorize use, start a session, or enforce runtime controls.

The explicit destructive action in
`docs/agent-guides/disposable-worktree-cleanup.md` can remove one exact
prepared worktree after canonical-path confirmation. It does not prove that a
runner performs cleanup after success, failure, timeout, or host crash.

The separate read-only consumer in
`docs/agent-guides/disposable-worktree-cleanup-validation.md` can validate the
exact cleanup receipt against current absence. Its `valid=true` result still
does not prove automated lifecycle enforcement.

The bounded experiment in `docs/agent-guides/wall-clock-timeout-proof.md`
verifies only direct-child timeout behavior after process creation. It does not
satisfy or promote the proposed 30-minute implementation-session budget.

The Windows experiment in
`docs/agent-guides/windows-process-tree-timeout-proof.md` verifies cleanup of
one fixed two-level tree through `taskkill /T /F`. It also does not satisfy or
promote the proposed session timeout.

Aggregate current evidence with
`docs/agent-guides/runner-readiness.md`. Its `controls_ready` result remains
separate from proposal validity, runner selection, authorization, and session
start.
