# Deterministic Implementation Handoff

`build_implementation_handoff.py` prepares a bounded, reproducible package for
a later supervised implementation session. It does not invoke an agent, expose
repository source files, mutate the checkout or run, or authorize any action.

This is deliberately separate from implementation readiness. Readiness
describes declared prerequisite consistency. The handoff adds a more
conservative pilot rule: `plan.md` must be exactly `approved` for every risk
route, including low risk.

## Contents

The external JSON package contains:

- exact `task.md`, `research.md`, and approved `plan.md` content;
- issue, declared risk, base commit, and matching repository `HEAD`;
- a SHA-256 snapshot binding all five run artifacts;
- the separately carried validated plan-approval receipt SHA-256;
- a content-free manifest with status, size, and SHA-256 for all five artifacts;
- explicit false authorization declarations.

It contains no implementation prompt, repository source file, environment
variable, credential, transcript, model configuration, or adapter command.
Embedded artifact content preserves exact UTF-8 bytes, including an optional
byte-order mark accepted by the portable artifact contract.

## Build

Use an approved external run and a clean checkout at the exact base commit:

```text
python .agent/checks/build_implementation_handoff.py \
  --repo . \
  --run <external-run-directory> \
  --output <external-path>/implementation-handoff.json \
  --plan-approval-receipt <external-plan-approval-receipt.json> \
  --plan-approval-receipt-sha256 <separately-carried-sha256> \
  --format json
```

The output path and plan-approval receipt must be outside both the checkout and
run directory, and the output must not already exist. Exit code `0` means the
package was produced, `2` means a deterministic prerequisite blocked it, and
`1` means a tool, input, policy, or I/O error.

The explicit policy lives in
`.agent/policies/implementation-handoff.json`. The CLI does not accept policy
overrides.

## Preconditions

The builder requires:

- a valid external five-artifact run with no contracted symbolic links;
- an output outside both the checkout and run directory;
- implementation readiness according to the existing risk route;
- an exact `approved` plan for every risk route;
- a valid external plan-approval receipt for the exact current approved run;
- repository `HEAD` equal to the run base commit;
- a clean repository worktree;
- no high-confidence secret signature in any of the five artifacts;
- unchanged run snapshot and repository state immediately before output;
- a final package no larger than 70,000 bytes.

## Honest Boundary

The handoff records reviewed intent, exact inputs, and validated local
plan-approval receipt integrity. It is not an authorization token and cannot
prove that the plan, research, declared risk, or approval identity is correct.
Anyone able to edit the external run and matching receipts while preserving all
bound hashes remains inside the local trust boundary.

The builder detects observed state drift before writing but provides no
cross-process lock. A later consumer must independently revalidate the package
against its chosen implementation workspace.

Every package states:

```text
authorized=false
agent_invocation_authorized=false
implementation_authorized=false
repository_mutation_authorized=false
network_authorized=false
publication_authorized=false
```

`docs/agent-guides/implementation-session.md` defines the next non-authorizing
proposal layer: supervised prompt, workspace requirement, tool permissions,
budgets, and external controls. Output capture, enforced isolation, explicit
authorization, and invocation remain separate controls.
