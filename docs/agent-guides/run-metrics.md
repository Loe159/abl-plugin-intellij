# Run Metrics

`record_run_metrics.py` creates one bounded JSON metrics record from an
explicit post-run observation and, when available, an exact complete patch.
It is intentionally a bounded evidence boundary until an enforced runner can
supply trusted timestamps, provider usage, and outcomes.

`build_runner_metrics_observation.py` can derive the observation identity,
outcome, and patch digest from a validated supervised-runner final receipt. It
still requires the operator to supply start/completion timestamps and model
identity explicitly, and it records token and cost data as unavailable.

## Observation Contract

The observation is external to the checkout and uses exact JSON fields. It
records:

- run, issue, stage, base commit, adapter, and model identifiers;
- UTC start and completion timestamps;
- token usage and cost as `reported`, `estimated`, or `unavailable`;
- outcome status and measured or unassessed human corrections;
- final disposition and regression status;
- whether a diff is measured or not applicable.

Cost uses integer `amount_microunits`, where one currency unit equals one
million microunits. This avoids floating-point rounding while retaining
sub-cent values. An unavailable value must be `null`; zero is a real measured
or estimated value and cannot stand in for unknown data.

A successful `implement` observation must bind an external complete patch by
SHA-256. A blocked implementation run that stopped before patch production may
use `diff_status: "not_applicable"` with `patch_sha256: null`. When a patch is
measured, the checker calculates duration, patch size, file count, changed
lines, additions, deletions, paths, binary paths, and symbolic-link paths. It
refuses a digest mismatch or malformed patch.

Example implementation observation:

```json
{
  "observation_version": 1,
  "purpose": "agentic_run_metrics_observation",
  "mode": "post-run-observation",
  "run_id": "issue-17-run-1",
  "issue": 17,
  "stage": "implement",
  "base_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "adapter": {
    "id": "codex",
    "version": "manual-pilot"
  },
  "model": {
    "provider": "openai",
    "id": "unknown"
  },
  "timing": {
    "started_at": "2026-06-17T10:00:00Z",
    "completed_at": "2026-06-17T10:02:03.456Z"
  },
  "tokens": {
    "status": "unavailable",
    "source": "unavailable",
    "input_tokens": null,
    "output_tokens": null
  },
  "cost": {
    "status": "estimated",
    "source": "manual_estimate",
    "amount_microunits": 12500,
    "currency": "EUR"
  },
  "outcome": {
    "status": "succeeded"
  },
  "human_corrections": {
    "status": "measured",
    "count": 2
  },
  "final_disposition": "pending",
  "regression_status": "not_assessed",
  "diff_status": "measured",
  "patch_sha256": "<64 lowercase hexadecimal characters>"
}
```

## Check Before Writing

When starting from the supervised runner, first derive a bounded observation
from the validated final receipt:

```text
python .agent/checks/build_runner_metrics_observation.py \
  --repo . \
  --final-receipt <external-run>/final-receipt.json \
  --final-receipt-sha256 <separately-carried-sha256> \
  --run-id issue-17-run-1 \
  --started-at 2026-06-17T10:00:00Z \
  --completed-at 2026-06-17T10:02:03Z \
  --model-provider openai \
  --model-id unknown \
  --output <external-run>/metrics-observation.json \
  --format json
```

This builder validates the final receipt with
`.agent/checks/validate_supervised_runner_receipt.py`, derives only fields
present in that receipt, writes the observation once, and leaves all
authorization fields false. It does not authenticate timestamps, query a
provider, infer token usage, or create the metrics record.

```text
python .agent/checks/record_run_metrics.py check \
  --repo . \
  --observation <external-observation.json> \
  --record <external-absent-metrics.json> \
  --patch <external-complete.patch> \
  --format json
```

Omit `--patch` only when `diff_status` is `not_applicable`. The `check`
subcommand computes the exact record and digest without writing it.

## Record Once

```text
python .agent/checks/record_run_metrics.py record \
  --repo . \
  --observation <external-observation.json> \
  --record <external-absent-metrics.json> \
  --patch <external-complete.patch> \
  --format json
```

The record is written with exclusive creation and is never overwritten. It
contains source and policy-binding hashes, but no transcript or patch content.

## Validate A Recorded File

Carry the `record_sha256` returned by `record` separately, then revalidate the
file against the same observation and patch:

```text
python .agent/checks/record_run_metrics.py validate \
  --repo . \
  --observation <external-observation.json> \
  --record <external-metrics.json> \
  --record-sha256 <sha256-from-record-command> \
  --patch <external-complete.patch> \
  --format json
```

Validation checks the separately carried digest and requires the recorded bytes
to equal the record recalculated from current exact evidence.

## Boundary

These tools do not invoke an agent, observe a process, query a provider, verify
a provider invoice, authenticate the observer, assess post-merge regressions,
or decide that a run should be merged. Receipt-derived observations prove only
that current receipt bytes and referenced artifacts validate. `reported` and
`estimated` are explicit provenance labels, not independent proof.
`unavailable`, `not_assessed`, and `pending` remain valid and preferable to
invented precision.

Every authorization, runner-selection, repository-mutation, network,
publication, and session-start field remains false. A metrics record is
comparison evidence only.
