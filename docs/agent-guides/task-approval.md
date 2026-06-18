# Exact Task Approval

`approve_task.py` governs the only current transition from an initialized
`task.md: awaiting_approval` to `task.md: approved`.

This is a local semantic decision separate from portable-run initialization,
stage readiness, stage authorization, and agent invocation. Approval means
only that the declared local approver accepts the exact initialized task as
the bounded workflow task.

## Two-Step Procedure

Keep the external initialization receipt and its SHA-256 reported by
`initialize_portable_run.py`. Review the exact task, then request a
content-bound confirmation:

```text
python .agent/checks/approve_task.py check \
  --repo <clean-checkout> \
  --run <external-run-directory> \
  --receipt <external-initialization-receipt.json> \
  --receipt-sha256 <separately-carried-receipt-sha256> \
  --approval-receipt <external-absent-task-approval-receipt.json> \
  --approver <local-approver-id>
```

`check` is read-only. A successful result reports `approvable=true` and prints
`required_confirmation`. That phrase binds:

- the unauthenticated approver declaration;
- issue, declared risk, and base commit;
- the exact initialization receipt SHA-256;
- a deterministic SHA-256 snapshot of all five initial artifacts;
- the exact current `task.md` SHA-256;
- the exact trusted task-approval controls and imported helper bytes.
- the external absent path reserved for the task-approval receipt.

After reviewing the task and phrase, pass the phrase unchanged:

```text
python .agent/checks/approve_task.py approve \
  --repo <clean-checkout> \
  --run <external-run-directory> \
  --receipt <external-initialization-receipt.json> \
  --receipt-sha256 <separately-carried-receipt-sha256> \
  --approval-receipt <same-external-absent-task-approval-receipt.json> \
  --approver <same-local-approver-id> \
  --confirm "<exact-required-confirmation>"
```

The CLI accepts no policy override. Exit code `0` means `check` found an
approvable exact task or `approve` completed the status transition. Exit code
`2` means a deterministic rule blocked it. Exit code `1` means a tool, input,
policy, Git, validation, or I/O error.

## Preconditions And Mutation

Both actions require:

- independent initialization validation to report `valid=true`;
- a valid external five-artifact run at its exact initial statuses;
- an external initialization receipt outside the run;
- an external absent task-approval receipt path outside the checkout and run;
- a separately carried receipt SHA-256 matching the exact receipt bytes;
- an exact receipt schema, initial manifest, and trusted initialization
  bindings;
- `task.md` at exactly `awaiting_approval`;
- repository `HEAD` equal to the task base commit;
- a clean repository worktree;
- no high-confidence secret signature in the run or approver declaration.

`approve` repeats the complete assessment after confirmation. Immediately
before mutation, it rechecks the run snapshot, task bytes, initialization
receipt bytes, and task-approval control bindings. It validates a complete
candidate run and constructs a bounded task-approval receipt binding:

- the initialization receipt SHA-256;
- the exact confirmation SHA-256 and approver declaration;
- issue, risk, base commit, and external run;
- exact run snapshots and task bytes before and after approval;
- exact task-approval controls and imported helper bytes.

The tool writes the approval receipt exclusively before atomically changing
the task status line. Before the task change, that receipt deliberately does
not match the run and cannot serve as valid approval evidence. After mutation,
the tool verifies the complete run, research readiness, receipt bytes, and
expected post-approval hashes.

On a handled receipt-write or post-mutation failure, the tool removes the
receipt it created and restores the original task only when the task still
matches its exact candidate bytes. It reports whether this bounded rollback
succeeded.

Receipt interpretation is not duplicated in this tool. It consumes
`validate_portable_run_initialization.py` as the single independent
receipt-validation source.

After approval, the initialization receipt deliberately no longer matches the
current run manifest, so it cannot approve the task again. The declared
`research` prerequisites become ready, but readiness remains only a
consistency result.

The task-approval receipt is durable traceability data. Its independent
read-only consumer is documented in
`docs/agent-guides/task-approval-validation.md`. Current generic stage
readiness still checks artifact statuses only and does not consume that
validation, so it does not prove that an approved status came from this
control. Making approval validation a readiness prerequisite is a separate
later step.

## Honest Boundary

Every result retains false authorization fields, including:

```text
authorized=false
task_approval_authenticated=false
stage_start_authorized=false
agent_invocation_authorized=false
```

The confirmation binds exact bytes and makes one local decision explicit. It
does not prove that a human typed the command, authenticate the approver,
verify organizational authority, prove that the task claims are true, or
prove that the declared risk is correct. SHA-256 is not a signature. Any actor
already able to run the tool can automate both steps.

A process crash cannot be rolled back by Python exception handling. A crash
before the task mutation may leave an invalid receipt beside an unapproved
task; a crash after the atomic task mutation may leave an approved task and
matching receipt. Consumers must validate both together rather than infer
approval from receipt existence alone.

The tool does not start research, invoke an agent, mutate the repository,
authorize network access, or authorize publication. A later stage must still
use the separate readiness, context, output-validation, and application
controls.
