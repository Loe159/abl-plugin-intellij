# GitHub Issue Snapshot Ingestion

`approve_github_issue_snapshot.py` turns one bounded external issue snapshot and
one human-written mini-specification into the exact normalized input accepted
by `initialize_portable_run.py`.

It is deliberately a local approval boundary, not a GitHub client. A separate
read-only collector, `fetch_github_issue_snapshot.py`, may use `gh issue view`
to build the external package, but approval remains a separate exact local
step. Untrusted issue content still cannot choose commands, files, tools, or
permissions.

## Optional Read-Only Fetch

To inspect the currently approved queue without selecting work:

```text
.agent/scripts/prepare-task.sh queue-list \
  --repo <local-checkout> \
  --queue <external-absent-queue.json> \
  --format json
```

This calls `gh issue list --state open --label agent:approved` with a bounded
JSON field list that excludes issue bodies and comments. The queue snapshot
sorts eligible issues by number, rejects entries carrying another `agent:*`
workflow status label, and records `issue_selected=false`.
When `--queue` is provided, the output path must be outside the Git checkout,
must not already exist, must have an existing parent directory, and must not be
a symbolic link. Producing the queue snapshot never selects an issue or
approves a task.

When a reviewer has already written the normalization file, create the external
package with:

```text
python .agent/checks/fetch_github_issue_snapshot.py \
  --repo <local-checkout> \
  --issue <number> \
  --normalization <external-human-normalization.json> \
  --package <external-absent-package.json> \
  --format json
```

The collector calls exactly `gh issue view <number> --repo
Loe159/abl-plugin-intellij --json author,body,labels,number,state,title,url`.
It requires an open issue carrying `agent:approved` and no other `agent:*`
workflow status label. It does not fetch comments, initialize a run, approve
the task, invoke an agent, mutate the repository, write to GitHub, or authorize
publication.

Its output package is still untrusted current-state evidence. Consumers must
continue through the approval and validation commands below.

`prepare-task.sh` wraps the same boundary in two explicit phases:

```text
.agent/scripts/prepare-task.sh fetch-check \
  --repo <clean-checkout> \
  --issue <number> \
  --normalization <external-human-normalization.json> \
  --package <external-absent-package.json> \
  --normalized-input <external-absent-normalized-input.json> \
  --approval-receipt <external-absent-approval-receipt.json> \
  --approver <local-reviewer-id> \
  --format json
```

After reviewing `required_confirmation`, continue with:

```text
.agent/scripts/prepare-task.sh approve-init \
  --repo <same-clean-checkout> \
  --package <same-external-package.json> \
  --normalized-input <same-external-normalized-input.json> \
  --approval-receipt <same-external-approval-receipt.json> \
  --approver <same-local-reviewer-id> \
  --confirm "<exact-required-confirmation>" \
  --run <external-absent-run-directory> \
  --initialization-receipt <external-absent-initialization-receipt.json> \
  --format json
```

This convenience wrapper still does not approve the initialized task. Use
`approve_task.py` as a separate local decision, or delegate to it through:

```text
.agent/scripts/prepare-task.sh task-check \
  --repo <same-clean-checkout> \
  --run <external-run-directory> \
  --receipt <external-initialization-receipt.json> \
  --receipt-sha256 <separately-carried-initialization-sha256> \
  --approval-receipt <external-absent-task-approval-receipt.json> \
  --approver <local-approver-id>
```

After reviewing the exact task and `required_confirmation`:

```text
.agent/scripts/prepare-task.sh task-approve \
  --repo <same-clean-checkout> \
  --run <same-external-run-directory> \
  --receipt <same-external-initialization-receipt.json> \
  --receipt-sha256 <same-separately-carried-initialization-sha256> \
  --approval-receipt <same-external-task-approval-receipt.json> \
  --approver <same-local-approver-id> \
  --confirm "<exact-required-confirmation>"
```

These wrapper commands do not authenticate the approver, start research, invoke
an agent, or authorize repository mutation beyond the exact local task-status
transition implemented by `approve_task.py`.

## External Package

The exact JSON package contains:

- repository, capture timestamp, issue number, canonical URL, open state,
  title, body, author, and sorted labels;
- no comments or arbitrary extra fields;
- one human-written risk and base commit;
- the five normalized task sections: goal, expected behavior, acceptance
  criteria, constraints, and out of scope.

The package must target `Loe159/abl-plugin-intellij`, carry
`agent:approved`, and carry no other `agent:*` workflow status label. If the
package was produced by `fetch_github_issue_snapshot.py`, that label was
observed through the local `gh` command, but it still does not authenticate who
set the label or authorize any workflow stage.

The raw issue body is secret-scanned and bounded, but it is never copied into
the normalized task input. Text filtering is not treated as a prompt-injection
security boundary. The human normalization is the only task content forwarded.

## Check And Approve

First calculate the exact confirmation without writing:

```text
python .agent/checks/approve_github_issue_snapshot.py check \
  --repo <clean-checkout> \
  --package <external-package.json> \
  --normalized-input <external-absent-normalized-input.json> \
  --approval-receipt <external-absent-approval-receipt.json> \
  --approver <local-reviewer-id> \
  --format json
```

Review the package, mini-specification, output paths, and
`required_confirmation`, then pass the phrase unchanged:

```text
python .agent/checks/approve_github_issue_snapshot.py approve \
  --repo <same-clean-checkout> \
  --package <same-external-package.json> \
  --normalized-input <same-external-absent-normalized-input.json> \
  --approval-receipt <same-external-absent-approval-receipt.json> \
  --approver <same-local-reviewer-id> \
  --confirm "<exact-required-confirmation>" \
  --format json
```

The confirmation binds the reviewer declaration, repository, issue, base
commit, package digest, normalized-input digest, trusted control digest, and
both output paths. Approval repeats the assessment, writes the receipt
exclusively, then writes the normalized input exclusively.

## Validate

Carry the reported approval-receipt SHA-256 separately:

```text
python .agent/checks/approve_github_issue_snapshot.py validate \
  --repo <same-clean-checkout> \
  --package <same-external-package.json> \
  --normalized-input <external-normalized-input.json> \
  --approval-receipt <external-approval-receipt.json> \
  --approval-receipt-sha256 <separately-carried-sha256> \
  --format json
```

Validation recomputes the normalized input, confirmation, and trusted bindings
from the current exact package and checkout.

## Boundary

Approval means only that the declared local reviewer accepted the exact
snapshot and manual normalization. Even `valid=true` retains:

```text
source_state_authenticated=false
github_label_independently_verified=false
approver_authenticated=false
agent_invocation_authorized=false
repository_mutation_authorized=false
publication_authorized=false
```

SHA-256 is not a signature. Approval does not prove that the label was added by
an authorized human, that the issue is still open after approval, or that the
mini-specification is correct. This approval tool does not read issue comments,
call GitHub, initialize a run, start a stage, invoke an agent, modify the
checkout, or publish anything.

A host crash after receipt creation but before normalized-input creation can
leave an invalid receipt. Consumers must run `validate` and must not infer
approval from file existence alone.
