# Stage Application Receipt Validation

`validate_stage_application.py` is a read-only consumer for one
stage-application receipt produced by `apply_stage_output.py`. It validates
that the receipt still matches the current external run and repository state.

It never applies an artifact, approves research or a plan, starts an agent, or
authorizes a later stage.

## Run

Carry the receipt SHA-256 separately from the applying command:

```text
python .agent/checks/validate_stage_application.py \
  --repo . \
  --run <external-run-directory> \
  --application-receipt <external-path>/stage-application-receipt.json \
  --application-receipt-sha256 <trusted-apply-sha256> \
  --format json
```

Exit code `0` means the receipt validates against the current state, `2`
means the receipt or current state is rejected, and `1` means a tool, policy,
input, or I/O error.

## Checked Evidence

The validator checks:

- receipt SHA-256 before parsing JSON;
- exact receipt schema and false authorization metadata;
- external run and receipt paths outside both the checkout and run;
- no symbolic links for the run, receipt, or contracted artifacts;
- the current five-artifact run contract;
- repository `HEAD` and clean worktree;
- current run snapshot against the receipt's post-application snapshot;
- current target artifact digest against the receipt's response digest;
- confirmation digest reconstructed from the receipt and trusted controls;
- trusted stage-application bindings;
- high-confidence secret signatures in run artifacts and reviewer declaration.

## Limits

`valid=true` is current-state integrity evidence, not historical proof. The
validator does not reopen the original bundle or captured response, and it
cannot prove that a human typed the confirmation. SHA-256 is used for local
integrity checks; it is not a signature.

`build_stage_context.py` now uses this validator as the provenance gate for
`plan` context preparation: planning may consume completed research only when
the current run still matches a validated operator-confirmed research
application receipt. That remains context-integrity evidence, not approval of
the research claims or authorization to start planning.
