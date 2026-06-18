# Implementation Runner Control Readiness

`assess_runner_readiness.py` aggregates the current local metadata audit,
bounded disposable-worktree fixture, and bounded timeout fixtures into one
fail-closed control-readiness report. It does not validate a proposal, select a
runner, invoke an agent, or authorize a session.

## Run

```text
python .agent/checks/assess_runner_readiness.py --repo . --format json
```

The CLI accepts no policy or evidence override. It executes the eleven fixed
local evidence sources:

- `.agent/checks/audit_local_runner.py`;
- `.agent/checks/prove_disposable_worktree.py`;
- `.agent/checks/prove_wall_clock_timeout.py`;
- `.agent/checks/prove_windows_process_tree_timeout.py`;
- `.agent/checks/prove_parent_environment_isolation.py`;
- `.agent/checks/prove_bounded_output_capture.py`;
- `.agent/checks/prove_implementation_result_validation.py`;
- `.agent/checks/prove_implementation_patch_validation.py`;
- `.agent/checks/prove_implementation_patch_receipt_validation.py`;
- `.agent/checks/prove_implementation_quality_gate.py`;
- `.agent/checks/prove_implementation_quality_gate_validation.py`.

The readiness policy binds those source files, the launcher, the aggregator,
and every exact policy by SHA-256. The report rejects changed source identity,
mode, completion state, assessment IDs, policy bytes, authorization fields, or
repository state.

## Status Vocabulary

Each required runtime control receives exactly one status:

- `satisfied`: exact evidence named by the policy reports
  `verified_enforcement`;
- `related_evidence_only`: a configured metadata observation or bounded fixture
  succeeded, but its scope is narrower than the required control;
- `missing_evidence`: no configured related or satisfying evidence matched.

Metadata and fixture results can never satisfy a control. A verified fixture is
not silently promoted to verified enforcement.

## Required Controls

The pilot currently requires evidence for:

- parent-environment credential isolation;
- provider-credential noninheritance into agent descendants;
- disposable-worktree lifecycle;
- filesystem write scope;
- implementation-session wall-clock timeout;
- model turn budget;
- network isolation;
- bounded output capture;
- implementation-result contract validation;
- runner-enforced output post-validation;
- implementation-patch post-validation;
- implementation-patch receipt validation;
- implementation quality-gate execution;
- quality-gate receipt validation;
- tool allowlist.

The current real-checkout report returns `controls_ready=false`.
Parent-environment credential isolation is satisfied by the exact reconstructed
environment launcher and adversarial child fixture. Provider-credential
noninheritance remains missing because that requires a future real agent
boundary. Disposable worktrees have both observed metadata and one verified
synthetic fixture, but still only related evidence. Filesystem scope, timeout,
and tool allowlisting have only related evidence. Bounded output capture, the
exact implementation-result contract, deterministic patch post-validation,
and independent patch-receipt validation are satisfied by their focused
proofs. Patch candidacy also requires a nonempty change set; a clean worktree
cannot advance merely because untrusted output claimed it changed.
Runner-enforced post-validation remains missing because no
implementation runner yet proves that every invocation calls the validators.
Quality-gate execution has only a bounded synthetic process fixture and
therefore remains related evidence. Independent receipt validation is
satisfied, but it does not authenticate historical build output. Model-turn
budgeting and network isolation have no satisfying evidence.

## Honest Boundary

Even `controls_ready=true` would mean only that every exact evidence rule in
the current policy matched. It would still retain:

```text
authorized=false
agent_invocation_authorized=false
implementation_authorized=false
runner_selected=false
session_start_authorized=false
```

Readiness assessment remains separate from proposal validation, human
authorization, runner selection, invocation, and supervision.

`prepare_disposable_worktree.py`, `validate_disposable_worktree.py`,
`cleanup_disposable_worktree.py`, and
`validate_disposable_worktree_cleanup.py` are intentionally not readiness
evidence sources. Their explicit actions can create, validate, deliberately
remove, and validate the absence of one exact workspace, but they do not prove
that a runner enforces the full lifecycle or cleanup after success, failure,
timeout, or host crash.
