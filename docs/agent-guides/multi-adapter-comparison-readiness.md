# Multi-Adapter Comparison Readiness

`check_multi_adapter_comparison_readiness.py` is a local preflight boundary for
a future multi-adapter comparison workflow. It does not invoke adapters, call a
model provider, contact a network service, mutate the repository, compare
outputs, or record metrics.

## Run

```text
python .agent/checks/check_multi_adapter_comparison_readiness.py \
  --repo . \
  --format json
```

Exit code `0` would mean the exact local preflight reports
`comparison_ready=true`. The current expected result is exit code `2` with
`comparison_ready=false`. Exit code `1` means policy, repository, or I/O
failure. The CLI accepts no policy, adapter, model, provider, network, or
metric override.

## Current Boundary

The preflight binds only local files and reports the controls still missing
before any real comparison could be treated as ready:

- an explicit comparison task;
- at least two reviewed adapter contracts;
- bounded identical stage context for all adapters;
- sandbox controls for adapter invocation;
- captured output validation;
- manual metric interpretation.

Every output keeps these fields false:

```text
authorized=false
adapter_invocation_authorized=false
model_invocation_authorized=false
network_authorized=false
repository_mutation_authorized=false
external_service_written=false
comparison_executed=false
metrics_recorded=false
```

## Honest Boundary

This check is an inventory boundary, not a comparison runner. A future
multi-adapter workflow must separately prove how adapters are selected,
invoked, bounded, captured, validated, compared, and interpreted.
