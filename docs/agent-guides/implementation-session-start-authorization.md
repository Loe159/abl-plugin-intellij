# Implementation Session Start Authorization

`authorize_implementation_session_start.py` records explicit local consent for
one exact implementation session-start boundary. It does not invoke an agent,
start a process, mutate the workspace, enable network access, or authorize
publication.

The gate is deliberately later than proposal approval. It requires the exact
proposal, prepared worktree receipt, proposal-approval receipt, invocation
preflight, selectable runner candidate, and current session-start readiness to
remain coherent.

## Two-Step Procedure

First request the exact confirmation:

```text
python .agent/checks/authorize_implementation_session_start.py check \
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
  --authorization-receipt <external-absent-start-authorization.json> \
  --format json
```

If `authorizable=true`, review every bound input and repeat the returned phrase
unchanged:

```text
python .agent/checks/authorize_implementation_session_start.py authorize \
  <same-inputs> \
  --authorizer <local-authorizer-declaration> \
  --confirm "<exact-required-confirmation>" \
  --format json
```

The receipt path must be absent, outside both the source checkout and prepared
workspace, and written exclusively.

## Receipt Scope

The receipt binds:

- issue, risk, base commit, and exact prepared workspace path;
- proposal, worktree, proposal-approval, and preflight SHA-256 values;
- the fixed candidate runner declaration;
- the complete current session-start readiness result;
- trusted authorization-policy bindings;
- the exact confirmation and local authorizer declaration.

It records `session_start_authorized=true`, but retains:

```text
authorized=false
agent_invocation_authorized=false
implementation_authorized=false
repository_mutation_authorized=false
network_authorized=false
publication_authorized=false
runner_selected=false
authorizer_authenticated=false
replay_prevention_enforced=false
```

## Honest Boundary

This is an exact consent receipt, not an execution capability. The local
authorizer declaration is not authenticated or cryptographically signed.
The separate local consumption boundary documented in
`docs/agent-guides/implementation-session-start-consumption.md` can create one
exclusive adjacent marker and reject ordinary local replay. That marker is not
tamper resistant or a cross-host replay registry, and it does not invoke an
agent.

The current checkout still lacks satisfying enforcement evidence for all
runner controls, so a real authorization attempt is expected to remain
blocked. Fixture success proves the contract behavior only.

Validate any receipt independently before treating it as current evidence.
That process is documented in
`docs/agent-guides/implementation-session-start-authorization-validation.md`.
