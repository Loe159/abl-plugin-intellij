# Deterministic Patch Risk Classification

`classify_patch_risk.py` assigns a supervision route to an already-produced
patch. It uses the same diff policy facts and violations as the patch validator,
plus repository-specific path and size rules from
`.agent/policies/risk-rules.json`.

It does not authorize a patch. A policy-blocked patch is always classified
`high`, and classification can never turn `policy_allowed` from `false` to
`true`.

## Routes

| Risk | Route | Meaning during the pilot |
| --- | --- | --- |
| `low` | A | Small documentation or focused test change; implementation review remains required. |
| `medium` | B | Standard application change; plan and implementation reviews are required, research review is recommended. |
| `high` | C | Policy violation or sensitive internals; research, plan, intermediate implementation, and final implementation reviews are required. |

## Current Deterministic Rules

Risk is the maximum of all matching signals:

- any diff-policy violation makes risk `high`;
- parser, semantic-boundary, and debugger-internal paths make risk `high`;
- any `src/main/**` application change makes risk at least `medium`;
- four or more files make risk at least `medium`;
- 51 or more added/removed lines make risk at least `medium`;
- otherwise risk is `low`.

The high-risk paths are verified repository paths, not generic keywords inferred
from issue text. Task-text and threading-keyword classification remain deferred
until normalized `task.md` artifacts exist.

JSON is used instead of the handoff's suggested YAML so the first classifier
remains dependency-free and uses the same standard-library validation approach
as the existing guardrails.

## Run

```text
python .agent/checks/classify_patch_risk.py \
  --patch <external-path>/patch.diff \
  --repo . \
  --base <base-commit> \
  --format json
```

Use reinforced `--repo` and `--base` mode for implementation candidates. Exit
code `0` means classification completed, including for `high` or policy-blocked
patches. Exit code `1` means classifier input or configuration error. Policy
enforcement remains the responsibility of `diff_policy.py`.

For a portable task route declared before patch generation:

```text
python .agent/checks/classify_task_route.py \
  --run <external-run-directory> \
  --format json

.agent/scripts/classify-task.sh <external-run-directory>
```

This validates the portable run artifacts, reads only `task.md` frontmatter,
maps `risk` to route `A`, `B`, or `C`, and reports the current task status.
It does not prove that the declared risk is correct, approve the task, select a
runner, authorize implementation, or inspect issue text. `task_approved=true`
only reports that `task.md` already has `status: approved`.

## Deliberate Limits

The classifier does not inspect issue text, infer public API changes, detect
threading semantics, or estimate business impact. It does not replace human
judgment, and its output may only be increased by later review, never used to
justify lowering required supervision.
