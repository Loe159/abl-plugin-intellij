# Implementation Session Start Authorization Validation

`validate_implementation_session_start_authorization.py` independently
validates one exact session-start authorization receipt. It is read-only and
does not invoke an agent, select a runner, mutate a workspace, or consume the
receipt.

## Run

```text
python .agent/checks/validate_implementation_session_start_authorization.py \
  --repo <clean-source-checkout> \
  --proposal <external-path>/implementation-session-proposal.json \
  --proposal-sha256 <expected-proposal-sha256> \
  --workspace <prepared-external-worktree> \
  --worktree-receipt <external-path>/disposable-worktree-receipt.json \
  --worktree-receipt-sha256 <expected-worktree-receipt-sha256> \
  --approval-receipt <external-session-approval-receipt.json> \
  --approval-receipt-sha256 <expected-approval-receipt-sha256> \
  --preflight <external-path>/implementation-invocation-preflight.json \
  --preflight-sha256 <expected-preflight-sha256> \
  --authorization-receipt <external-start-authorization.json> \
  --authorization-receipt-sha256 <expected-authorization-receipt-sha256> \
  --format json
```

Exit code `0` means the exact receipt currently validates, `2` means a
deterministic condition rejected it, and `1` means an input, policy, tool, or
I/O error.

## Validation Scope

The validator:

- checks the separately carried receipt SHA-256 before trusting its content;
- rejects symbolic links, internal receipt paths, extra fields, and
  authorization overclaims;
- reruns session-start readiness and therefore runner-control checks;
- recalculates candidate-runner, readiness, confirmation, and policy digests;
- requires the clean source checkout and exact base commit to remain current;
- detects state or validator-binding drift before returning `valid=true`.

## Honest Boundary

`valid=true` means the receipt still matches current local evidence. It does
not authenticate the authorizer, prevent replay, select or invoke a runner,
enforce a sandbox, grant network access, authorize publication, or prove that a
future process will obey the receipt.
