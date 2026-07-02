# Exact Plan Approval

`approve_plan.py` governs the only current transition from
`plan.md: awaiting_approval` to `plan.md: approved`.

This is a semantic decision separate from:

- copying a structurally accepted plan into the run;
- checking whether implementation prerequisites are ready;
- authorizing or starting implementation.

Approving a plan means only that the declared local approver accepts the exact
current plan as the intended implementation path. It does not authorize an
agent, Git write, publication, or external action.

## Two-Step Procedure

Review the current external run and exact plan, then request the content-bound
confirmation:

```text
python .agent/checks/approve_plan.py check \
  --repo . \
  --run <external-run-directory> \
  --application-receipt <external-plan-application-receipt.json> \
  --application-receipt-sha256 <separately-carried-sha256> \
  --approval-receipt <external-absent-plan-approval-receipt.json>
```

`check` is read-only. A successful result reports `approvable=true` and prints
`required_confirmation`. That phrase binds:

- issue, declared task risk, and base commit;
- a deterministic SHA-256 snapshot of all five run artifacts;
- the exact current `plan.md` SHA-256;
- the separately carried applied-plan receipt SHA-256;
- the trusted plan-approval control bindings;
- the external absent path reserved for the plan-approval receipt.

After reviewing the plan, pass the phrase unchanged:

```text
python .agent/checks/approve_plan.py approve \
  --repo . \
  --run <external-run-directory> \
  --application-receipt <external-plan-application-receipt.json> \
  --application-receipt-sha256 <separately-carried-sha256> \
  --approval-receipt <same-external-absent-plan-approval-receipt.json> \
  --approver <local-approver-id> \
  --confirm "<exact-required-confirmation>"
```

The approver identifier follows the same restricted local identifier format as
stage application. High-confidence secret signatures are refused without being
echoed.

Exit code `0` means `check` found an approvable exact plan or `approve`
completed the status transition. Exit code `2` means a deterministic rule
blocked it. Exit code `1` means a tool, input, policy, or I/O error.

## Preconditions And Mutation

Both actions use only versioned repository policies and require:

- a valid external five-artifact run with no contracted symbolic links;
- an approved `task.md`;
- no blocked artifact;
- `plan.md` at exactly `awaiting_approval`;
- a valid stage-application receipt for the current applied `plan.md`;
- an external absent plan-approval receipt path outside the checkout and run;
- planning prerequisites from the declared risk route;
- completed research for medium and high risk;
- repository `HEAD` equal to the run base commit;
- a clean repository worktree.

`approve` repeats the assessment after confirmation, including applied-plan
receipt validation and trusted-control binding checks. It compares the complete
run snapshot and plan bytes again immediately before mutation, validates a
complete candidate run, writes the plan-approval receipt exclusively, then
atomically changes only the plan status line. Replays, stale confirmations,
already approved plans, missing provenance, existing receipt paths, missing
prerequisites, and dirty repositories are rejected.

The plan-approval receipt records:

- the applied-plan receipt SHA-256;
- the exact confirmation SHA-256 and approver declaration;
- issue, risk, base commit, and external run;
- exact run snapshots and plan bytes before and after approval;
- exact plan-approval controls and imported helper bytes.

After approval, the tool reports whether the declared implementation
prerequisites are ready. It always retains:

```text
authorized=false
implementation_authorized=false
publication_authorized=false
```

`implementation_ready=true` is a consistency fact, not permission to execute.

## Honest Boundary

The confirmation and durable receipt make the decision explicit and bind it to
one exact plan. They do not prove that a human typed the command. Any actor
already able to run the tool can automate both steps. The approver declaration
is not authenticated or signed, the receipt is not an authorization token, and
no cross-process lock is provided.

The tool does not prove:

- that the plan is technically correct or complete;
- that its evidence or provenance is semantically trustworthy;
- that the task risk is correctly declared;
- that the approver has organizational authority;
- that implementation should now begin.

Stronger identity or signed approval remains a future design decision rather
than a property claimed by this local pilot.

After approval, `docs/agent-guides/plan-approval-validation.md` describes the
independent read-only check for the durable receipt. The implementation
handoff consumes that validator as a prerequisite while still producing only a
non-authorizing package. Producing a handoff package still does not start or
authorize the session.
