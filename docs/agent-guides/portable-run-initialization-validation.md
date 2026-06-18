# Portable Run Initialization Validation

`validate_portable_run_initialization.py` independently checks that one
external initialization receipt still describes one exact current portable
run. It is a read-only consumer of initialization evidence, not part of the
initializer and not an approval mechanism.

## Run

Carry the SHA-256 reported by `initialize_portable_run.py` separately from the
receipt, then run:

```text
python .agent/checks/validate_portable_run_initialization.py \
  --repo <clean-checkout> \
  --run <external-run-directory> \
  --receipt <external-initialization-receipt.json> \
  --receipt-sha256 <separately-carried-receipt-sha256> \
  --format json
```

The CLI accepts no policy override. Exit code `0` means the current receipt and
run are valid under the exact repository controls. Exit code `2` means a
deterministic validation rule rejected them. Exit code `1` means an input,
policy, Git, parsing, or I/O error.

## Validation Contract

The validator requires:

- a valid external five-artifact run at the exact initial statuses;
- an external receipt outside the checkout and run;
- a separately carried SHA-256 matching the receipt before parsing;
- the exact initialization receipt schema and all false authorization fields;
- receipt identity matching the current run, issue, risk, and base;
- an exact manifest matching every current artifact byte and initial status;
- exact trusted initializer, helper, template, and policy bindings;
- no high-confidence secret signature in the current run;
- a clean checkout whose `HEAD` equals the receipt base.

Before reporting success, it rechecks the receipt bytes, complete run snapshot,
repository state, and exact validator bytes. It does not write the run,
receipt, checkout, or any result file.

`approve_task.py` consumes this validator as its single receipt-validation
source. A task cannot be approved unless this independent check reports
`valid=true`. After task approval, the run intentionally differs from the
initial manifest and validation returns `valid=false`.

## Honest Boundary

`valid=true` proves only that the current receipt and current initial run match
the exact local contracts and bytes checked now. It does not prove who created
the receipt, authenticate the source reference, prove that task claims or risk
are correct, or prove that no unobserved earlier state existed. SHA-256 is not
a signature.

Every result retains:

```text
authorized=false
task_approved=false
task_approval_authenticated=false
research_ready=false
stage_start_authorized=false
agent_invocation_authorized=false
```

Validation never approves the task, starts research, invokes an agent, selects
a runner, or authorizes repository, network, or publication actions.
