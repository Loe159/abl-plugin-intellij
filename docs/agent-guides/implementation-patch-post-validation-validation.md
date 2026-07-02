# Implementation Patch Post-Validation Receipt Validation

`validate_implementation_patch_receipt.py` independently checks one exact
post-validation receipt against the current implementation result, session
identity, retained patch, implementation workspace, diff policy, risk rules,
and trusted producer bytes.

It does not prove when or by whom the receipt was produced. It does not invoke
an agent, execute the plugin quality gate, approve a patch, authorize
publication, commit, push, or open a pull request.

## Run

All four evidence files must be distinct regular files outside the trusted
source checkout and implementation workspace:

```text
python .agent/checks/validate_implementation_patch_receipt.py \
  --repo <trusted-source-checkout> \
  --result <external-path>/result.json \
  --expected-session <external-path>/expected-session.json \
  --patch <external-path>/patch.diff \
  --receipt <external-path>/patch-validation.json \
  --receipt-sha256 <expected-lowercase-sha256> \
  --format json
```

The validator requires a retained patch. A producer receipt that records
`retained=false`, for example after detecting a high-confidence secret, cannot
be independently validated because the rejected bytes are intentionally
unavailable.

## Checks

The validator:

- verifies the expected receipt digest and canonical JSON bytes;
- revalidates the exact implementation result and session identity;
- verifies the patch digest, size, path, facts, and current worktree match;
- reapplies the exact diff policy and supervision-risk rules;
- recomputes `patch_candidate_ready`, including the nonempty-patch requirement;
- requires the quality gate to remain required, incomplete, and not passed;
- checks the producer and validator bindings against current trusted bytes;
- rejects changes to the inputs, workspace, or validator during validation.

A policy-blocked retained patch may have `valid=true` while
`patch_candidate_ready=false`. Validity means that the receipt accurately
describes the current blocked evidence, not that the policy block was waived.
The same distinction applies to an empty retained patch: it can be described
accurately, but there is no implementation change to send to the quality gate.

## Proof

```text
python .agent/checks/prove_implementation_patch_receipt_validation.py \
  --repo . \
  --format json
```

The proof uses disposable Git repositories to verify an allowed receipt, a
protected-path receipt routed to `C`, an empty receipt that remains
non-candidate, and rejection after patch tampering.

## Honest Boundary

This satisfies only `implementation_patch_receipt_validation`.
`runner_enforced_output_post_validation` remains missing until a real runner
atomically connects bounded capture, result validation, patch production, and
receipt validation. `implementation_quality_gate_execution` also remains
missing.

`valid=true` is current-state integrity evidence. It is not historical
producer proof, approval, runner telemetry, permission to merge, or permission
to publish.
