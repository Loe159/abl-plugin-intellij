# Workflow Status

`check_workflow_status.py` reports a bounded capability ledger for the local
agentic workflow pilot. It exists to prevent the number of scripts and passing
tests from being mistaken for an end-to-end autonomous system.

## Run

```text
python .agent/checks/check_workflow_status.py --repo . --format json
```

Exit code `0` means every capability currently marked as required for the pilot
is implemented. Exit code `2` means the ledger is valid but the pilot remains
incomplete. Exit code `1` means a policy, evidence, repository, or I/O error.
The CLI accepts no policy or readiness override.

## Current Boundary

The ledger distinguishes:

- verified local patch and artifact guardrails;
- deterministic implementation-patch production and independent current-state
  receipt validation, without quality-gate or publication authority;
- a bounded offline quality-gate executor whose synthetic mechanism proof is
  not yet authenticated real-execution evidence, plus independent current-state
  validation of its bounded receipt;
- manual-only research and planning rehearsal;
- implementation-session contracts through validated post-consumption launch
  readiness;
- a functional supervised local runner that consumes exact session-start
  authorization, launches a bounded adapter, validates implementation output,
  generates a patch, runs the quality gate, and writes a final receipt;
- runtime-hardening controls that are still not all ready in the real checkout;
- an exact local session-start authorization receipt that does not authenticate
  the authorizer or invoke a runner, plus an exclusive adjacent consumption
  marker with independent current-state validation; it rejects ordinary local
  replay but is not tamper resistant, cross-host, or atomically coupled to
  invocation;
- deterministic draft-PR publication tooling that remains explicit-request
  only and is not authorized by the status check;
- local multi-adapter comparison scaffolding that validates already-captured
  artifacts and metrics without invoking adapters or providers;
- a deferred historical golden set for the current young-repository pilot;
- a local-only draft-PR publication preflight that lists missing external
  controls but does not push, create a PR, authenticate a remote, or authorize
  publication;
- a local-only multi-adapter comparison preflight and validator that list
  missing live adapter, sandbox, context-provenance, provider-authentication,
  and interpretation controls while validating local artifact/metrics evidence;
- manual exact approval of external GitHub issue snapshots that does not
  authenticate GitHub or independently verify labels;
- receipt-derived metrics-observation building plus manual post-run metrics
  recording; this still does not claim trusted runner timestamps, provider
  usage telemetry, billing proof, or correction measurements;
- a golden-set readiness preflight, candidate contract, exact local adoption
  receipt tool, and versioned `evals/golden-set.yaml` status marker; these
  remain available for later, but the current pilot does not require a
  fabricated historical corpus from a repository that has not accumulated
  suitable closed issues.

The checker validates the exact policy, hashes every declared evidence file,
and consumes the current runner-readiness assessment. The functional runner
capability can be implemented while `runner_controls_ready=false`; that means
the local supervised workflow can be exercised, not that network isolation,
provider credential descendant noninheritance, model-turn budget enforcement,
cleanup, or crash-atomic launch coupling are proven.

`historical_golden_set` is deliberately not required for the current pilot.
For a young repository, inventing issues solely to satisfy a benchmark contract
would create low-quality evidence. The golden-set tools stay in the ledger so a
real corpus can be adopted later once closed issues or reviewed task records
exist.

The result also includes `runner_unready_controls`, a compact projection of
every runner-readiness control whose status is not `satisfied`. This is
diagnostic evidence only; it does not change the ledger's authorization or
readiness rules.

Every result retains all authorization, invocation, runner-selection,
repository-mutation, network, publication, and session-start fields as false.
This status is documentation backed by current local evidence, not an
authorization mechanism or a claim that absent capabilities are impossible to
implement.
