# Portable Agent Artifact Contract

The pilot uses six small Markdown artifacts to carry verified context between
manual phases without depending on one model, prompt, or orchestration tool:

- `task.md` records the approved problem boundary and initial risk;
- `research.md` records evidence, unknowns, and rejected approaches;
- `plan.md` records the reviewed implementation path and stop conditions;
- `progress.md` records durable implementation state and decisions;
- `verification.md` records candidate checks, policy results, and residual risk;
- `review.md` records consultative read-only review findings.

Templates live in `.agent/templates/`. The deterministic contract lives in
`.agent/policies/artifact-contract.json`.
Templates do not assert approval or completed research by default.

## Format

Each artifact starts with deliberately limited scalar frontmatter:

```text
---
artifact_version: 1
artifact: task
issue: 123
base_commit: 0123456789abcdef0123456789abcdef01234567
status: approved
risk: low
---
```

This is not general YAML. Each frontmatter line is one non-empty `key: value`
scalar so the validator remains dependency-free and predictable. UTF-8 with or
without a byte-order mark is accepted for portability across common Windows
tools.

A filled run must contain exactly the six contracted top-level Markdown files.
They must share one positive numeric issue ID and one full lowercase 40-character
base commit. Required sections must exist and be non-empty, placeholders must be
resolved, statuses must be allowed, and each artifact must remain at or below
20,000 bytes. Additional top-level Markdown files are rejected.

## Validate

Validate the repository templates:

```text
python .agent/checks/validate_artifacts.py --templates .agent/templates
```

Validate a filled run stored outside the checkout:

```text
python .agent/checks/validate_artifacts.py \
  --run <external-run-directory> \
  --format json
```

Exit code `0` means structurally valid, `2` means contract violations, and `1`
means a tool, input, or contract-configuration error.

## Deliberate Limits

Structural validity does not prove that claims are true, evidence is sufficient,
an approval occurred, or a phase transition is authorized. The validator does
not compare `task.md` risk with the patch-risk classifier, inspect nested or
non-Markdown files, enforce status transitions, or execute implementation
checks. Those controls remain explicit later increments rather than hidden
assumptions in this first portable artifact contract.

Use `docs/agent-guides/stage-readiness.md` for the separate declared-status
readiness check.
Use `docs/agent-guides/stage-application.md` for the only current
operator-confirmed mutation of a filled external run.
Use `docs/agent-guides/plan-approval.md` for the separate exact-plan transition
from `awaiting_approval` to `approved`.
Use `docs/agent-guides/implementation-handoff.md` to package an approved plan
and its bounded context without authorizing or starting implementation.
Use `docs/agent-guides/portable-run-initialization.md` to create one complete
external run from an already normalized local task without approving it.
