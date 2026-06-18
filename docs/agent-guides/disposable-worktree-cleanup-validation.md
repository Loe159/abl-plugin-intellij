# Disposable Worktree Cleanup Receipt Validation

`validate_disposable_worktree_cleanup.py` independently consumes one exact
preparation receipt and one exact cleanup receipt, then compares them with the
current source repository and absent workspace path. It is read-only and does
not clean up, authorize, invoke, or supervise anything.

## Run

Carry both expected receipt SHA-256 values separately from their files:

```text
python .agent/checks/validate_disposable_worktree_cleanup.py \
  --source <clean-source-checkout> \
  --workspace <removed-external-worktree-path> \
  --preparation-receipt <external-preparation-receipt.json> \
  --preparation-receipt-sha256 <expected-preparation-sha256> \
  --cleanup-receipt <external-cleanup-receipt.json> \
  --cleanup-receipt-sha256 <expected-cleanup-sha256> \
  --format json
```

The CLI accepts no policy override. Its exact policy is
`.agent/policies/disposable-worktree-cleanup-validation.json`.

Exit code `0` means the exact receipts and observed current state are valid,
`2` means a deterministic rule rejected them, and `1` means an input, policy,
Git, parsing, or I/O error.

## Validation Scope

The validator:

- verifies each separately supplied digest before parsing its receipt;
- requires exact receipt schemas, false authorization fields, identities,
  declared invariants, postconditions, and trusted byte bindings;
- requires both receipts to identify the same source, workspace, base commit,
  and preparation-receipt SHA-256;
- requires receipts and the absent workspace path to remain outside the source;
- requires both receipts to remain outside the absent workspace path;
- requires the source to remain clean and at the exact preparation base;
- requires the workspace path to remain absent and unregistered from Git;
- rechecks both receipts, source state, workspace absence, registration
  absence, and validator bindings before returning success.

Every result retains:

```text
authorized=false
agent_invocation_authorized=false
implementation_authorized=false
runner_selected=false
session_start_authorized=false
workspace_use_authorized=false
```

## Honest Boundary

`valid=true` means only that the exact receipts are internally consistent and
match the observed current state during validation. It does not prove which
uncommitted files were discarded, that all other worktree registrations were
historically unchanged, why cleanup happened, or that a runner performs
cleanup after success, failure, timeout, or host crash.

The validator is a separate consumer-side command, but reuses versioned parsing
and Git-observation helpers from the preparation validator. It is not a
cryptographically independent implementation. SHA-256 binds exact bytes but is
not a signature. An actor controlling both receipt files and both separately
carried digests can fabricate a structurally coherent pair; this validator
does not authenticate who performed cleanup.

The workspace path or source repository may change immediately after
validation. This result is intentionally not a runner-readiness evidence
source and grants no authorization.
