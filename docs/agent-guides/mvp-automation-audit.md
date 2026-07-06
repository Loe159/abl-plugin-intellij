# MVP Automation Audit

Audit date: 2026-07-06.

This document is the short operational audit for restarting the local agentic
workflow from a clean baseline. It deliberately avoids repeating the historical
handoff narrative. Detailed per-stage contracts remain in the existing
`docs/agent-guides/*.md` files.

## Why This Workflow Exists

Running Codex directly is useful for a single supervised edit, but it gives the
agent broad context, mutation ability, and judgement responsibility in one
session. The local workflow splits those concerns:

- untrusted issue text is converted into a bounded human-normalized task;
- read-only research and planning are separated from implementation;
- approvals are exact local transitions, not implied by model confidence;
- implementation happens in a disposable worktree, not directly on `main`;
- deterministic scripts generate the patch, enforce policy, run checks, and
  retain receipts;
- publication remains a separate explicit human request.

The benefit is not that the workflow is fully autonomous. The benefit is that
each transition leaves current-state evidence that can be independently
rechecked before the next step.

## Current Implemented Surface

The checkout already contains the MVP building blocks:

- issue ingestion:
  `.agent/checks/list_github_approved_issues.py`,
  `.agent/checks/fetch_github_issue_snapshot.py`,
  `.agent/checks/prepare_github_task.py`, and
  `.agent/scripts/prepare-task.sh`;
- portable run artifacts:
  `.agent/templates/` plus `.agent/checks/initialize_portable_run.py` and
  `.agent/checks/validate_artifacts.py`;
- read-only stages:
  `.agent/adapters/manual_read_only.py`, `.agent/adapters/local_read_only.py`,
  `.agent/checks/build_stage_context.py`, and
  `.agent/checks/validate_stage_output.py`;
- HITL transitions:
  task approval, stage application, plan approval, implementation-session
  approval, and session-start authorization scripts;
- implementation runner:
  `.agent/checks/run_supervised_implementation.py`,
  `.agent/checks/build_supervised_runner_invocation.py`, and provider wrapper
  entrypoints under `.agent/adapters/`;
- deterministic validation:
  complete patch generation, diff policy, risk classification, implementation
  result validation, patch receipt validation, quality gate, final runner
  receipt validation, and optional cleanup validation;
- explicit-only publication:
  `.agent/checks/publish_draft_pr.py` and
  `.agent/scripts/publish-draft-pr.sh`.

`check_workflow_status.py` still reports `pilot_ready=false`. For the current
MVP direction, the important interpretation is: most local mechanics exist, but
the checked-in ledger still requires the historical golden set and runner
hardening evidence that are not prerequisites for a first supervised local
exercise.

## Documentation Cleanup

The duplicated root handoff document was removed after consolidation. The
maintained documentation now has three roles:

- `AGENTS.md`: concise mandatory repository and workflow rules for agents;
- `.agents/skills/agentic-workflow-pilot/README.md`: human operator overview;
- `docs/agent-guides/*.md`: exact per-stage contracts and validators.

Large historical files remain only where they still carry current evidence:

- `docs/agent-guides/repository-audit.md` is the chronological repository
  evidence log;
- `docs/agent-guides/handoff-implementation-audit.md` is the reconciliation log
  from the original handoff to the current checkout.

These two files should not be used as the normal operator path. The normal
operator path should point here plus `supervised-runner-workflow.md`.

## Memory Model

The original handoff mentioned a memory-bank idea, but the implemented system
does not currently have a three-level persistent memory store or a backlog
directory per issue.

What exists today:

- one external portable run directory per issue/session;
- durable artifacts: `task.md`, `research.md`, `plan.md`, `progress.md`,
  `verification.md`, and `review.md`;
- `progress.md` plus `.agent/prompts/compact-progress.md` for session
  compaction;
- metrics records produced after a runner receipt.

What does not exist yet:

- a repo-standard `runs/ISSUE-<n>/` or `.agent/work/ISSUE-<n>/` layout;
- persistent project memory shared across issues;
- a backlog filesystem separate from GitHub labels;
- automatic compaction between every phase.

For the MVP, keep the issue-scoped run directory external to the checkout and
standardize its naming before adding a global memory layer.

## Recommended MVP Path

1. Add one non-authorizing orchestrator command, for example
   `.agent/checks/run_issue_workflow.py`, with resumable subcommands rather than
   one opaque magic command.
2. Start with issue preparation only: `prepare --issue <n>` should fetch,
   check, approve-init after exact confirmation, initialize the external run,
   and show the next required human action.
3. Add `research`, `plan`, and `approve-plan` subcommands that call the existing
   stage-context, output-validation, stage-application, and plan-approval tools.
4. Add `prepare-implementation` to build handoff, session proposal, disposable
   worktree, preflight, and exact start authorization package.
5. Add `run-implementation` as a thin wrapper around
   `build_supervised_runner_invocation.py` and
   `run_supervised_implementation.py`.
6. Add `summarize` to print the current run state, next command, required human
   confirmation phrase, and produced receipts.
7. Move the golden set out of the MVP readiness requirement or introduce an
   `--mvp-without-golden-set` status profile that still reports the missing
   evidence honestly.

The orchestrator should call existing validators instead of reimplementing
their logic. It should never hide exact confirmations, never auto-approve a
plan, and never publish without an explicit publication command.

## Codebase Audit Notes

The plugin code remains outside this cleanup. The verified architecture still
matches `docs/agent-guides/repository-audit.md`: Kotlin plugin code lives under
`src/main/kotlin/com/ablls/plugin/`, parser construction stays behind
`core/AblParserFacade.kt` and `core/AblParseResult.kt`, and RSSW Proparse 3.7.2
is the ABL source of truth.

Before changing ABL parsing, completion, inspections, navigation, schema
handling, or semantic analysis, use the local `proparse-research` skill and
record RSSW evidence. This audit does not approve any plugin behavior change.

## Deliberate Non-Goals For This MVP

- no historical golden set adoption;
- no fully autonomous GitHub issue loop;
- no automatic PR publication;
- no `.github/**` or Gradle changes;
- no new guardrail cycle unless a concrete orchestrator integration exposes a
  real gap;
- no claim that network isolation, provider credential descendant isolation,
  or crash-atomic launch coupling are proven.

