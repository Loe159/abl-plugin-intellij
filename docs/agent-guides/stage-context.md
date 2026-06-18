# Deterministic Read-Only Stage Context

`build_stage_context.py` prepares the exact bounded input that a future
read-only adapter may receive. It does not execute an agent.

The builder emits deterministic JSON containing:

- one validated static prompt;
- only the workflow artifacts allowed for that stage;
- issue, risk, base commit, sizes, and SHA-256 digests;
- `mode: read-only` and `authorized: false`.

Research receives only `task.md`. Planning receives only `task.md` and
`research.md`. Raw issue comments, transcripts, unrelated workflow artifacts,
repository files, environment variables, and credentials are not copied into
the bundle.

## Preconditions

The explicit policy in `.agent/policies/stage-context.json` requires:

- valid prompts and portable artifacts;
- a ready declared stage;
- valid task-approval provenance for `research`;
- valid research-application receipt provenance for `plan`;
- an external run-artifact directory;
- an external non-existing output path;
- repository `HEAD` equal to the artifact base commit;
- a clean repository worktree;
- no high-confidence secret signature in bundled content;
- a final bundle no larger than 50,000 bytes.

Build a context outside the checkout:

```text
python .agent/checks/build_stage_context.py \
  --repo . \
  --run <external-run-directory> \
  --stage research \
  --approval-receipt <external-task-approval-receipt.json> \
  --approval-receipt-sha256 <separately-carried-sha256> \
  --output <external-path>/research-context.json \
  --format json
```

For planning, carry the stage-application receipt SHA-256 from the separate
operator-confirmed research application:

```text
python .agent/checks/build_stage_context.py \
  --repo . \
  --run <external-run-directory> \
  --stage plan \
  --application-receipt <external-stage-application-receipt.json> \
  --application-receipt-sha256 <separately-carried-sha256> \
  --output <external-path>/plan-context.json \
  --format json
```

Exit code `0` means a bundle was produced, `2` means a declared precondition
blocked production, and `1` means a tool, input, or policy error. The builder
never overwrites an existing output.

The version-3 bundle carries a `provenance` object. Research records the
validated task-approval receipt SHA-256. Planning records the validated
stage-application receipt SHA-256 for the applied `research.md`. The builder
rechecks the relevant provenance immediately before writing the bundle. This
binds the later bundle digest to the provenance digest without embedding the
receipt or declaring authorization.

## Deliberate Limits

The bundle is structured input, not a security sandbox. It contains untrusted
task and research text as data and does not prove that a model will ignore
embedded instructions. It does not include repository source evidence; a future
adapter may expose the verified clean checkout read-only. It does not invoke a
model, enforce network isolation, validate model output, or authorize a stage.

Validate a captured response with `docs/agent-guides/stage-output.md`. Carry the
builder-reported SHA-256 separately; do not derive the expected digest from the
bundle being validated.

For a provider-neutral manual rehearsal that composes context building and
output validation without executing an agent, use
`docs/agent-guides/manual-read-only-adapter.md`.
