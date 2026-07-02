# Provenance-Aware Research Readiness

`check_research_readiness.py` composes two separate read-only checks before a
research context may be prepared:

- declared `research` prerequisites from `check_stage_readiness.py`;
- independent task-approval validation from `validate_task_approval.py`.

It reports readiness only when both checks pass. It does not authorize or
start research, authenticate the approver, invoke an agent, or mutate the run
or repository.

## Run

Carry the task-approval receipt SHA-256 reported by `approve_task.py`
separately:

```text
python .agent/checks/check_research_readiness.py \
  --repo <clean-checkout> \
  --run <external-approved-run-directory> \
  --approval-receipt <external-task-approval-receipt.json> \
  --approval-receipt-sha256 <separately-carried-sha256> \
  --format json
```

Exit code `0` means declared readiness and approval provenance both validate,
`2` means a deterministic prerequisite failed, and `1` means an input,
policy, Git, validation, or I/O error.

The CLI accepts no policy override. An approved status without an existing
valid approval receipt reports `ready=false`.

## Contract

The exact policy in `.agent/policies/research-readiness.json` requires:

- the fixed stage `research`;
- declared research readiness;
- valid task-approval provenance;
- unchanged exact research-readiness controls during the check;
- every authorization and authentication field to remain false.

`build_stage_context.py` consumes this gate twice for `research`: once before
building and once immediately before writing its external bundle. The
version-3 research bundle records the separately carried approval-receipt
SHA-256 used by the gate. The bundle digest therefore binds captured output to
that approval-provenance digest.

## Honest Boundary

This gate strengthens the provenance required to prepare research, but
readiness remains a precondition result rather than authorization. It inherits
the approval validator's limits: no authenticated human identity, no proof of
historical producer execution, no proof that task claims or risk are correct,
and no signature.

The generic stage-readiness engine remains status-based. Planning context
preparation adds its own provenance gate for the operator-confirmed research
application receipt, documented in `docs/agent-guides/stage-context.md`.
