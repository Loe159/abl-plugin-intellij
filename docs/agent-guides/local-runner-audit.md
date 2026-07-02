# Local Runner Capability Audit

`audit_local_runner.py` performs a bounded, read-only metadata audit before any
local implementation runner is designed or selected. It does not invoke Codex
as an agent, run a model, inspect credentials, modify the repository, or write
an audit artifact.

## Run

```text
python .agent/checks/audit_local_runner.py --repo . --format json
```

The CLI accepts no policy override. It runs only the exact metadata commands in
`.agent/policies/local-runner-audit.json`, without a shell, with a five-second
timeout per probe and a 120,000-byte output limit.

Raw command output, executable paths, repository paths, environment variables,
and error messages are not returned. Each probe records only status, return
code, byte counts, SHA-256 digests, and fixed marker presence.

## Evidence Vocabulary

`observed_metadata` means that one exact local metadata command succeeded and
contained every configured marker. It proves only that the installed command
advertises or exposes that interface in this environment.

`not_observed` means that the command or configured markers were not observed.
It does not prove that the capability is absent.

`not_proven` is used for every operational enforcement control. The current
audit never promotes these controls based on help text or executable presence:

- credential isolation;
- disposable-worktree lifecycle;
- filesystem write scope;
- model turn budget;
- network isolation;
- bounded output capture;
- implementation-result contract validation;
- runner-enforced output post-validation;
- implementation-patch post-validation;
- implementation quality-gate execution;
- tool allowlist;
- wall-clock timeout.

Every result retains `runner_selected=false`,
`agent_invocation_authorized=false`, and `session_start_authorized=false`.

## Why Metadata Is Not Enforcement

The installed Codex CLI currently advertises non-interactive execution,
sandbox modes, permission profiles, ephemeral sessions, structured output, and
output capture. Its approval-policy option is observed on the global Codex
interface rather than the `exec` subcommand interface, so argument placement is
material. Git worktree, WSL, and Docker metadata may also be observable. None
of those observations proves that a future runner combines them correctly,
applies the intended configuration, resists bypass, stops on budget, or cleans
up safely.

The audit also keeps authorization-consumption-to-process-start coupling
unproven. A separate synthetic fixture supplies related evidence only.

OpenAI documents that Codex sandboxing is the technical boundary for spawned
commands and that its implementation differs between native Windows and WSL2:

- https://developers.openai.com/codex/concepts/sandboxing
- https://developers.openai.com/codex/windows
- https://developers.openai.com/codex/cli/reference

Those product guarantees still require a concrete, configured invocation and
focused adversarial verification before this repository can claim enforcement.

## Next Boundary

A future experiment may test one control at a time with a harmless disposable
fixture. It must remain separate from agent invocation and authorization. A
runner should not be selected until its required controls have independent
positive and negative evidence.

The bounded timeout experiments are documented in
`docs/agent-guides/wall-clock-timeout-proof.md` and
`docs/agent-guides/windows-process-tree-timeout-proof.md`. The first concrete
launcher enforcement proof is documented in
`docs/agent-guides/parent-environment-isolation.md`; it satisfies only
parent-environment credential isolation and deliberately leaves provider
credential propagation unproven.

The supervised-runner adapter allowlist is now checked by
`.agent/checks/prove_runner_tool_allowlist.py`. That proof is separate from
this metadata audit: it observes the runner rejecting an untrusted adapter
entrypoint before authorization consumption and resolving an allowlisted
relative entrypoint to the absolute source-checkout path before launch, without
invoking a provider.

The bounded concurrent capture mechanism and excessive-output fixture are
documented in `docs/agent-guides/bounded-output-capture.md`. The separate
canonical result contract and adversarial validation proof are documented in
`docs/agent-guides/implementation-result-validation.md`. Neither metadata nor
the contract proves that a future runner always invokes post-validation.

Deterministic complete-patch generation, diff policy, and risk classification
are connected in
`docs/agent-guides/implementation-patch-post-validation.md`. That gate still
does not execute the plugin quality checks. Independent current-state
validation of its retained receipt is documented in
`docs/agent-guides/implementation-patch-post-validation-validation.md`; it does
not prove historical production or runner integration.

The fixed offline Gradle executor and its bounded synthetic process proof are
documented in `docs/agent-guides/implementation-quality-gate.md`. The fixture
does not run Gradle, prove descendant cleanup, or satisfy real quality-gate
execution. The independent receipt validator checks current candidate,
command, digest, bound, cache, and binding integrity without authenticating
historical build output.
