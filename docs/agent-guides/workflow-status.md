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
  readiness, without runner selection or execution;
- runner controls that are still not ready in the real checkout;
- an exact local session-start authorization receipt that does not authenticate
  the authorizer or invoke a runner, plus an exclusive adjacent consumption
  marker with independent current-state validation; it rejects ordinary local
  replay but is not tamper resistant, cross-host, or atomically coupled to
  invocation;
- missing deterministic draft-PR publication, an authenticated historical
  golden set, and multi-adapter comparison;
- a local-only draft-PR publication preflight that lists missing external
  controls but does not push, create a PR, authenticate a remote, or authorize
  publication;
- a local-only multi-adapter comparison preflight that lists missing adapter,
  sandbox, context, validation, and metric-interpretation controls without
  invoking adapters or model providers;
- manual exact approval of external GitHub issue snapshots that does not
  authenticate GitHub or independently verify labels;
- manual post-run metrics recording that does not claim automatic runner or
  provider telemetry.
- a golden-set readiness preflight and candidate contract that can validate
  local reference commits but cannot authenticate GitHub issue state or select
  the historical corpus.

The checker validates the exact policy, hashes every declared evidence file,
and consumes the current runner-readiness assessment. A future satisfying
runner assessment can update only that capability; it cannot make the whole
pilot ready while other required capabilities remain missing.

Every result retains all authorization, invocation, runner-selection,
repository-mutation, network, publication, and session-start fields as false.
This status is documentation backed by current local evidence, not an
authorization mechanism or a claim that absent capabilities are impossible to
implement.
