# Implementation Runner Control Readiness

`assess_runner_readiness.py` aggregates the current local metadata audit,
bounded disposable-worktree fixture, and bounded timeout fixtures into one
fail-closed control-readiness report. It does not validate a proposal, select a
runner, invoke an agent, or authorize a session.

## Run

```text
python .agent/checks/assess_runner_readiness.py --repo . --format json
```

The CLI accepts no policy or evidence override. It executes the seventeen fixed
local evidence sources:

- `.agent/checks/audit_local_runner.py`;
- `.agent/checks/prove_runner_tool_allowlist.py`;
- `.agent/checks/prove_local_adapter_environment_filter.py`;
- `.agent/checks/prove_disposable_worktree.py`;
- `.agent/checks/prove_wall_clock_timeout.py`;
- `.agent/checks/prove_windows_process_tree_timeout.py`;
- `.agent/checks/prove_parent_environment_isolation.py`;
- `.agent/checks/prove_bounded_output_capture.py`;
- `.agent/checks/prove_implementation_launch_transaction.py`;
- `.agent/checks/prove_implementation_result_validation.py`;
- `.agent/checks/prove_runner_output_post_validation.py`;
- `.agent/checks/prove_supervised_runner_execution.py`;
- `.agent/checks/run_supervised_implementation.py` contract assessment;
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
- authorization-consumption-to-process-start coupling;
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
noninheritance has related environment-only evidence from the local
implementation adapter's filtered child environment, but remains unsatisfied
because files, operating-system credential stores, deliberate provider-specific
credential channels, and a future real agent boundary are not covered.
Disposable worktrees have observed metadata, one verified synthetic
fixture, supervised-runner contract evidence for optional cleanup after a
successful run, and a supervised-runner fixture that observes cleanup receipt
retention after a successful candidate run. The runner contract and fixture
also cover optional cleanup after a controlled blocked stage, such as invalid
implementation output, when `--cleanup-receipt-output` is supplied. The runner
also validates the retained cleanup receipt through the separate cleanup
validator after cleanup succeeds. The supervised-runner fixture also observes a
captured adapter timeout result being rejected before result retention, patch
generation, and quality-gate execution, with optional cleanup and cleanup
receipt validation on that controlled path. This is still only related
evidence. It does not cover cleanup after arbitrary failure,
forced process termination outside the captured runner path, host crash, or concurrent mutation. Filesystem scope has related
metadata and contract evidence: the runner passes the disposable workspace as
the adapter working directory and requires generated runner artifacts to be
external, absent, distinct, and outside both the source checkout and
implementation workspace. This still does not prove a filesystem sandbox or
deny arbitrary absolute writes by a child process. Timeout has
only related evidence. The supervised-runner contract now proves that its
`adapter_timeout_seconds` value fits inside the `isolated_process.py` maximum
direct-child timeout, preventing a local policy mismatch before adapter launch;
the supervised-runner fixture also observes that a timeout already captured by
the adapter launcher blocks before patch generation and the quality gate. That
is still narrower than a complete session deadline, arbitrary process tree
timeout, or crash-safe timeout cleanup. Tool
allowlisting is satisfied by a bounded enforcement proof that shows the
supervised runner rejects a non-allowlisted adapter entrypoint before
authorization consumption and recognizes the repo-local adapter entrypoint.
That proof does not execute an adapter, invoke an agent, or prove provider
command behavior. Bounded output capture, the
exact implementation-result contract, deterministic patch post-validation,
and independent patch-receipt validation are satisfied by their focused
proofs. Patch candidacy also requires a nonempty change set; a clean worktree
cannot advance merely because untrusted output claimed it changed.
The local claim-before-spawn proof supplies related fixture evidence only:
it leaves a crash window and does not consume a real authorization chain. The
supervised-runner fixture also observes the runner's own sequence
`consume authorization -> check launch readiness -> run adapter` before an
invalid-output block, but that remains fixture evidence and does not prove
crash-safe atomicity or cross-host replay prevention.
Runner-enforced post-validation is satisfied by a supervised-runner fixture
that executes the actual runner core with fixture consumption and launch-ready
inputs. It verifies an invalid captured result is rejected before the result
file is retained, before patch generation, and before the quality gate. The
same proof observes a captured adapter-timeout path being blocked before patch
generation and quality-gate execution. It uses fixture patch and quality-gate
executors only to observe the later quality-gate sequence after a candidate-ready
patch result and fixture cleanup after successful completion and controlled
blocked completion; it does not prove real patch generation, real Gradle
execution, real authorization consumption, or cleanup after arbitrary failure,
forced process termination outside the controlled runner path, or host crash.
The cleanup receipt validation in that proof uses fixture cleanup
receipts and therefore remains narrower than a real destructive cleanup
receipt validation. A separate synthetic wrapper still supplies narrower related
evidence by invoking the implementation-result validator and detecting a bypass
record. The local supervised implementation runner is also accounted for as
contract-only related evidence: its exact policy requires authorization
consumption before adapter execution, bounded adapter execution through
`isolated_process.py`, implementation-result validation before retaining
output, patch post-validation before the quality gate, and quality-gate receipt
validation. The runner also validates its final receipt after writing by
checking current receipt bytes, bindings, and referenced artifacts; the
supervised-runner fixture observes this validation in both a controlled blocked
run and a successful fixture run. This still does not prove provider-credential descendant
noninheritance, network isolation, cross-host replay prevention, crash-atomic
authorization-consumption-to-process-start coupling, or cleanup after runner
completion, so it cannot make `controls_ready=true` by itself.
Quality-gate execution has only a bounded synthetic process fixture and
therefore remains related evidence. Independent receipt validation is
satisfied, but it does not authenticate historical build output. Model-turn
budgeting now has related contract evidence from the implementation-session
policy's declared `max_turns=12` budget, but the runner still does not enforce
provider turn consumption. Network isolation now has related contract evidence
that the supervised runner policy does not request network or publication, but
there is still no OS-level sandbox proof, provider-boundary proof, or live
adapter network-denial proof.

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
