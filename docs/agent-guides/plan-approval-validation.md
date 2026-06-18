# Independent Plan-Approval Validation

`validate_plan_approval.py` independently checks one exact external
plan-approval receipt against its exact current approved portable run and
clean checkout.

It is a read-only integrity and provenance check. It does not authenticate the
approver, authorize implementation, start an agent, mutate the run, mutate the
repository, or publish anything.

## Run

Carry the SHA-256 reported by `approve_plan.py` separately from the receipt:

```text
python .agent/checks/validate_plan_approval.py \
  --repo <clean-checkout> \
  --run <external-approved-run-directory> \
  --approval-receipt <external-plan-approval-receipt.json> \
  --approval-receipt-sha256 <separately-carried-sha256> \
  --format json
```

Exit code `0` means the exact current approval validates, `2` means a
deterministic rule rejected it, and `1` means an input, policy, Git,
validation, or I/O error.

The CLI accepts no policy override.

## Verified Contract

Before reporting `valid=true`, the validator checks:

- the separately carried receipt SHA-256 before parsing;
- the exact receipt schema, purpose, mode, and false authorization fields;
- the exact trusted plan-approval bindings;
- the external run and receipt paths, with no symbolic-link inputs;
- the complete artifact contract and exact approved plan identity;
- the unique reversible frontmatter `awaiting_approval` to `approved`
  transition;
- reconstructed plan and run hashes before and after approval;
- the reconstructed exact approval confirmation and its receipt-path binding;
- current implementation readiness, repository base, and clean worktree;
- absence of high-confidence secret signatures;
- unchanged receipt, run, repository, and validator controls at completion.

The validator does not need the applied-plan receipt bytes. It verifies that
the plan-approval receipt carries a valid applied-plan receipt SHA-256 and
binds it into the reconstructed confirmation. Independent validation of the
applied-plan receipt can be performed separately when a consumer needs that
provenance chain.

## Honest Boundary

`valid=true` proves that the exact current approved run, receipt,
reconstructed transition, and trusted local controls agree at validation time.
It does not prove historical execution of `approve_plan.py`, authenticate the
approver, prove organizational authority, prove the plan is correct, authorize
implementation, or make SHA-256 a signature.

An actor able to forge the receipt and current run while preserving all bound
values can reproduce this local integrity evidence. Implementation handoff now
uses this validator as a prerequisite, but validation itself never authorizes
or starts implementation.
