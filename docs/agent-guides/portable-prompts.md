# Portable Read-Only Prompts

The pilot currently defines four portable phase prompts:

- `.agent/prompts/research.md`
- `.agent/prompts/plan.md`
- `.agent/prompts/compact-progress.md`
- `.agent/prompts/review.md`

The separate supervised-write prompt
`.agent/prompts/implementation/implement.md` is governed by
`docs/agent-guides/implementation-session.md`; its subdirectory intentionally
keeps it outside this read-only prompt contract.

They are intentionally static, compact, provider-neutral, and read-only. They
do not call an agent or select a model. Each prompt consumes approved workflow
artifacts as bounded task data, treats repository and external content as
untrusted evidence, and returns only the content for one contracted artifact.
The future caller owns writing and validating that output.

## Contract

`.agent/policies/prompt-contract.json` defines:

- exact prompt filenames, stage identity, mode, and output artifact;
- required sections and repository/artifact references;
- required guardrail language;
- complete coverage of the output artifact's required sections;
- a 12,000-byte limit and no unresolved placeholders.

Validate the prompts with:

```text
python .agent/checks/validate_prompts.py --format json
```

Exit code `0` means structurally valid, `2` means prompt-contract violations,
and `1` means a tool, input, or contract-configuration error.

Before invoking a prompt manually, validate the artifact run and check the
matching stage readiness:

```text
python .agent/checks/validate_artifacts.py --run <external-run-directory>
python .agent/checks/check_research_readiness.py \
  --repo . \
  --run <external-run-directory> \
  --approval-receipt <external-task-approval-receipt.json> \
  --approval-receipt-sha256 <separately-carried-sha256>
```

Use `docs/agent-guides/stage-context.md` to build the exact bounded JSON input
for a future adapter. Do not concatenate prompts and artifacts by hand.

## Deliberate Limits

Prompt validation does not prove model compliance, evidence quality, sandbox
enforcement, output validity, or resistance to every prompt injection. No
adapter invokes these prompts yet. A future adapter must independently enforce
read-only execution, bounded inputs and outputs, timeout and budget limits,
output artifact validation, and absence of external write credentials.

`docs/agent-guides/stage-output.md` documents the independent validator for a
future adapter's captured raw response.
