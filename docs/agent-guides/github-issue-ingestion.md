# GitHub Issue Snapshot Ingestion

`approve_github_issue_snapshot.py` turns one bounded external issue snapshot and
one human-written mini-specification into the exact normalized input accepted
by `initialize_portable_run.py`.

It is deliberately a local approval boundary, not a GitHub client. Network
retrieval stays outside this tool so untrusted issue content cannot choose
commands, files, tools, or permissions.

## External Package

The exact JSON package contains:

- repository, capture timestamp, issue number, canonical URL, open state,
  title, body, author, and sorted labels;
- no comments or arbitrary extra fields;
- one human-written risk and base commit;
- the five normalized task sections: goal, expected behavior, acceptance
  criteria, constraints, and out of scope.

The package must target `Loe159/abl-plugin-intellij`, carry
`agent:approved`, and carry no other `agent:*` workflow status label. This is
only a declared snapshot condition until a trusted GitHub retrieval boundary
exists.

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

SHA-256 is not a signature. The tool does not prove that GitHub returned the
snapshot, that the label was added by an authorized human, that the issue is
still open, or that the mini-specification is correct. It does not read issue
comments, call GitHub, initialize a run, start a stage, invoke an agent, modify
the checkout, or publish anything.

A host crash after receipt creation but before normalized-input creation can
leave an invalid receipt. Consumers must run `validate` and must not infer
approval from file existence alone.
