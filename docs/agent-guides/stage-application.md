# Operator-Confirmed Stage Application

`apply_stage_output.py` is the first pilot tool allowed to mutate a workflow
run. It can atomically replace exactly one external run artifact with a
structurally accepted read-only stage response and write a bounded external
application receipt for that exact copy operation.

It deliberately separates:

- structural acceptance of model output;
- operator confirmation of one exact copy operation;
- later approval of the artifact's meaning.

Applying a plan does not approve it. A plan response remains
`status: awaiting_approval`; a separate future control must govern the
transition to `approved`. That separate local control is documented in
`docs/agent-guides/plan-approval.md`.

## Two-Step Procedure

First inspect the captured response, then ask the tool to revalidate all inputs
and print the exact content-bound confirmation:

```text
python .agent/checks/apply_stage_output.py check \
  --repo . \
  --run <external-run-directory> \
  --bundle <external-path>/research-context.json \
  --bundle-sha256 <trusted-builder-sha256> \
  --response <external-path>/captured-response.md \
  --application-receipt <external-path>/stage-application-receipt.json
```

`check` is read-only. A successful result reports `applicable=true` and prints
`required_confirmation`. That phrase binds:

- stage and target artifact;
- expected bundle SHA-256;
- a deterministic SHA-256 snapshot of all five current run artifacts;
- the deterministic post-copy run snapshot;
- captured response SHA-256;
- SHA-256 of the exact target content that would be replaced;
- the exact trusted application-control bindings;
- the reserved absent external receipt path.

The receipt path must be outside both the Git checkout and the portable run,
must not be a symbolic link, and must not already exist.

After reviewing that operation, pass the phrase unchanged and declare a short
operator identifier:

```text
python .agent/checks/apply_stage_output.py apply \
  --repo . \
  --run <external-run-directory> \
  --bundle <external-path>/research-context.json \
  --bundle-sha256 <trusted-builder-sha256> \
  --response <external-path>/captured-response.md \
  --application-receipt <external-path>/stage-application-receipt.json \
  --reviewer <local-operator-id> \
  --confirm "<exact-required-confirmation>"
```

The operator identifier permits only letters, digits, dot, underscore, `@`,
and hyphen. High-confidence secret signatures are refused without being
echoed. The identifier is a declaration for local traceability, not
authenticated identity.

Exit code `0` means `check` found an applicable operation or `apply` completed
the replacement. Exit code `2` means a deterministic rule blocked it. Exit
code `1` means a tool, input, policy, or I/O error.

## Revalidated Before Copy

Both actions use only the versioned repository policies and revalidate:

- the complete five-artifact run contract;
- the exact stage bundle and separately supplied digest;
- the captured response contract and allowed output status;
- repository `HEAD` and a clean worktree;
- every run context source against the bundle;
- an external run, bundle, and response with no contracted symbolic links;
- the target's current status;
- a non-empty byte-level change;
- an absent external receipt path.

`apply` repeats this assessment after confirmation, then compares the response
and target bytes again immediately before mutating anything. It writes the
receipt exclusively, replaces the target file on the same filesystem, validates
the resulting run, and verifies that both the receipt bytes and post-copy run
snapshot still match the confirmation-bound operation.

Research may replace only a `pending` `research.md`. Planning may replace only
an `awaiting_approval` `plan.md`. Approved or blocked targets, stale
confirmations, replayed applications, changed context, self-approved plans, and
byte-identical responses are rejected.

## Honest Boundary

The exact confirmation prevents accidental, stale, and ordinary replayed copy
operations. The external application receipt is durable local traceability for
the exact copy, but it is not signed and is not independently consumed by later
stages yet. It does not prove that a human typed the confirmation: any actor
already able to execute the command can automate both actions. The reviewer
declaration is not authenticated or signed.

The receipt is written before the artifact replacement. Handled failures remove
only the receipt created by that attempt and restore the target only while its
bytes still match the attempted replacement. This ordering fails closed for
later provenance checks, but it is not transactional crash recovery: a process
crash can still leave an invalid receipt beside an unchanged target, or a
mutated target with no usable receipt.

The tool does not:

- approve research claims or plans;
- authorize implementation, publication, Git operations, or external writes;
- run an agent or quality gate;
- copy into the Git checkout;
- provide a cross-process lock against a concurrent writer;
- authenticate or cryptographically sign audit records.

Every result retains `authorized=false`, `stage_authorized=false`, and
`publication_authorized=false`. A successful application reports only that the
exact validated response was operator-confirmed, copied into the external run,
and recorded in a bounded external receipt. Results explicitly report
`run_mutated`, `response_applied`, `copy_confirmed`, and `receipt_written`;
blocked and check-only operations report all four as `false`.

`docs/agent-guides/stage-application-validation.md` documents the independent
read-only validator for the resulting external receipt.
