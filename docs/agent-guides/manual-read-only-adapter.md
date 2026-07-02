# Manual Read-Only Adapter

`manual_read_only.py` is a provider-neutral rehearsal adapter for the existing
read-only stage contracts. It composes deterministic checks into one small
interface but deliberately does not execute an agent.

It supports only two actions:

- `prepare` validates readiness and creates one bounded external context bundle;
- `validate` validates one externally captured raw response against that exact
  bundle.

Both actions emit a JSON envelope with:

```text
adapter=manual-read-only
mode=read-only
agent_invoked=false
run_mutated=false
response_applied=false
authorized=false
```

These fields describe this adapter's deliberately limited operation. They do
not certify the behavior of a model or manual tool used between the two
actions.

## Manual Procedure

Start from a clean checkout and a valid ready run directory outside it:

```text
python .agent/adapters/manual_read_only.py prepare \
  --repo . \
  --run <external-run-directory> \
  --stage research \
  --approval-receipt <external-task-approval-receipt.json> \
  --approval-receipt-sha256 <separately-carried-sha256> \
  --bundle <external-path>/research-context.json
```

`prepare` delegates to the deterministic stage-context builder. On success, its
JSON result contains the bundle SHA-256. Carry that digest separately through a
trusted operator channel. Do not treat a digest later supplied by the same
untrusted producer as the bundle as a trust anchor.

Research preparation also requires the separately carried task-approval
receipt SHA-256 and validates its provenance before producing the bundle.
Planning requires the separately carried stage-application receipt SHA-256 for
the applied research. `compact-progress` and `review` use local artifact
contract provenance only; they still require a clean checkout, a valid external
run, and a ready declared stage:

```text
python .agent/adapters/manual_read_only.py prepare \
  --repo . \
  --run <external-run-directory> \
  --stage plan \
  --application-receipt <external-stage-application-receipt.json> \
  --application-receipt-sha256 <separately-carried-sha256> \
  --bundle <external-path>/plan-context.json
```

The human operator may then inspect the bundle and use a separately chosen
read-only model or tool to produce one raw response outside the checkout. This
manual action is outside the adapter's guarantees.

Validate the captured response:

```text
python .agent/adapters/manual_read_only.py validate \
  --repo . \
  --bundle <external-path>/research-context.json \
  --bundle-sha256 <digest-reported-by-prepare> \
  --response <external-path>/captured-response.md
```

Exit code `0` means bundle production or structural response acceptance,
depending on the action. Exit code `2` means a deterministic precondition or
validation rule blocked the operation. Exit code `1` means a tool, input, or
policy error.

## Contract And Limits

`.agent/policies/manual-read-only-adapter.json` explicitly limits the adapter to
the contracted read-only stages: `research`, `plan`, `compact-progress`, and
`review`. Its safety flags must all remain `false`; policy drift toward agent
execution, run mutation, response application, or authorization is rejected.
The command-line interface does not accept alternate policy or prompt paths; it
always composes the versioned repository contracts.

The adapter does not:

- invoke Codex or any other provider;
- enforce a provider sandbox, network isolation, timeout, or token budget;
- save a trusted receipt or metrics record;
- copy an accepted response into the run;
- approve a plan or advance workflow state;
- support implementation;
- prove that research claims, plans, compactions, or reviews are correct.

After manual review, `docs/agent-guides/stage-application.md` documents the
separate operator-confirmed tool that may copy one accepted response into the
external run. The adapter itself remains read-only.
