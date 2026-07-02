# Multi-Adapter Comparison Readiness

`check_multi_adapter_comparison_readiness.py` is a local preflight boundary for
a future multi-adapter comparison workflow. It does not invoke adapters, call a
model provider, contact a network service, mutate the repository, compare live
outputs, or record metrics.

`validate_multi_adapter_comparison.py` adds a deterministic local scaffold for
already-captured evidence. It validates a manifest that names at least two
distinct adapters, local artifact files, and local run-metrics records, checks
their SHA-256 digests, and emits a normalized metric table. It does not select a
winner or authenticate the provider, observer, adapter process, or historical
producer.

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

## Validate Local Comparison Evidence

```text
python .agent/checks/validate_multi_adapter_comparison.py \
  --repo . \
  --manifest <external-or-local-comparison-manifest.json> \
  --format json
```

The manifest uses exact JSON fields:

```json
{
  "manifest_version": 1,
  "purpose": "multi_adapter_comparison_manifest",
  "mode": "local-artifact-and-metrics-comparison-only",
  "comparison_id": "issue-17-implement",
  "task": {
    "id": "issue-17",
    "issue": 17,
    "stage": "implement",
    "base_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "context_sha256": "<64 lowercase hexadecimal characters>"
  },
  "candidates": [
    {
      "candidate_id": "codex",
      "adapter": {"id": "codex", "version": "manual-pilot"},
      "model": {"provider": "local", "id": "unknown"},
      "artifact": {
        "role": "complete_patch",
        "path": "codex.patch",
        "sha256": "<64 lowercase hexadecimal characters>"
      },
      "metrics_record": {
        "path": "codex-metrics.json",
        "sha256": "<64 lowercase hexadecimal characters>"
      }
    },
    {
      "candidate_id": "aider",
      "adapter": {"id": "aider", "version": "manual-pilot"},
      "model": {"provider": "local", "id": "unknown"},
      "artifact": {
        "role": "complete_patch",
        "path": "aider.patch",
        "sha256": "<64 lowercase hexadecimal characters>"
      },
      "metrics_record": {
        "path": "aider-metrics.json",
        "sha256": "<64 lowercase hexadecimal characters>"
      }
    }
  ],
  "manual_interpretation": {
    "required": true,
    "winner_selected": false
  }
}
```

Relative artifact and metrics paths resolve from the manifest directory. Each
candidate metrics record must match the task issue, stage, base commit,
adapter, and model declared by the manifest. `complete_patch` artifacts must
also match the metrics record's `diff.sha256`.

The command returns exit code `0` only when the local bytes match the manifest
and policy. Its output may include `local_comparison_calculated=true` and
`local_artifacts_compared=true`, but keeps live execution and authorization
fields false.

## Current Boundary

The readiness preflight binds only local files and reports both the local
scaffold now available and the controls still missing before any real
multi-adapter run could be treated as ready.

Available local scaffold:

- bounded comparison manifest;
- local artifact digest validation;
- metrics-record digest validation;
- deterministic metric table.

Controls still missing:

- reviewed adapter contracts for each candidate;
- validated identical stage-context provenance;
- sandbox controls for adapter invocation;
- captured output validation from each adapter;
- provider usage authentication;
- manual metric interpretation.

Every output keeps these fields false:

```text
authorized=false
adapter_invocation_authorized=false
model_invocation_authorized=false
network_authorized=false
repository_mutation_authorized=false
external_service_written=false
publication_authorized=false
winner_selected=false
comparison_executed=false
metrics_recorded=false
```

`metrics_recorded=false` means the comparison validator does not create or
authenticate new metrics records. It may still read already captured metrics
records and verify that their declared task, adapter, model, stage, base
commit, and patch digest match the comparison manifest.

## Honest Boundary

These checks are inventory and local-evidence boundaries, not a comparison
runner. A valid comparison result says only that the current local manifest,
artifact bytes, and metrics-record bytes match the contract. A future
multi-adapter workflow must separately prove how adapters are selected,
invoked, bounded, captured, authenticated, validated, compared, and interpreted.
