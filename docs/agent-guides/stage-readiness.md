# Manual Stage Readiness

`check_stage_readiness.py` checks whether the declared statuses in one portable
artifact run satisfy the prerequisites for a requested manual stage. It is a
read-only consistency gate, not an orchestrator.

The policy is explicit in `.agent/policies/stage-readiness.json`. Repository
templates deliberately start with `task.md` at `awaiting_approval` and
`research.md` at `pending`; copying and filling templates cannot make a stage
ready without an explicit status change.

## Current Stages

| Stage | Low risk | Medium and high risk |
| --- | --- | --- |
| `research` | approved task | approved task |
| `plan` | approved task | approved task and completed research |
| `implement` | approved task and present plan | approved task, completed research, approved plan |
| `verify` | implementation done | implementation done; research done; plan approved |
| `complete` | verification passed | verification passed; research done; plan approved |

For low-risk work, research may remain `pending` or be marked `not_required`.
A `blocked` status on any artifact makes every readiness check fail. Every
result always reports `authorized=false`.

## Run

```text
python .agent/checks/check_stage_readiness.py \
  --run <external-run-directory> \
  --stage implement \
  --format json
```

Exit code `0` means declared prerequisites are ready, `2` means not ready, and
`1` means a tool, input, policy, or unknown-stage error.

## Deliberate Limits

Readiness does not prove that an approval was issued by a human, that artifact
claims are true, or that stages occurred in chronological order. The checker
does not edit statuses, run an agent, compare task risk with a candidate patch,
execute quality gates, authorize publication, or communicate with GitHub.
Those remain separate controls.

Copying a validated plan into a run does not approve it. The operator-confirmed
copy step is documented separately in `docs/agent-guides/stage-application.md`.
The exact local plan-status transition is documented in
`docs/agent-guides/plan-approval.md`. Even after approval, readiness remains a
consistency result rather than authorization to execute.

The later deterministic implementation handoff is documented in
`docs/agent-guides/implementation-handoff.md`. It adds a conservative approved
plan requirement for every risk route but still does not authorize execution.

The initializer documented in
`docs/agent-guides/portable-run-initialization.md` intentionally creates
`task.md` at `awaiting_approval`, so its fresh run is structurally valid but
not ready for `research`. The exact local transition is documented in
`docs/agent-guides/task-approval.md`; it can make the declared prerequisites
ready but does not authorize starting the stage.

Task approval emits a durable external receipt with an independent read-only
validator documented in `docs/agent-guides/task-approval-validation.md`.
This generic readiness checker intentionally remains the status-only engine
used by internal consistency checks. Therefore its `ready=true` still cannot
distinguish controlled approval from a manually edited approved status.

Before preparing a real research context, use the provenance-aware composite
gate documented in `docs/agent-guides/research-readiness.md`. Later stages
remain status-only for now.
