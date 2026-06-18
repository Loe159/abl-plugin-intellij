# Portable Run Initialization

`initialize_portable_run.py` creates one external five-artifact workflow run
from an external task specification that a human has already normalized. It
does not fetch or sanitize a GitHub issue, authenticate an approver, approve
the task, start research, or invoke an agent.

## Normalized Input

The input is bounded JSON with exactly this shape:

```json
{
  "input_version": 1,
  "purpose": "portable_run_normalized_task_input",
  "mode": "normalized-task-only",
  "issue": 123,
  "risk": "medium",
  "base_commit": "0123456789abcdef0123456789abcdef01234567",
  "source": {
    "kind": "human_normalized_input",
    "reference": "local:issue-123"
  },
  "task": {
    "goal": "One concrete bounded goal.",
    "expected_behavior": "The observable expected behavior.",
    "acceptance_criteria": "- One measurable criterion.",
    "constraints": "- One verified constraint.",
    "out_of_scope": "- One explicit exclusion."
  }
}
```

The input must not be raw issue content copied blindly. Its source reference is
traceability data only; it does not authenticate the source, reviewer, or
approval. Task text remains untrusted data when later exposed to a model.

## Run

Use a clean checkout at the exact declared base commit. Input, run, and receipt
must be external to the checkout, and output paths must not exist:

```text
python .agent/checks/initialize_portable_run.py \
  --repo <clean-checkout> \
  --input <external-normalized-task.json> \
  --run <external-absent-run-directory> \
  --receipt <external-absent-initialization-receipt.json> \
  --format json
```

The CLI accepts no policy override. Its exact policy is
`.agent/policies/portable-run-initialization.json`.

Exit code `0` means the run and receipt were created, `2` means a deterministic
precondition rejected initialization without writing outputs, and `1` means an
input, policy, Git, validation, I/O, or rollback error.

Validate the resulting receipt independently before consuming it:

```text
python .agent/checks/validate_portable_run_initialization.py \
  --repo <clean-checkout> \
  --run <external-run-directory> \
  --receipt <external-initialization-receipt.json> \
  --receipt-sha256 <separately-carried-receipt-sha256> \
  --format json
```

The independent validation contract is documented in
`docs/agent-guides/portable-run-initialization-validation.md`.

## Initialization Contract

The command:

- requires an exact bounded input schema with non-empty task sections;
- rejects high-confidence secret signatures without echoing matching values;
- requires a clean checkout whose `HEAD` equals the exact base commit;
- creates exactly the five contracted Markdown artifacts from trusted
  repository templates;
- validates the complete resulting artifact contract;
- verifies fixed initial statuses and requires `research` readiness to remain
  false;
- creates the final run path exclusively instead of replacing a path that
  appeared concurrently;
- writes an external receipt binding the input digest, run manifest, exact
  templates, policies, initializer, and imported helper bytes;
- rechecks input, run, receipt, and repository state before success;
- removes only the run and receipt it created after a post-creation failure.

The initial task is always `awaiting_approval`. Later-stage sections contain an
explicit statement that their workflow stage has not run. The plan template's
existing initial status remains `awaiting_approval`, but its content does not
claim that planning occurred.

## Honest Boundary

Every result and receipt retains false authorization fields, including:

```text
authorized=false
task_approval_authenticated=false
stage_start_authorized=false
agent_invocation_authorized=false
```

Initialization is reproducible scaffolding, not issue normalization or
approval. It does not prove that task claims are true, that risk is correctly
classified, that a human reviewed the task, or that the source reference maps
to a real approved issue. SHA-256 binds exact bytes but is not a signature.

The initialized run deliberately fails the `research` readiness check until a
separate, explicit task-approval control is completed. Use
`docs/agent-guides/task-approval.md`; do not edit the task status by hand and
treat that as authenticated approval.
