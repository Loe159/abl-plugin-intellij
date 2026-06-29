# Repository Audit

Audit date: 2026-06-09. Base commit at audit start: `b2c4f39`.

This document records facts verified from the local checkout. It is not a
feature roadmap and does not certify runtime behavior.

## Scope And Result

The first agentic increment is documentation-only:

- concise repository rules in `AGENTS.md`;
- one read-only research skill in `.agents/skills/proparse-research/`;
- no Kotlin, Gradle, dependency, or GitHub workflow change.

The second increment adds only a local deterministic diff-policy validator and
its isolated standard-library tests. It still does not run an agent or publish
anything.

## Repository Facts

- Gradle project name: `abl-intellij-plugin`.
- Plugin ID: `com.ablls.abl-language-support`.
- Plugin package root: `com.ablls.plugin`.
- Kotlin/JVM toolchain: Java 17.
- IntelliJ Platform property: `2024.1`; Gradle plugin configuration declares
  `sinceBuild = 241`, while `plugin.xml` still declares `since-build="232"`.
- Main Kotlin files: 116 at audit time.
- Test Kotlin files: 31 at audit time.
- Proparse dependency: `eu.rssw.openedge.parsers:proparse:3.7.2`.
- Profiler parser dependency: `eu.rssw.openedge.parsers:profiler-parser:3.7.2`.
- Gradle wrapper: 8.11.1.

## Architecture Map

| Area | Verified paths |
| --- | --- |
| Language and PSI | `language/`, `parser/`, `highlight/` |
| RSSW parsing boundary | `core/AblParserFacade.kt`, `core/AblParseResult.kt` |
| Project analysis and symbols | `core/AblProjectAnalysisService.kt`, `core/AblSymbolCollector.kt`, `core/AblSymbolIndex.kt` |
| Editor features | `completion/`, `documentation/`, `navigation/`, `hints/`, `structure/` |
| Analysis | `annotator/`, `inspections/` |
| Execution and tooling | `run/`, `debug/`, `coverage/`, `xref/`, `duplication/`, `db/` |
| Project integration | `project/`, `startup/`, `actions/` |
| Tests | `src/test/kotlin/com/ablls/plugin/`, `src/test/testData/` |

`AblPsiParser.kt` currently creates structured composite block nodes. Any
statement that the PSI is entirely flat is stale.

## Quality Gate

`.github/workflows/quality-gate.yml` runs on pushes to `main` and pull requests:

```text
./gradlew ktlintCheck detekt
./gradlew test
./gradlew verifyPlugin
```

`.github/CODEOWNERS` contains `@Loe159`.

Branch protection cannot be verified from this checkout.

## Existing Agentic Artifacts

The worktree contained agentic experiments before this audit:

- `.agent/adapters/codex.sh` is present and modified but not validated.
- `skills/abl-dev-context/` and `skills/graphify-nav/` contain useful ideas but
  also stale paths, fixed external IDs, and unverified claims.
- staged deletions remove an older autonomous multi-role setup under `agents/`.

These artifacts must not be treated as a trusted orchestration system. This
increment does not edit or restore them.

The verified local guardrail is documented in `docs/agent-guides/diff-policy.md`.
It protects its own `.agent/**` policy and implementation from autonomous
patches.

## RSSW Evidence

No `sonar-openedge` checkout was found under `D:\` to depth 3. The published
Proparse 3.7.2 source JAR is available in the local Gradle cache and was used to
verify the APIs documented by `proparse-research`.

Verified corrections to old context:

- `AblLexerAdapter` is handwritten and only uses `ABLNodeType` for
  classification; it is not an `ABLLexer` adapter.
- `AblParseResult`, not only `AblParserFacade`, constructs `ParseUnit`.
- `ParseUnit.getRootScope()` is public in the pinned 3.7.2 source JAR, although
  the plugin currently retains a reflection fallback.
- The PSI parser is structured around block markers, not fully flat.

## Validation Status

The initial sandbox attempt could not download Gradle 8.11.1. After explicitly
allowing the pinned Gradle wrapper to run, the declared quality gate completed:

```text
.\gradlew.bat ktlintCheck detekt test verifyPlugin --no-daemon
BUILD SUCCESSFUL
```

Plugin Verifier reported compatibility with IntelliJ Community 2024.1 and
reported existing API risk: 2 deprecated usages, 156 experimental usages, and
1 internal API usage.

The bundled skill validator could not start because its Python environment does
not include PyYAML. The skill frontmatter and required fields were therefore
checked separately.

The second increment was verified with:

```text
python -m unittest discover -s .agent/checks/tests -p "test_*.py" -v
14 tests passed
```

The validator was also evaluated against the real tracked diff from `HEAD`. It
correctly blocked the existing mixed agentic experiments because they change
protected instruction/orchestration paths and exceed the 500-line threshold.
The full Gradle quality gate passed again after this increment.

The third increment adds reinforced patch/worktree consistency checks. It uses
real temporary Git repositories to verify tracked, staged, deleted, and
untracked paths; patch pre-images against a declared base; and patch post-images
against the current worktree. The isolated suite contains 21 tests after this
increment, then 22 after adding a positive complete-patch case for an untracked
file.

The reinforced validator was also run against the real checkout with a tracked
`git diff` from `HEAD`. It blocked the patch and reported the exact ten
untracked files omitted from it. The included tracked-file content passed the
base and worktree content checks.

The full Gradle quality gate passed again after the reinforced validator was
added.

The fourth increment adds a deterministic complete-patch generator. Its test
suite proves inclusion of tracked, staged, deleted, and untracked files while
preserving the real index, `HEAD`, worktree status, and repository object store.
It also refuses outputs inside the checkout and active content filters assigned
to changed paths. The combined deterministic guardrail suite contains 27 tests
and includes a Git binary-patch case.

On the real plugin checkout, the generator produced and validated a complete
patch containing all 22 changed paths without changing the worktree. Policy
then correctly blocked the artifact for protected paths, file count, and
changed-line count. The temporary artifact was removed after the test. Exact
patch size and line-count measurements are intentionally kept in command output
rather than this self-modifying checkout audit.

The fifth increment makes binary-file and symbolic-link handling explicit.
Repository policy blocks both for human approval. Detection uses canonical Git
patch metadata, reports the affected paths, and covers existing symlink target
changes as well as creation, deletion, and type changes. It deliberately does
not inspect binary content or validate link targets. The combined deterministic
guardrail suite now contains 35 tests. A real-checkout run reported no binary or
symlink paths, preserved the worktree, and retained only the three expected
policy violations. The full Gradle quality gate passed after this increment.

The sixth increment blocks explicit test disabling in `src/test/**`: adding
JUnit/Kotlin Test `@Ignore` or `@Disabled` annotations, or removing `@Test`.
Deleting or renaming a test file also requires human approval.
The repository's existing ignored integration test remains an observed baseline
and is not blocked unless a patch adds its annotation. This is intentionally not
presented as coverage protection: renamed methods, weakened assertions, and
commented-out bodies remain outside the deterministic rule. The combined
guardrail suite contains 50 tests after this increment, including adversarial
patch headers that attempt to hide a test target. A real-checkout run
reported no test-disable or test-file-removal violation and preserved the
worktree. The full Gradle quality gate passed after this increment.

The seventh increment adds a deliberately narrow high-confidence secret check
for added patch lines. It recognizes named private-key, GitHub-token, AWS-key,
and Google-key signatures without returning matching values. Unlike ordinary
policy blocks, a secret-blocked complete patch is not retained. This remains a
local complement to Gitleaks and provider-side push protection, not a claim of
complete secret detection.

The combined deterministic guardrail suite contains 58 tests after the secret
increment. The real checkout produced no secret detection, retained its
ordinary policy-blocked artifact, and preserved the worktree. Secret fixtures
prove the opposite branch: no requested artifact, no credential value in text
or JSON output, and an early stop before content/base application checks.
The full Gradle quality gate passed after this increment. It also reported the
existing non-failing recommendation to update the IntelliJ Platform Gradle
Plugin from `2.3.0` to `2.16.0`; no protected Gradle file was changed.

The eighth increment adds deterministic patch-risk classification. It maps
patches to routes A/B/C using the maximum of policy violations, verified
sensitive paths, application-code paths, file count, and changed-line count.
It cannot authorize a patch or lower a policy block. During the pilot, medium
risk requires plan and implementation review while research review remains
explicitly recommended rather than mandatory.

The combined deterministic guardrail suite contains 69 tests after the risk
classifier increment. On the real checkout, the complete retained patch was
classified `high`, route C, with `policy_allowed=false`; required gates were
research, plan, intermediate implementation, and final implementation review.
The reasons were the existing policy block plus file-count and changed-line
thresholds, and the worktree status remained unchanged.
The full Gradle quality gate passed after this increment.

The ninth increment defines a portable five-artifact phase contract with small
Markdown templates for task, research, plan, progress, and verification. Its
dependency-free validator checks exact artifact presence, scalar frontmatter,
identity, status, shared issue and base commit, required non-empty sections,
resolved placeholders, unexpected top-level Markdown, and a 20,000-byte
per-artifact limit. It deliberately does not certify truth, approval, or phase
transitions. Filled run artifacts remain external to the checkout during this
pilot.

The combined deterministic guardrail suite contains 79 tests after the artifact
contract increment.
The full Gradle quality gate passed after this increment. Plugin Verifier
reported the same existing API-risk counts as the preceding increments.

The thirteenth increment adds independent deterministic validation for a raw
read-only stage response. It authenticates the bounded bundle with a separately
provided expected SHA-256 before JSON parsing, validates embedded records and
the current repository prompt, and accepts only the exact contracted output
artifact. Research may return `complete` or `blocked`; planning may return
`awaiting_approval` or `blocked` and cannot self-approve. Accepted output remains
`authorized=false` and is not copied into the run.

The combined deterministic guardrail suite contains 117 tests after the stage
output increment.
A manual medium-risk planning scenario was exercised outside the checkout. A
raw `awaiting_approval` plan response was accepted with `authorized=false`; the
same response changed to `approved` was rejected by `response_status`, also
with `authorized=false`. The run's existing `plan.md` remained unchanged.
The complete retained checkout patch remained blocked by protected paths,
54 changed files, and 7,665 changed lines. It was classified `high`, route C,
with no binary or symbolic-link paths, and the worktree remained unchanged.
The full Gradle quality gate passed after this increment. Plugin Verifier
reported compatibility with IC 2024.1 and the same existing counts: 2
deprecated API usages, 156 experimental API usages, and 1 internal API usage.

The fourteenth increment adds a provider-neutral manual read-only adapter. It
composes the existing context builder and output validator through explicit
`prepare` and `validate` actions. Its policy supports only research and
planning, and explicitly forbids agent invocation, run mutation, response
application, and authorization. It does not call Codex or replace the
unvalidated experimental `codex.sh`. Its CLI cannot substitute alternate
policy or prompt paths.

The combined deterministic guardrail suite contains 124 tests after the manual
adapter increment. A clean temporary repository exercised the complete manual
rehearsal: research output was structurally accepted without application, a
self-approved plan was rejected by `response_status`, and both the run and
repository remained unchanged. The real intentionally dirty checkout refused
`prepare` with `clean_worktree`, created no bundle, and remained unchanged.
The complete retained checkout patch remained blocked by protected paths,
58 changed files, and 8,318 changed lines. It was classified `high`, route C,
with no binary or symbolic-link paths, and the worktree remained unchanged.
The full Gradle quality gate passed after this increment. Plugin Verifier
reported compatibility with IC 2024.1 and the same existing API-risk counts.

The fifteenth increment adds the first controlled mutation of an external
workflow run. Its separate `check` and `apply` actions bind an exact copy
confirmation to the bundle, response, complete five-artifact run snapshot, and
current target SHA-256 values.
Application revalidates the complete run, clean repository, current context
sources, response, target status, and exact bytes before atomically replacing
only `research.md` or `plan.md`. It refuses policy overrides, no-op copies,
approved or blocked targets, stale confirmations, ordinary replays, symbolic
links, self-approved plans, and high-confidence secret signatures in the
operator declaration.

The operator declaration remains unauthenticated, the confirmation can be
automated by an actor already able to execute the command, and no trusted
receipt or cross-process lock is claimed. Successful copy results still report
`authorized=false`, `stage_authorized=false`, and
`publication_authorized=false`.

A clean temporary repository exercised the two-stage procedure. A wrong
confirmation was rejected; applying research changed only `research.md` and
made planning ready; replay was rejected; applying planning changed only
`plan.md`, retained `awaiting_approval`, and left medium-risk implementation
blocked. The repository remained unchanged throughout.

The combined deterministic guardrail suite contains 135 tests after the stage
application increment. The complete retained checkout patch remained blocked
by protected paths, 62 changed files, and at least 9,327 changed lines. It was
classified `high`, route C, with no binary or symbolic-link paths, and the
worktree remained unchanged.
The full Gradle quality gate passed after this increment. Plugin Verifier
reported compatibility with IC 2024.1 and the same existing counts: 2
deprecated API usages, 156 experimental API usages, and 1 internal API usage.

The sixteenth increment adds a separate exact-plan approval transition. Its
`check` action binds a confirmation to issue, declared risk, base commit,
complete five-artifact run snapshot, and exact plan SHA-256. Its `approve`
action revalidates planning prerequisites, clean repository state, current run
and plan bytes, validates a complete candidate run, and atomically changes only
`plan.md` from `awaiting_approval` to `approved`.

The approver declaration remains unauthenticated and the confirmation can be
automated by an actor already able to execute the command. Plan provenance,
technical quality, declared risk, and approver authority are not proven.
Successful approval may make implementation prerequisites ready but always
reports `authorized=false`, `implementation_authorized=false`, and
`publication_authorized=false`; it neither starts nor authorizes execution.

The combined deterministic guardrail suite contains 143 tests after the plan
approval increment. A clean temporary medium-risk scenario was not ready for
implementation before approval. A wrong confirmation was rejected; exact
approval changed only `plan.md`; implementation readiness then became true
while authorization remained false; replay was rejected; and the repository
remained unchanged. The complete retained checkout patch remained blocked by
protected paths, 66 changed files, and at least 10,080 changed lines. It was
classified
`high`, route C, with no binary or symbolic-link paths, and the worktree
remained unchanged.
The full Gradle quality gate passed after this increment. Plugin Verifier
reported compatibility with IC 2024.1 and the same existing counts: 2
deprecated API usages, 156 experimental API usages, and 1 internal API usage.

The seventeenth increment adds a deterministic implementation-handoff builder.
It packages only exact task, research, and approved plan content plus a
content-free manifest and SHA-256 snapshot binding all five external run
artifacts. It requires a clean checkout at the exact base commit, an external
run, an output outside both checkout and run, implementation readiness, an
approved plan for every risk route, no contracted symbolic links, no
high-confidence secret signature, a final observed-state drift check, and a
70,000-byte output limit. It does not claim a cross-process lock.

The package deliberately contains no implementation prompt, repository source,
model invocation, adapter command, credential, or implicit permission. Every
result and package retains false declarations for authorization, agent
invocation, implementation, repository mutation, network access, and
publication. A low-risk run that is ready under the existing readiness policy
but still has an awaiting-approval plan is explicitly refused.

The combined deterministic guardrail suite contains 152 tests after the
implementation-handoff increment, including observed run-drift refusal. A
clean temporary repository produced byte-identical non-authorizing handoffs.
The real intentionally dirty checkout refused production with
`clean_worktree`, created no output, and retained false authorization
declarations.

The complete retained checkout patch remained blocked by protected paths, 70
changed files, and at least 10,864 changed lines. It was classified `high`,
route C, with no binary or symbolic-link paths, and the worktree remained
unchanged. The full Gradle quality gate passed after this increment. Plugin
Verifier reported compatibility with IC 2024.1 and the same existing counts: 2
deprecated API usages, 156 experimental API usages, and 1 internal API usage.

The eighteenth increment defines a deterministic proposal for a future
supervised implementation session. It adds a static supervised-write prompt
and an exact repository policy fixing the intended workspace shape,
capabilities, budgets, policy bindings, and required external controls. The
builder independently validates the exact handoff, rejects re-hashed but
inconsistent structures and authorization injection, binds critical repository
policies and the prompt by SHA-256, requires a clean matching checkout, detects
observed state drift, and emits a reproducible external proposal.

The proposal remains deliberately non-executable and non-authorizing. It does
not create a worktree, invoke an agent, authenticate a human, enforce network
isolation, enforce time or turn limits, mutate the repository or run, or
capture implementation output. Every proposal retains false declarations for
authorization, invocation, implementation, repository mutation, network,
publication, and session start.

The combined deterministic guardrail suite contains 162 tests after the
implementation-session proposal increment. A clean temporary repository
produced byte-identical proposals without changing the repository; the
proposal required a disposable-worktree shape, retained
`session_start_authorized=false`, and retained `network_access=false`. Applying
the same proposal attempt to the real intentionally dirty checkout was refused
for base and clean-worktree mismatch and created no output.

The complete retained checkout patch remained blocked by protected paths, 75
changed files, and at least 12,146 changed lines. It was classified `high`,
route C, with no binary or symbolic-link paths, and the worktree remained
unchanged. The full Gradle quality gate passed after this increment. Plugin
Verifier reported compatibility with IC 2024.1 and the same existing counts: 2
deprecated API usages, 156 experimental API usages, and 1 internal API usage.

The nineteenth increment adds independent consumer-side validation for an
exact implementation-session proposal. It verifies the separately carried
proposal digest before parsing, reconstructs and validates the embedded
handoff, compares prompt, policy bindings, capabilities, budgets, and external
controls with type-sensitive equality, requires a clean matching workspace,
and rechecks proposal and repository state immediately before returning.

The validator found and closed a validation-order drift window during its
adversarial tests. It remains read-only and always reports every authorization
and session-start declaration as false. A valid proposal is only a current
consistency result; it is not a sandbox, authorization, runner, invocation, or
proof that declared controls are enforced.

The same increment also corrected an earlier exact-content inconsistency:
handoffs now preserve optional UTF-8 BOM bytes accepted by the artifact
contract, and a focused end-to-end test proves that a BOM-bearing run survives
handoff, proposal building, and proposal validation.

The combined deterministic guardrail suite contains 171 tests after the
consumer-side validation increment. A clean temporary workspace validated an
exact proposal without changing either workspace or proposal and retained
`session_start_authorized=false`. The same proposal was refused against the
real intentionally dirty checkout for base and clean-worktree mismatch, also
with session start unauthorized.

The complete retained checkout patch remained blocked by protected paths, 78
changed files, and at least 12,908 changed lines. It was classified `high`,
route C, with no binary or symbolic-link paths, and the worktree remained
unchanged. The full Gradle quality gate passed after this increment. Plugin
Verifier reported compatibility with IC 2024.1 and the same existing counts: 2
deprecated API usages, 156 experimental API usages, and 1 internal API usage.

The tenth increment adds a read-only manual-stage readiness checker. Its
explicit policy distinguishes low-risk work from medium/high routes, requires
declared prerequisite statuses, stops on any blocked artifact, and always
reports `authorized=false`. The task and research templates now default to
`awaiting_approval` and `pending`, so merely filling templates cannot make a
stage ready. The checker does not run agents, edit artifacts, prove approvals,
or authorize publication.

The combined deterministic guardrail suite contains 90 tests after the stage
readiness increment.
The manual medium-risk scenario was exercised outside the checkout: filled
templates were not ready, declared task approval enabled research, premature
implementation remained blocked, and completed research plus an approved plan
enabled implementation while still reporting `authorized=false`. The full
Gradle quality gate passed after this increment.

The eleventh increment adds provider-neutral read-only prompts for research and
planning plus a deterministic prompt-contract validator. The prompts return
artifact content rather than writing files, require explicit untrusted-evidence
and no-side-effect guardrails, and cover every required output-artifact section.
The validator checks shape and guardrail presence; it does not prove model
compliance, sandbox enforcement, or evidence quality. No adapter invokes these
prompts yet.

The combined deterministic guardrail suite contains 97 tests after the portable
read-only prompt increment.
The repository prompts validated successfully. A temporary negative scenario
that removed the no-implementation guardrail and omitted the research
`Evidence` output section was rejected with both violations and exit code `2`.
The full Gradle quality gate passed after this increment. The existing
`.agent/adapters/codex.sh` remains an unvalidated experiment and was not used.

The twelfth increment adds a deterministic bounded-context builder for future
read-only adapters. It emits reproducible JSON containing one validated prompt
and only the stage-approved artifacts, with sizes and SHA-256 digests. It
requires a ready stage, matching repository `HEAD`, a clean checkout, external
run and output paths, no high-confidence secret signature, and a 50,000-byte
limit. It always reports `authorized=false` and does not execute an agent.

The combined deterministic guardrail suite contains 106 tests after the stage
context increment.
A clean temporary Git repository produced byte-identical research bundles on
two runs. Each reported `read-only`, `authorized=false`, and exactly the prompt
plus `task.md` as sources. The real plugin checkout correctly refused bundle
production with `clean_worktree` and created no output because this ongoing
pilot worktree is intentionally dirty.
The full Gradle quality gate passed after this increment. Plugin Verifier
reported the same existing API-risk counts as the preceding increments.

The twentieth increment adds a metadata-only local runner capability audit. It
runs only exact bounded help, version, status, and Git worktree-list probes
without a shell. Results contain statuses, byte counts, SHA-256 digests, and
fixed marker presence rather than raw output, executable paths, repository
paths, environment values, or error text.

Observed metadata is deliberately separate from enforcement. Credential
isolation, disposable-worktree lifecycle, filesystem write scope, model turn
budget, network isolation, output capture and post-validation, tool allowlist,
and wall-clock timeout always remain `not_proven`. The audit does not invoke a
model, select a runner, authorize a session, mutate the repository, or write an
artifact.

The combined deterministic guardrail suite contains 177 tests after this
increment. Two consecutive real-checkout audits were byte-identical and left
the worktree unchanged. Local metadata was observed for Codex CLI,
non-interactive Codex execution, the global Codex approval option, the Codex
sandbox helper, Git, Git worktrees, WSL, and Docker; Podman was not observed.
The installed Codex CLI also established that `--ask-for-approval` is a global
option that must precede `exec`; the existing experimental `codex.sh` remains
untouched and unvalidated.

The complete retained checkout patch remained blocked by protected paths, 82
changed files, and at least 13,621 changed lines. It was classified `high`,
route C, with no binary, symbolic-link, or high-confidence secret detection,
and the worktree remained unchanged. The full Gradle quality gate passed after
this increment. Plugin Verifier reported compatibility with IC 2024.1 and the
same existing counts: 2 deprecated API usages, 156 experimental API usages,
and 1 internal API usage.

The twenty-first increment exercises one operational control without invoking
an agent. A fixed fast Python child completes normally, while a fixed sleeping
child exceeds a 0.5-second wait, receives a direct kill, and is reaped within a
bounded cleanup period. Both run in isolated mode, without a shell, output, or
intentional side effects.

This evidence verifies only `post_spawn_direct_child_timeout` for the harmless
fixture. Process creation time, descendant-process-tree timeout, and the full
implementation-session wall-clock timeout remain `not_proven`. No runner is
selected, and all authorization fields remain false.

The combined deterministic and fixture-proof suite contains 183 tests after
this increment. Two consecutive real-checkout proofs verified the same bounded
direct-child behavior and left the worktree unchanged. The complete retained
checkout patch remained blocked by protected paths, 86 changed files, and at
least 14,160 changed lines. It was classified `high`, route C, with no binary,
symbolic-link, or high-confidence secret detection, and the worktree remained
unchanged.

The full Gradle quality gate passed after this increment. Plugin Verifier
reported compatibility with IC 2024.1 and the same existing counts: 2
deprecated API usages, 156 experimental API usages, and 1 internal API usage.

The twenty-second increment exercises Windows process-tree cleanup without
invoking an agent. A fixed root Python process creates a child that creates a
grandchild. The proof opens synchronization handles for both exact descendant
process objects, observes them running, applies `taskkill /PID <root> /T /F`
after a timeout, reaps the root, and requires both descendant handles to signal
termination within the cleanup bound.

This verifies only
`windows_taskkill_two_level_process_tree_timeout_fixture` in the current
Windows environment. Arbitrary-tree cleanup, cross-platform cleanup, process
creation timeout, and the full implementation-session wall-clock timeout
remain `not_proven`. No runner is selected, and all authorization fields remain
false.

The combined deterministic and fixture-proof suite contains 190 tests after
this increment. Two consecutive real-checkout proofs verified the same
two-level tree cleanup and left the worktree unchanged. The complete retained
checkout patch remained blocked by protected paths, 90 changed files, and at
least 14,878 changed lines. It was classified `high`, route C, with no binary,
symbolic-link, or high-confidence secret detection, and the worktree remained
unchanged.

The full Gradle quality gate passed after this increment. Plugin Verifier
reported compatibility with IC 2024.1 and the same existing counts: 2
deprecated API usages, 156 experimental API usages, and 1 internal API usage.

The twenty-third increment adds a fail-closed implementation-runner control
readiness assessment. It aggregates the fixed local metadata audit and both
bounded timeout fixtures, binds their exact scripts and policies, validates
source identities and false authorization fields, and refuses repository state
drift.

The report distinguishes `satisfied`, `related_evidence_only`, and
`missing_evidence`. Metadata and fixtures can never satisfy a runtime control.
On the real checkout, `controls_ready=false`: disposable-worktree lifecycle,
filesystem write scope, implementation-session timeout, output capture, and
tool allowlisting have only related evidence; credential isolation,
model-turn budgeting, and network isolation have missing evidence. No runner
is selected, and all authorization fields remain false.

The combined deterministic and fixture-proof suite contains 197 tests after
this increment. Two consecutive real-checkout readiness assessments returned
the same control-status matrix and left the worktree unchanged. The complete
retained checkout patch remained blocked by protected paths, 94 changed files,
and at least 15,663 changed lines. It was classified `high`, route C, with no
binary, symbolic-link, or high-confidence secret detection, and the worktree
remained unchanged.

The full Gradle quality gate passed after this increment. Plugin Verifier
reported compatibility with IC 2024.1 and the same existing counts: 2
deprecated API usages, 156 experimental API usages, and 1 internal API usage.

The twenty-fourth increment exercises one disposable Git worktree lifecycle
without touching the plugin checkout. A synthetic temporary repository creates
a detached worktree at its exact committed `HEAD`, confines tracked and
untracked dirty state to that worktree, force-removes it, prunes registrations,
and verifies that the base commit, branch set, content, and clean status remain
unchanged.

This verifies only
`disposable_git_worktree_lifecycle_fixture` for the fixed synthetic scenario.
Concurrent worktrees, implementation-runner lifecycle enforcement, and cleanup
after a host crash remain `not_proven`. Runner readiness consumes the result
only as related evidence, remains `controls_ready=false`, selects no runner, and
retains all authorization fields as false.

The combined deterministic and fixture-proof suite contains 204 tests after
this increment. The full suite initially exposed that the Windows process-tree
fixture fails closed inside the restricted process sandbox; its authorized
out-of-sandbox rerun and the complete suite then passed. The new disposable
worktree proof passed in the ordinary sandbox and left the plugin worktree
unchanged.

The complete retained checkout patch remained blocked by protected paths, 98
changed files, and at least 16,320 changed lines. It was classified `high`,
route C, with no binary, symbolic-link, or high-confidence secret detection,
and the worktree remained unchanged.

The full Gradle quality gate passed after this increment. Plugin Verifier
reported compatibility with IC 2024.1 and the same existing counts: 2
deprecated API usages, 156 experimental API usages, and 1 internal API usage.

The twenty-fifth increment adds the first deterministic preparation action for
a future supervised implementation workspace. It accepts only a clean source
checkout at an exact 40-character commit, creates one external detached clean
worktree, verifies source and target invariants, and writes an external receipt
binding the exact preparer and policy bytes.

Preparation necessarily changes source Git worktree metadata and creates the
external target and receipt. It creates no branch, invokes no agent, authorizes
no workspace use, and is not consumed as runner-readiness evidence. Failure
after creation removes the receipt and attempts bounded worktree rollback.
Cleanup after successful preparation remains explicit and human-controlled;
cross-process locking, independent receipt validation, runner lifecycle
enforcement, and crash cleanup remain unproven.

The combined deterministic and fixture-proof suite contains 213 tests after
this increment. Real temporary Git repositories verified successful detached
preparation, exact receipt bindings, refusal of dirty or mismatched sources,
path protections, and rollback after both receipt-write and postcondition
failures. The preparer was not run against the intentionally dirty plugin
checkout because that checkout correctly fails its clean-source prerequisite.

The complete retained checkout patch remained blocked by protected paths, 102
changed files, and at least 17,146 changed lines. It was classified `high`,
route C, with no binary, symbolic-link, or high-confidence secret detection,
and the worktree remained unchanged.

The full Gradle quality gate passed after this increment. Plugin Verifier
reported compatibility with IC 2024.1 and the same existing counts: 2
deprecated API usages, 156 experimental API usages, and 1 internal API usage.
The final runner-readiness assessment retained the same four evidence sources,
returned `controls_ready=false`, and did not consume the worktree-preparation
action as evidence.

The twenty-sixth increment adds independent consumer-side validation for one
exact disposable-worktree preparation receipt. It verifies the separately
carried receipt digest before parsing, requires exact false-authorization
metadata, compares preparer and policy bindings with trusted bytes, and checks
that the current source and workspace remain clean, at the exact base, and
registered together as a detached Git worktree.

The validator rejects re-hashed authorization injection, altered identity or
invariants, stale bindings, dirty or branched workspaces, dirty sources,
separate clones at the correct commit, and state drift during validation.
`valid=true` remains a read-only current-state observation; it does not
authorize workspace use, lock state, enforce runtime controls, invoke an agent,
or prove cleanup.

The combined deterministic and fixture-proof suite contains 222 tests after
this increment. Real temporary Git repositories exercised the complete
preparation-to-validation chain and all listed rejection cases. Existing
implementation-session validation and runner-readiness tests remained green.
The real checkout retained exactly its original single registered worktree.

The complete retained checkout patch remained blocked by protected paths, 106
changed files, and at least 17,867 changed lines. It was classified `high`,
route C, with no binary, symbolic-link, or high-confidence secret detection,
and the worktree remained unchanged.

The full Gradle quality gate passed after this increment. Plugin Verifier
reported compatibility with IC 2024.1 and the same existing counts: 2
deprecated API usages, 156 experimental API usages, and 1 internal API usage.

The twenty-seventh increment adds a controlled destructive cleanup action for
one exact prepared disposable worktree. It requires the separately carried
preparation-receipt digest and exact canonical workspace-path confirmation,
then accepts only a workspace still registered with the clean source,
detached, and at the preparation base. It may deliberately discard
uncommitted workspace changes, but refuses branches and divergent detached
commits.

The action removes only the named worktree registration without broad pruning,
preserves the source checkout and original preparation receipt, and writes an
external cleanup receipt binding exact tool, helper, and policy bytes plus
verified postconditions. It reports the irreducible failure boundary where Git
removal succeeds but cleanup-receipt writing fails; discarded changes cannot
be restored. Controlled cleanup does not prove runner lifecycle enforcement,
automatic cleanup, concurrent safety, or crash cleanup, and is not consumed as
runner-readiness evidence.

The combined deterministic and fixture-proof suite contains 232 tests after
this increment. Real temporary Git repositories verified exact confirmation,
dirty-workspace removal, source and receipt preservation, refusal of branches,
divergent commits, dirty sources, unregistered clones, unsafe receipt paths,
and state drift before removal. A forced-removal success followed by cleanup
receipt-write failure is reported as an irreversible error rather than proof.
The real plugin checkout retained exactly its original single registered
worktree.

The complete retained checkout patch remained blocked by protected paths, 110
changed files, and at least 18,747 changed lines. It was classified `high`,
route C, with no binary, symbolic-link, or high-confidence secret detection,
and the worktree remained unchanged.

The full Gradle quality gate passed after this increment. Plugin Verifier
reported compatibility with IC 2024.1 and the same existing counts: 2
deprecated API usages, 156 experimental API usages, and 1 internal API usage.
The runner-readiness assessment remained `controls_ready=false` and did not
consume the explicit cleanup action as lifecycle-enforcement evidence.

The twenty-eighth increment adds a separate read-only consumer for one exact
preparation receipt and one exact cleanup receipt. It verifies both separately
carried digests before parsing, exact schemas and trusted bindings, cross-
receipt identity and base consistency, then requires the source to remain
clean at the preparation base and the workspace path to remain absent and
unregistered.

The validator rejects altered or re-hashed authorization metadata, identity,
postconditions, bindings, preparation-receipt references, and base commits. It
also rejects recreated or re-registered workspaces, source drift, unsafe paths,
and state drift during validation. `valid=true` remains a current-state
observation. It does not authenticate who performed cleanup, reconstruct
discarded files, prove historical preservation of every other registration,
or prove an automated runner lifecycle.

The combined deterministic and fixture-proof suite contains 242 tests after
this increment. Real temporary Git repositories exercised the complete
preparation-to-cleanup-to-validation chain and all listed rejection cases. The
real plugin checkout retained exactly its original single registered worktree.

The complete retained checkout patch remained blocked by protected paths, 114
changed files, and at least 19,574 changed lines. It was classified `high`,
route C, with no binary, symbolic-link, or high-confidence secret detection,
and the worktree remained unchanged.

The full Gradle quality gate passed after this increment. Plugin Verifier
reported compatibility with IC 2024.1 and the same existing counts: 2
deprecated API usages, 156 experimental API usages, and 1 internal API usage.
The runner-readiness assessment remained `controls_ready=false`; cleanup
receipt validation is intentionally not lifecycle-enforcement evidence.

The twenty-ninth increment adds deterministic local initialization of one
portable workflow run from an external task specification that a human has
already normalized. The bounded JSON input records one issue, risk, exact base
commit, source reference, and the five required task sections. It is explicitly
not a raw-issue ingester, GitHub client, sanitizer, risk classifier, or approval
mechanism.

The initializer requires a clean checkout at the exact declared base, rejects
high-confidence secret signatures, creates exactly the five contracted
Markdown artifacts from trusted templates, validates their complete contract,
and writes an external receipt binding the exact input digest, run manifest,
initializer, imported helpers, templates, and policies. It publishes the final
run path exclusively and rolls back only outputs it created after
post-creation failure.

Every initialized task remains `awaiting_approval`, every authorization field
remains false, and the fresh run is deliberately not ready for `research`.
Later-stage sections state that their stage has not run. Initialization does
not authenticate the source reference or a human approval, prove task claims,
or verify the declared risk.

The combined deterministic and fixture-proof suite contains 251 tests after
this increment. Real temporary Git repositories verified reproducible
artifacts, structural validity, initial non-readiness, secret and path
protections, input and repository drift rejection, exclusive output creation,
and rollback after receipt failure. Existing artifact, readiness, and stage-
context integration tests remained green. The real plugin checkout retained
exactly its original single registered worktree.

The complete retained checkout patch remained blocked by protected paths, 118
changed files, and at least 20,606 changed lines. It was classified `high`,
route C, with no binary, symbolic-link, or high-confidence secret detection,
and the worktree remained unchanged.

The full Gradle quality gate passed after this increment. Plugin Verifier
reported compatibility with IC 2024.1 and the same existing counts: 2
deprecated API usages, 156 experimental API usages, and 1 internal API usage.
The runner-readiness assessment remained `controls_ready=false`. Run
initialization is intentionally not approval, authorization, or runner-control
evidence.

The thirtieth increment adds the only current controlled transition from an
initialized `task.md: awaiting_approval` to `task.md: approved`. The two-step
local control requires the exact external initialization receipt, its
separately carried SHA-256, an unauthenticated approver declaration, and a
clean checkout at the exact task base.

Before presenting a confirmation, the checker validates the complete initial
run, exact receipt schema, fixed initial manifest, and trusted initialization
bindings. The confirmation binds the approver declaration, receipt, complete
run snapshot, exact task bytes, and exact task-approval controls. Approval
repeats those checks, rechecks run, task, receipt, and control bytes
immediately before mutation, validates a complete candidate run, and
atomically changes only the task status line.

The initialization receipt deliberately ceases to match the run after
approval, so replay is rejected. Research prerequisites then report ready, but
all authorization and authentication fields remain false. The control does
not authenticate the declared approver, prove task claims or risk, start a
stage, invoke an agent, or authorize repository, network, or publication
actions.

The combined deterministic and fixture-proof suite contains 259 tests after
this increment. Eight focused task-approval tests cover exact successful
transition, read-only checking, receipt and run tampering, stale confirmations,
approver binding, replay, path and secret protections, and last-moment control
drift. The full suite passed after rerunning outside the restricted sandbox
because one existing fixture requires Git access to a system temporary
directory.

The complete retained checkout patch remained blocked by protected paths, 122
changed files, and at least 21,557 changed lines. It was classified `high`,
route C, with no binary or symbolic-link detection, and the worktree remained
unchanged.

The full Gradle quality gate passed after this increment. Plugin Verifier
reported compatibility with IC 2024.1 and the same existing counts: 2
deprecated API usages, 156 experimental API usages, and 1 internal API usage.
The runner-readiness assessment remained `controls_ready=false`. Explicit task
approval is intentionally not authenticated identity, stage authorization, or
runner-control evidence.

The thirty-first increment adds an independent read-only consumer for one
portable-run initialization receipt and its exact current initial run. It
requires the separately carried receipt SHA-256 before parsing, validates the
exact receipt schema, false authorization metadata, identity, initial
manifest, and trusted initializer bindings, then checks the current clean
checkout at the exact base.

Before reporting `valid=true`, the validator rechecks the receipt bytes,
complete run snapshot, repository state, and its own exact validator bindings.
It rejects altered or re-hashed authorization metadata, identity, manifest,
trusted bindings, run bytes, initial statuses, high-confidence secret
signatures, base drift, dirty checkouts, unsafe paths, and state drift during
validation.

Task approval now consumes this independent validator as its single
initialization-receipt interpretation instead of maintaining duplicate
receipt-validation logic. After approval, the receipt intentionally no longer
matches the initial run, so both independent validation and replayed approval
fail closed.

`valid=true` remains current-state evidence. It does not authenticate who
initialized the run, prove the normalized source or task claims, approve the
task, authorize research, start an agent, or prove historical state.

The combined deterministic and fixture-proof suite contains 268 tests after
this increment. Nine focused initialization-validation tests cover valid
read-only consumption, digest-before-parse behavior, re-hashed metadata,
identity, manifest, and binding changes, run and repository drift, secret
rejection, unsafe paths, CLI behavior, and state drift during validation.
Existing task-approval tests prove the approval path consumes the independent
validator without changing its authorization boundary.

The complete retained checkout patch remained blocked by protected paths, 126
changed files, and at least 22,187 changed lines. It was classified `high`,
route C, with no binary or symbolic-link detection, and the worktree remained
unchanged.

The full Gradle quality gate passed after this increment. Plugin Verifier
reported compatibility with IC 2024.1 and the same existing counts: 2
deprecated API usages, 156 experimental API usages, and 1 internal API usage.
The runner-readiness assessment remained `controls_ready=false`. Independent
receipt validation is intentionally not approval, authorization, or
runner-control evidence.

The thirty-second increment makes controlled task approval produce a bounded,
durable receipt outside both the checkout and portable run. The exact
confirmation now binds the reserved absent receipt path, initialization
receipt, approver declaration, issue, risk, base, complete pre-approval run,
candidate post-approval run, exact pre- and post-approval task bytes, and
trusted approval controls.

The approver writes the receipt exclusively before atomically changing only
the task status. Before the task mutation, the receipt deliberately does not
match the current run. After a successful mutation, it binds the resulting
approved task and complete run. Handled failures roll back the task only while
its bytes still match the exact candidate and remove only the receipt created
by that attempt.

The ordering fails closed across process crashes, but cannot provide
transactional crash recovery. A crash before task mutation can leave an
invalid receipt beside an unapproved task; a crash after mutation can leave
the approved task and matching receipt. The receipt is not signed and does not
authenticate the declared approver.

No independent consumer validates the task-approval receipt yet. Generic stage
readiness still evaluates artifact statuses only, so `ready=true` does not
currently establish approval provenance or authorize a stage. Independent
approval-receipt validation is the next provenance control to add before
making readiness depend on the receipt.

The combined deterministic and fixture-proof suite contains 270 tests after
this increment. Ten focused task-approval tests cover the exact successful
transition and receipt, read-only checking, receipt-write and post-mutation
failure rollback, existing-receipt rejection, tampering, replay, path and
secret protections, stale confirmations, and last-moment control drift.

The complete retained checkout patch remained blocked by protected paths, 126
changed files, and at least 22,501 changed lines. It was classified `high`,
route C, with no binary or symbolic-link detection, and the worktree remained
unchanged.

The full Gradle quality gate passed after this increment. Plugin Verifier
reported compatibility with IC 2024.1 and the same existing counts: 2
deprecated API usages, 156 experimental API usages, and 1 internal API usage.
The runner-readiness assessment remained `controls_ready=false`. The durable
receipt is intentionally traceability data, not approval authentication,
stage authorization, or runner-control evidence.

The thirty-third increment adds an independent read-only consumer for one
task-approval receipt and its exact current approved portable run. It requires
the separately carried receipt SHA-256 before parsing, validates the exact
receipt schema and false authorization metadata, and checks the current clean
checkout at the exact task base.

The validator independently reconstructs the unique frontmatter transition
from `awaiting_approval` to `approved`, the exact task and complete run
snapshots before and after approval, the trusted approval-control bindings,
and the confirmation bound to the external approval-receipt path. It rejects
copied receipts whose path no longer matches the confirmation, re-hashed
metadata, identity, transition, or binding changes, unsafe paths, secrets,
run or repository drift, and state changes during validation.

The initialization receipt bytes are not required because they deliberately
cease to match the run after approval. The approval validator checks that the
approval receipt carries a valid initialization-receipt SHA-256 and binds it
into the reconstructed confirmation, but it cannot independently revalidate
the historical initial run.

`valid=true` remains current-state integrity and provenance evidence. It does
not prove historical execution of the producer, authenticate the approver,
prove task claims or risk, authorize research, start an agent, or make SHA-256
a signature. Generic stage readiness still does not consume this validator,
so readiness alone remains status-only.

The combined deterministic and fixture-proof suite contains 280 tests after
this increment. Ten focused task-approval-validation tests cover valid
read-only consumption, digest-before-parse behavior, exact frontmatter
reconstruction, re-hashed schema, metadata, identity, digest, transition, and
binding changes, receipt-path binding, unsafe paths, secret redaction, run and
repository drift, CLI behavior, and state drift during validation.

The complete retained checkout patch remained blocked by protected paths, 130
changed files, and at least 23,346 changed lines. It was classified `high`,
route C, with no binary or symbolic-link detection, and the worktree remained
unchanged.

The full Gradle quality gate passed after this increment. Plugin Verifier
reported compatibility with IC 2024.1 and the same existing counts: 2
deprecated API usages, 156 experimental API usages, and 1 internal API usage.
The runner-readiness assessment remained `controls_ready=false`. Independent
approval validation is intentionally not approver authentication, stage
authorization, or runner-control evidence.

The thirty-fourth increment adds a provenance-aware readiness gate for the
`research` stage. The generic stage-readiness checker remains a status-only
engine, but actual research context preparation now also requires an external
task-approval receipt and its separately carried SHA-256 to pass the
independent task-approval validator.

The new research-readiness checker combines declared `research` readiness with
valid approval provenance, records its own trusted bindings, and rechecks
those bindings before reporting `ready=true`. It reports `declared_ready` and
`task_approval_valid` separately so operators can distinguish a missing status
transition from invalid provenance.

Stage-context bundles are now version 2. A `research` bundle carries only the
approval-receipt digest as provenance metadata, and context construction
revalidates the research-readiness gate immediately before writing the bundle.
`plan` bundles still carry `provenance.kind=none` and reject approval-receipt
arguments. The manual read-only adapter now passes the receipt path and digest
through during research preparation.

Stage-output validation checks the version-2 provenance schema and the bundle
digest that binds the response to that provenance record. It intentionally
does not reopen or revalidate the external receipt; receipt validity is a
context-build precondition, not a response-validation side effect.

`ready=true` remains current-state readiness evidence only. It does not
authorize research, start an agent, authenticate the approver, prove task
claims or risk, prove historical producer execution, or enforce runner
controls.

The combined deterministic and fixture-proof suite contains 290 tests after
this increment. Eight focused research-readiness tests cover valid provenance,
manual status edits without receipts, invalid and tampered receipts, binding
drift, CLI behavior, and non-authorization. Stage-context, manual-adapter,
stage-output, and application tests cover provenance requirements, final
pre-write revalidation, and version-2 bundle validation.

The complete retained checkout patch remained blocked by protected paths, 134
changed files, and at least 24,103 changed lines. It was classified `high`,
route C, with no binary or symbolic-link detection, and the worktree remained
unchanged.

The full Gradle quality gate passed after this increment. Plugin Verifier
reported compatibility with IC 2024.1 and the same existing counts: 2
deprecated API usages, 156 experimental API usages, and 1 internal API usage.
The runner-readiness assessment remained `controls_ready=false`.
Provenance-aware research readiness is intentionally not stage authorization,
approver authentication, or runner-control evidence.

The thirty-fifth increment makes operator-confirmed stage application produce
a bounded, durable receipt outside both the checkout and portable run. The
application policy is now version 2 and requires an absent external receipt
path during both `check` and `apply`.

The exact application confirmation now binds the stage, target artifact,
bundle SHA-256, pre-copy run snapshot, post-copy run snapshot, response
SHA-256, replaced target SHA-256, trusted application-control bindings, and
reserved receipt path. `apply` repeats the full assessment, writes the receipt
exclusively, atomically replaces exactly one artifact, validates the final run,
and verifies that the receipt bytes and post-copy run snapshot still match the
confirmed operation.

The receipt records the unauthenticated reviewer declaration, stage, artifact,
status, issue, risk, base commit, run path, bundle SHA-256, pre- and post-copy
run snapshots, response and replaced-target digests, confirmation digest, and
trusted application bindings. It always records authorization fields as false.

Handled failures remove only the receipt created by that attempt and restore
the target only while its bytes still match the attempted replacement. The
ordering fails closed for later provenance checks, but still is not
transactional crash recovery. A crash can leave an invalid receipt or an
applied artifact without a usable receipt. No independent consumer validates
this receipt yet, and plan context preparation still does not require it.

The combined deterministic and fixture-proof suite contains 291 tests after
this increment. Twelve focused stage-application tests cover policy version 2,
read-only confirmation binding, successful receipt writing, single-artifact
replacement, plan non-approval, stale confirmations, receipt-path refusal,
rollback after receipt/write failure, replay rejection, dirty checkout and
context drift, invalid reviewer declarations, and secret redaction.

The complete retained checkout patch remained blocked by protected paths, 134
changed files, and at least 24,443 changed lines. It was classified `high`,
route C, with no binary or symbolic-link detection, and the worktree remained
unchanged.

The full Gradle quality gate passed after this increment. Plugin Verifier
reported compatibility with IC 2024.1 and the same existing counts: 2
deprecated API usages, 156 experimental API usages, and 1 internal API usage.
The runner-readiness assessment remained `controls_ready=false`.
Stage-application receipts are intentionally not approval, approver
authentication, plan-readiness provenance, stage authorization, or
runner-control evidence.

The thirty-sixth increment adds an independent read-only validator for one
stage-application receipt and its exact current applied run. It requires the
separately carried receipt SHA-256 before parsing, validates the exact receipt
schema and false authorization metadata, and checks the current clean checkout
at the recorded base commit.

The validator reconstructs the application confirmation digest from the
receipt fields and current trusted controls, verifies the current run snapshot
against the receipt's post-application snapshot, verifies the current target
artifact digest against the recorded response digest, and rejects altered
bindings, copied receipt paths, unsafe paths, high-confidence secret
signatures, run drift, repository drift, and state changes during validation.

`valid=true` remains current-state integrity evidence. It does not reopen the
original bundle or captured response, prove that a human confirmed the copy,
approve research or a plan, authorize `plan` context preparation, start an
agent, or make SHA-256 a signature. `plan` preparation still does not require
this receipt; adding that composite gate is a later increment.

The combined deterministic and fixture-proof suite contains 298 tests after
this increment. Seven focused stage-application-validation tests cover valid
research and plan receipts, digest-before-parse behavior, re-hashed metadata,
identity, confirmation, and binding changes, run and repository drift, secret
redaction, unsafe paths, CLI behavior, and non-authorization.

The complete retained checkout patch remained blocked by protected paths, 138
changed files, and at least 25,191 changed lines. It was classified `high`,
route C, with no binary or symbolic-link detection, and the worktree remained
unchanged.

The full Gradle quality gate passed after this increment. Plugin Verifier
reported compatibility with IC 2024.1 and the same existing counts: 2
deprecated API usages, 156 experimental API usages, and 1 internal API usage.
The runner-readiness assessment remained `controls_ready=false`.
Stage-application receipt validation is intentionally not artifact approval,
stage authorization, plan-readiness provenance, approver authentication, or
runner-control evidence.

The thirty-seventh increment wires validated research-application provenance
into `plan` context preparation. Stage-context policy is now version 3:
`research` still requires independently validated task-approval provenance,
while `plan` now requires an independently validated stage-application receipt
for the current applied `research.md`.

`build_stage_context.py` rejects plan bundles without the separately carried
research-application receipt SHA-256, validates the receipt before reading
the planning sources, requires it to describe `stage=research`,
`artifact=research.md`, and `status=complete`, and revalidates the receipt
immediately before writing the bundle. The bundle records only the receipt
SHA-256 as provenance metadata; it does not embed the receipt or authorize
planning.

`validate_stage_output.py` now accepts the version-3 provenance schema for
both research and plan bundles. The manual read-only adapter forwards
application receipt provenance for `plan` while remaining non-mutating and
non-authorizing. Existing stage-application and stage-output tests now prepare
planning through an applied research receipt instead of manually marking
research complete.

The combined deterministic and fixture-proof suite contains 299 tests after
this increment. Focused stage-context, stage-output, stage-application, and
manual-adapter tests cover missing and invalid plan provenance, revalidation
before bundle write, plan response validation against version-3 bundles, and
manual rehearsal without run mutation or authorization.

The complete retained checkout patch remained blocked by protected paths,
138 changed files, and at least 25,526 changed lines. It was classified
`high`, route C, with `policy_allowed=false`, and the worktree remained
unchanged.

`valid=true`, `produced=true`, and `accepted=true` remain evidence about the
current local artifacts only. This increment does not prove research claims,
approve a plan, authorize a stage, start an agent, authenticate an operator,
or enforce runner controls.

The thirty-eighth increment wires validated applied-plan provenance into the
exact plan-approval transition. `plan-approval.json` is now version 2 and
requires a valid stage-application receipt for the current `plan.md` before
`approve_plan.py check` can report `approvable=true`.

Both `check` and `approve` now require the separately carried plan-application
receipt SHA-256. The assessment validates the receipt through
`validate_stage_application.py`, requires `stage=plan`, `artifact=plan.md`,
and `status=awaiting_approval`, and binds the receipt digest into the exact
approval confirmation. `approve` repeats the same receipt validation after
confirmation and immediately before changing only the plan status line.

The plan-approval path remains non-authorizing. A valid applied-plan receipt
shows that the current plan bytes match an operator-confirmed copy operation;
it does not prove the plan is correct, authenticate the approver, authorize
implementation, start an agent, or make implementation-runner controls ready.

The combined deterministic and fixture-proof suite contains 300 tests after
this increment. Focused plan-approval tests cover the version-2 policy, exact
confirmation binding to the applied-plan receipt digest, missing and invalid
receipt refusal, read-only `check`, single-line status mutation on approval,
replay rejection, drift rejection, and continued non-authorization.

The complete retained checkout patch remained blocked by protected paths,
138 changed files, and at least 25,670 changed lines. It was classified
`high`, route C, with `policy_allowed=false`, and the worktree remained
unchanged.

The thirty-ninth increment makes exact plan approval emit a bounded durable
receipt outside both the checkout and portable run. `plan-approval.json` is
now version 3, reserves an absent external receipt path during `check`, and
binds that path plus exact plan-approval control bytes into the required
confirmation.

`approve_plan.py approve` repeats applied-plan receipt validation, verifies the
run snapshot, plan bytes, and plan-approval bindings immediately before
mutation, writes the plan-approval receipt exclusively, atomically changes only
the plan status line, validates the final run and implementation readiness,
then verifies the receipt bytes and expected post-approval hashes. Handled
failures remove only the receipt created by that attempt and restore the plan
only while it still matches the attempted approved bytes.

The receipt records the unauthenticated approver declaration, applied-plan
receipt SHA-256, confirmation SHA-256, issue, risk, base commit, run path,
pre- and post-approval run snapshots, pre- and post-plan digests, and trusted
plan-approval bindings. It always records authorization fields as false.

This receipt is traceability data only. There is not yet an independent
plan-approval receipt validator, and implementation handoff does not consume
the receipt yet. The receipt does not prove plan correctness, authenticate the
approver, authorize implementation, start an agent, or make runner controls
ready.

The combined deterministic and fixture-proof suite contains 300 tests after
this increment. Focused plan-approval tests cover the version-3 policy, exact
confirmation binding to the applied-plan receipt and reserved approval-receipt
path, receipt creation, external path refusal, existing receipt refusal,
single-line status mutation, replay and drift rejection, and non-authorization.

The complete retained checkout patch remained blocked by protected paths,
138 changed files, and at least 25,945 changed lines. It was classified
`high`, route C, with `policy_allowed=false`, and the worktree remained
unchanged.

The fortieth increment adds independent read-only validation for the durable
plan-approval receipt. `validate_plan_approval.py` consumes an external
approved run, an external plan-approval receipt, and a separately carried
receipt SHA-256. It validates the receipt before parsing, reconstructs the
unique frontmatter-only `awaiting_approval` to `approved` plan transition,
rebuilds the exact approval confirmation including the bound receipt path,
checks trusted plan-approval bindings, and requires the current run to remain
approved and implementation-ready.

The new `plan-approval-validation.json` policy is version 1 and remains
validation-only. The validator requires the run and receipt outside the
checkout, the receipt outside the run, repository `HEAD` equal to the run base
commit, and a clean worktree. It also checks high-confidence secret signatures
and rechecks receipt, run, repository, and validator-control stability before
reporting `valid=true`.

The validator does not need the applied-plan receipt bytes. It verifies that
the plan-approval receipt carries a valid applied-plan receipt SHA-256 and
binds that digest into the reconstructed confirmation. This keeps validation
bounded while leaving full provenance-chain policy to a later consumer.

`valid=true` remains current-state integrity evidence only. It does not prove
historical execution of `approve_plan.py`, authenticate the approver, prove
plan correctness, authorize implementation, start an agent, or make runner
controls ready. Implementation handoff still does not consume the validator;
that gate remains a later increment.

The combined deterministic and fixture-proof suite contains 310 tests after
this increment. Focused plan-approval-validation tests cover exact policy
binding, read-only validation, receipt digest refusal before parsing, metadata
and identity tampering, transition drift, trusted binding mismatch,
unapproved state, missing implementation readiness, dirty checkout, moved
repository `HEAD`, secret redaction, validation-time drift, internal path and
symlink refusal, missing policy overrides, and CLI behavior.

The complete retained checkout patch remained blocked by protected paths,
142 changed files, and at least 26,801 changed lines. It was classified
`high`, route C, with `policy_allowed=false`, and the worktree remained
unchanged.

The forty-first increment wires independent plan-approval validation into the
implementation handoff gate. `implementation-handoff.json` is now version 2
and requires a valid external plan-approval receipt for the exact current
approved run before a handoff can be produced.

`build_implementation_handoff.py` now requires `--plan-approval-receipt` and
`--plan-approval-receipt-sha256`. It validates the receipt through
`validate_plan_approval.py`, preserves only the separately carried receipt
SHA-256 in the handoff bundle, and keeps every authorization field false. The
handoff still includes exact `task.md`, `research.md`, and `plan.md` content,
the five-artifact manifest, the run snapshot, base commit, repository `HEAD`,
and no implementation prompt or source files.

`build_implementation_session.py` now accepts `handoff_version=2` and requires
the handoff's `plan_approval_receipt_sha256` field to be a SHA-256 digest.
Session proposals therefore consume the stronger handoff schema without
treating it as invocation authorization.

The focused handoff tests now construct a real receipt chain through portable
initialization, task approval, research application, plan application, plan
approval, plan-approval validation, and handoff production. They cover missing
or invalid plan-approval receipts, continued low-risk approved-plan gating,
non-authorization, reproducibility, drift refusal, dirty checkout, moved
`HEAD`, internal paths, symlinks, size limits, and policy override refusal.

This gate remains provenance integrity evidence only. It does not authenticate
the approver, prove plan correctness, authorize implementation, start an
agent, or make runner controls ready.

The combined deterministic and fixture-proof suite contains 311 tests after
this increment. Focused handoff and session tests cover the version-2 handoff
policy, required plan-approval receipt validation, missing receipt rejection,
handoff schema consumption by session proposal, proposal validation against
the stronger handoff package, and continued non-authorization.

The complete retained checkout patch remained blocked by protected paths,
142 changed files, and at least 27,106 changed lines. It was classified
`high`, route C, with `policy_allowed=false`, and the worktree remained
unchanged.

The forty-second increment binds implementation-session proposals to the
existing disposable-worktree preparation and validation chain. The session
policy is now version 2 and requires `require_valid_disposable_worktree=true`.
`build_implementation_session.py` now requires `--workspace`,
`--worktree-receipt`, and `--worktree-receipt-sha256`; it validates the
prepared worktree against the exact preparation receipt, requires the same
base commit as the handoff, records only a bounded `prepared_workspace`
summary in the proposal, and revalidates the workspace before writing output.

`validate_implementation_session.py` now consumes the same workspace and
receipt inputs. It revalidates the prepared worktree, compares the proposal's
prepared-workspace summary with current validation, and rechecks that state
before returning `valid=true`. The proposal and validator both bind the
disposable-worktree validator and policy bytes, and the required external
controls now include `disposable_worktree_validation`.

This remains current-state integrity evidence only. It does not authorize
workspace use, start a session, prove that a future runner is confined to the
prepared worktree, enforce no-network/tool/time/turn controls, or guarantee
cleanup after success, failure, timeout, or host crash.

The combined deterministic and fixture-proof suite contains 313 tests after
this increment. Focused builder and validator tests cover valid prepared
workspace binding, dirty prepared-worktree refusal, rehashed
prepared-workspace summary refusal, continued authorization falsehoods, CLI
strictness, and state-drift refusal. The full Gradle quality gate also passed.

The forty-third increment adds an exact local approval gate for a validated
implementation-session proposal. `approve_implementation_session.py` provides
`check` and `approve` subcommands backed by
`.agent/policies/implementation-session-approval.json`. The check requires a
valid proposal, the same prepared worktree and receipt inputs, a clean matching
source checkout, an external absent approval receipt path, and
`assess_runner_readiness.py` reporting `controls_ready=true`.

The approval confirmation binds the issue, risk, base commit, exact proposal
SHA-256, disposable-worktree receipt SHA-256, runner-readiness report SHA-256,
approval-control bindings, and approval receipt path. The approve step repeats
the assessment after confirmation and writes only an external receipt. The
receipt records `session_proposal_approved=true`, but keeps authorization,
runner selection, agent invocation, repository mutation, network, publication,
and session-start fields false.

This gate is expected to block in the real pilot checkout until runner
readiness has satisfying enforcement evidence. It does not authenticate the
approver, select a runner, invoke an agent, enforce a sandbox, prove workspace
confinement, or authorize session start.

The forty-fourth increment adds independent read-only validation for the
implementation-session approval receipt.
`validate_implementation_session_approval.py` consumes the exact proposal,
proposal digest, prepared worktree, disposable-worktree receipt and digest,
external approval receipt, and separately carried approval receipt digest. It
checks the receipt digest before parsing, requires the exact schema and false
authorization fields, revalidates the proposal, reruns runner-readiness
assessment, recalculates the approval confirmation digest, compares trusted
approval bindings, and rechecks receipt, repository, and validator state before
returning `valid=true`.

The new validation policy is
`.agent/policies/implementation-session-approval-validation.json`. Real
validation remains expected to fail in this pilot until runner readiness has
satisfying enforcement evidence. `valid=true` remains current-state integrity
evidence only; it is not runner selection, session authorization, sandbox
enforcement, or proof of cleanup.

Subsequent implementation-invocation increments add non-authorizing preflight
production and validation, invocation-readiness checking, runner-selection
readiness, and session-start readiness. These checks deliberately split
evidence from permission: a valid preflight can make the fixed runner candidate
selectable, and the session-start checker can report
`session_start_ready=true`, while every authorization field remains false.

At that point, `check_implementation_session_start.py` consumed
`check_implementation_runner_selection.py` and recorded the currently missing
`session_start_authorization` instead of starting anything or producing a
launch receipt. `check_implementation_invocation_readiness.py` policy version 2
could observe both runner-selection readiness and session-start readiness, but
still reported `invocation_ready=false` pending a separate exact explicit
start-authorization gate and independent validation.

The next skill increment adds `.agents/skills/agentic-workflow-pilot/`, a
repo-local operating guide for future small workflow changes. It deliberately
contains no scripts or assets: it tells future agents how to preserve the
evidence-vs-permission boundaries, when to use `proparse-research`, and what
validation and patch reporting are expected. A repository skill test checks
frontmatter, UI metadata, and absence of template TODOs for local skills.

The workflow-status increment adds a machine-readable capability ledger and
`check_workflow_status.py`. It records the local patch and portable-artifact
guardrails as implemented, the research and planning adapter as manual-only,
and the implementation chain as readiness-only. At that increment it explicitly
recorded the enforced runner, start authorization, approved GitHub issue
ingestion, deterministic draft-PR publisher, metrics, historical golden set,
and multi-adapter comparison as not yet implemented or not ready.

The checker binds declared evidence files and consumes current runner-readiness
evidence. Even a future `controls_ready=true` runner result cannot make the
pilot ready while the other required capabilities remain missing. The ledger
is a current local status report only and keeps every authorization field
false.

The run-metrics increment adds `.agent/checks/record_run_metrics.py` and an
exact `.agent/policies/run-metrics.json` contract. It accepts a bounded external
post-run observation, calculates duration from UTC timestamps, and measures an
exact external implementation patch by digest. The resulting external JSON
record includes adapter, model, token and cost provenance, outcome, human
corrections, final disposition, regression status, diff statistics, and source
and policy hashes.

Metrics recording is manual evidence only. The checker permits explicit
`unavailable`, `not_assessed`, and `pending` states instead of treating missing
data as zero. It does not run or observe an agent, query provider usage, prove
billing, authenticate the observer, determine post-merge regressions, or
authorize any later action. The workflow ledger therefore marks metrics as
`manual_evidence_recording_only`; later increments separately added bounded
GitHub ingestion and start-authorization contracts.

The golden-set readiness increment audits the real GitHub issue inventory
before creating benchmark data. On June 18, 2026, issues `#2`, `#3`, and `#7`
through `#32` were open. Existing commits and PRs therefore cannot be treated
as five resolved historical issues. The audit also found a concrete provenance
mismatch: commit `75914f64dfe051e3d19fecab7d40dc5ecc22aba5` says `closes #8`,
but its token-width behavior matches issue `#7`; issue `#8` is about
`AblSymbolIndex` concurrency.

`assess_golden_set_readiness.py` now validates an external 5-to-20-case
candidate manifest, required category coverage, bounded success criteria, and
reachable non-empty local reference commits. It deliberately keeps remote
source authentication, independent issue-closure verification,
issue-to-reference equivalence, and `golden_set_ready` false. No candidate
manifest is checked in from the currently unsuitable inventory, and the
workflow ledger records `historical_golden_set` as `candidate_contract_only`.

The GitHub issue-ingestion increment adds
`.agent/checks/approve_github_issue_snapshot.py` and the exact
`.agent/policies/github-issue-ingestion.json` contract. A bounded external
package carries one declared open issue with exactly the `agent:approved`
workflow label plus a separately human-written risk, base commit, and five
task sections. Extra fields such as comments are rejected, the raw body is
bounded and secret-scanned, and only the human normalization enters the
portable-run input.

The `check`, `approve`, and `validate` commands bind the exact package,
normalized input, reviewer declaration, checkout base, trusted controls, and
external output paths. Outputs are exclusive and independently recalculated.
The tool remains a manual snapshot boundary: it does not call or authenticate
GitHub, verify who applied the label, authenticate the reviewer, or authorize
research or agent invocation. The workflow ledger records
`approved_github_issue_ingestion` as `manual_snapshot_approval_only`.

The session-start authorization increment adds an exact two-step local consent
gate and an independent validator. The receipt binds the proposal, prepared
workspace, worktree receipt, proposal approval, preflight, fixed runner
candidate, current session-start readiness, policy bytes, authorizer
declaration, and external output path. It records only
`session_start_authorized=true`; agent invocation, implementation, repository
mutation, network, publication, and runner selection remain false.

`check_implementation_invocation_readiness.py` policy version 3 can consume the
exact receipt and makes `invocation_ready=true` reachable in a fixture where
all runner controls are satisfied. The real checkout remains not ready because
runner enforcement evidence is still missing. The receipt does not
authenticate its authorizer or enforce replay prevention, and the readiness
checker neither consumes the receipt nor invokes anything. A future runner
must provide atomic one-time consumption before real execution.

The parent-environment isolation increment adds the first concrete runtime
primitive, `.agent/checks/isolated_process.py`. It requires an absolute
executable, disables shell use and standard input, reconstructs the child
environment from an exact allowlist, and bounds timeout and output.
`prove_parent_environment_isolation.py` injects synthetic markers under six
sensitive variable names and confirms through a real isolated Python child that
none of those names crosses the launcher boundary.

Runner readiness now splits the earlier vague credential control. It marks
`parent_environment_credential_isolation=satisfied`, while
`provider_credential_descendant_noninheritance=missing_evidence`. No synthetic
value is emitted by the proof. This does not show that credentials deliberately
given to a future Codex process, loaded from files, or obtained through an
operating-system store are hidden from commands that Codex later spawns.

The bounded-output increment replaces post-capture acceptance with concurrent
streaming inside the same exact launcher. Two reader threads feed fixed-size
chunks into a bounded queue, while the main capture loop retains no more than
the configured combined ceiling. A timeout still applies when a child closes
both streams and continues running.

`prove_bounded_output_capture.py` verifies exact dual-stream content and
digests, then exercises an excessive-output child. The latter is rejected,
reaped, and returns no partial output. Runner readiness now marks
`bounded_output_capture=satisfied`; no result schema, patch, secret, task
provenance, or deterministic quality check is validated by this byte-level
mechanism.

The implementation-result increment adds a strict portable JSON schema,
`.agent/checks/validate_implementation_result.py`, and an adversarial proof.
The validator consumes the actual bounded execution record, requires canonical
UTF-8 JSON, binds issue, risk, base commit, workspace, runner, preflight, and
start-authorization receipt identity, and rejects incomplete capture, nonzero
protocol exit, nonempty stderr, extra fields, high-confidence secret
signatures, and claims that deferred deterministic actions already occurred.

A valid `completed` result only makes the workspace a candidate for external
patch generation. A valid `blocked` or `failed` result remains non-candidate
protocol evidence. Runner readiness now marks
`implementation_result_contract_validation=satisfied` but keeps
`runner_enforced_output_post_validation=missing_evidence`. No real agent was
invoked, no runner was built, and patch generation, policy validation, quality
checks, publication, and real-agent compatibility remain outside this proof.

The post-implementation patch increment adds
`.agent/checks/validate_implementation_patch.py`. It revalidates the exact
captured result, snapshots the declared workspace through
`generate_complete_patch.py`, applies the existing diff policy, classifies the
existing risk route, and writes a bounded external receipt. Output paths must
be absent, distinct, and outside both source and implementation checkouts.
Failures remove both outputs.

`prove_implementation_patch_validation.py` uses disposable Git repositories to
show that an allowed patch becomes candidate-ready, a protected-path patch
remains retained but blocked in route `C`, an empty patch remains auditable but
non-candidate, and an invalid result creates no artifact. Runner readiness marks
`implementation_patch_post_validation=satisfied` while keeping
`implementation_quality_gate_execution=missing_evidence`. The receipt records
the quality gate as required, incomplete, and not passed.

The receipt-validation increment adds
`.agent/checks/validate_implementation_patch_receipt.py`. It independently
revalidates the exact result, expected session, retained patch bytes, current
worktree match, diff-policy result, risk route, candidate state, receipt
digest, and trusted bindings. Inputs must be distinct external regular files,
and any observed state change fails closed.

`prove_implementation_patch_receipt_validation.py` verifies an allowed receipt,
a valid but policy-blocked route-`C` receipt, a valid empty receipt that cannot
be candidate-ready, and rejection after patch tampering. Runner readiness marks
`implementation_patch_receipt_validation=satisfied`. This is current-state
integrity only: historical producer identity, runner integration, the plugin
quality gate, agent invocation, approval, and publication remain unproven.

The quality-gate mechanism increment adds
`.agent/checks/run_implementation_quality_gate.py`. It requires an independently
valid, nonempty, policy-allowed patch receipt before running the three fixed
Gradle command groups in offline and no-daemon mode. It reconstructs a bounded
environment, captures both streams with a fixed limit, stops after the first
failure, records timeout and cleanup outcomes, and writes a canonical external
receipt without raw build logs.

`prove_implementation_quality_gate.py` exercises only synthetic capture,
timeout, and output-limit fixtures. In the current sandbox, `taskkill /T /F`
returns nonzero and the direct-root fallback reaps the root, so descendant
cleanup remains unproven. Runner readiness therefore reports
`implementation_quality_gate_execution=related_evidence_only` and
initially reported `quality_gate_receipt_validation=missing_evidence`.

A disposable README-only candidate was then executed manually through the
exact gate on June 18, 2026. Static analysis, tests, and Plugin Verifier all
passed; the external quality-gate receipt SHA-256 is
`7b1ffd7408a76818e1c76aa2549fd3408759ff5785358219fc7dea73cd64dbd8`.
Because the receipt remained external, temporary, and independently
unvalidated, this rehearsal did not initially satisfy either readiness
control.

The receipt-validation increment adds
`.agent/checks/validate_implementation_quality_gate.py`. It revalidates the
candidate patch chain, exact quality-gate receipt digest, fixed command order,
fail-fast sequence, runtime bounds, current Gradle cache, and producer
bindings. It accepts an accurate failed receipt without treating the gate as
passed and rejects rehashed command substitution.

`prove_implementation_quality_gate_validation.py` verifies passed, failed, and
tampered synthetic receipts. The retained real receipt
`7b1ffd7408a76818e1c76aa2549fd3408759ff5785358219fc7dea73cd64dbd8`
also passes current-state validation. Runner readiness now marks
`quality_gate_receipt_validation=satisfied` while keeping
`implementation_quality_gate_execution=related_evidence_only`, because output
digests without retained logs do not authenticate the historical processes.

The next increment adds exact local consumption of a validated session-start
authorization receipt. `consume_implementation_session_start_authorization.py`
revalidates the full chain and exclusively creates an adjacent `.consumed.json`
marker, so a second ordinary local consumption is rejected. The marker keeps
all invocation and authorization fields false; it is neither tamper resistant
nor cross-host, invokes no agent, and promotes no runner-readiness control.

The following increment adds independent validation of that marker.
`validate_implementation_session_start_consumption.py` checks its separately
carried digest before parsing, canonical schema, false authorization fields,
identity, exact derived path, producer bindings, current authorization
validity, and final state drift. The producer also repeats authorization
validation immediately before exclusive marker creation.

This closes ordinary local producer/consumer drift but still does not sign or
protect the marker from deletion, share replay state across hosts, invoke an
agent, or atomically couple consumption to process launch.

The next increment adds `check_implementation_launch_readiness.py`, a final
read-only agreement check requiring both current invocation readiness and the
validated consumption marker. A fully ready synthetic runner fixture reaches
`launch_ready=true`; current real runner controls remain not ready. The checker
does not select a runner, invoke a process, or atomically couple the marker to a
launch.

The next increment adds a synthetic local claim-before-spawn fixture.
`prove_implementation_launch_transaction.py` exclusively creates a claim bound
to a harmless marker digest, launches one bounded Python child through
`isolated_process.py`, and rejects replay before a second spawn. Runner
readiness names `authorization_consumption_to_process_start` explicitly and
records this proof as `related_evidence_only`.

The fixture does not consume a real authorization chain, invoke Codex, close
the crash window between claim creation and spawn, or prevent cross-host
replay. It cannot satisfy the required control or make the runner ready.

A June 19, 2026 local audit attempted to turn the Codex Windows sandbox into a
bounded network-isolation fixture. With `codex-cli 0.137.0`, an exact profile
declaring `network.enabled=false` still allowed both loopback TCP and an
external TCP connection. More importantly, the sandbox returned before a
Windows cache write completed and later created a literal `%SystemDrive%`
directory under the checkout when launched from the reconstructed environment.

The experimental network probe was removed rather than retained as readiness
evidence. Its generated cache was deleted after exact path verification. The
result is a documented local observation only: network isolation remains
`missing_evidence`, and no current check invokes that active sandbox fixture.
The metadata-only `codex sandbox --help` probe was verified separately and
remains read-only.

The cache mutation also exposed a separate defect in the synthetic quality-gate
proof. It used the Windows App Execution Alias for Python under an environment
that omitted `SYSTEMDRIVE`, `ALLUSERSPROFILE`, and `PROGRAMDATA`. The fixture
now uses the regular interpreter under `sys.prefix`, and both bounded launch
policies preserve those non-secret platform paths. Both policies also reject
local Windows App Execution Alias executables under
`AppData\Local\Microsoft\WindowsApps`.

The draft-PR publication preflight increment adds
`.agent/checks/check_draft_pr_publication_readiness.py`. It binds only local
files, reports `publication_ready=false`, keeps every repository mutation,
network, external-service, and publication field false, and lists the missing
external controls required for any future deterministic publisher. The workflow
ledger now records this as `local_preflight_only`; the deterministic publisher
capability remains unimplemented and required.

The multi-adapter comparison preflight increment adds
`.agent/checks/check_multi_adapter_comparison_readiness.py`. It binds only
local files, reports `comparison_ready=false`, keeps adapter invocation, model
invocation, network, repository mutation, external-service, and metrics fields
false, and lists the missing controls required before any future comparison can
be treated as ready. The workflow ledger records this as `local_preflight_only`;
the multi-adapter comparison capability remains unimplemented and required.

The historical golden-set preflight increment adds
`.agent/checks/check_historical_golden_set_readiness.py`. It binds the local
golden-set checker, policy, and guide; reports `golden_set_ready=false`; keeps
GitHub authentication, issue-closure verification, issue-reference equivalence,
agent invocation, repository mutation, network, publication, and adoption fields
false; and lists the missing controls required before a historical corpus can
be selected. The workflow ledger records this as `local_preflight_only`; the
historical golden-set capability remains unimplemented and required.

The runner output post-validation fixture increment adds
`.agent/checks/prove_runner_output_post_validation.py`. It exercises only a
synthetic wrapper around `validate_implementation_result.validate_execution(...)`
with a valid captured result, a session-identity mismatch, and a bypass record
with no validator invocation. Runner readiness records this as related evidence
for `runner_enforced_output_post_validation`; the required control remains
unsatisfied because no real implementation runner proves that every invocation
calls the validator or that real model output is compatible.

## Open Questions

- Should the old `skills/` experiments be migrated, archived, or removed after
  their useful facts are reconciled?
- Should the modified `.agent/adapters/codex.sh` be discarded or redesigned
  only after local read-only research and plan stages are proven manually?
- Which RSSW repository checkout and commit should be the canonical source for
  research beyond published Proparse 3.7.2?
- Which of the conflicting IntelliJ minimum versions, `232` or `241`, is
  intentional?
- Should a later plan-approval transition require a locally authenticated or
  cryptographically signed human identity, rather than an unauthenticated
  operator declaration?
- Which local supervised runner can actually enforce the proposed disposable
  workspace, no-network rule, tool restrictions, timeout, turn budget, and
  atomic one-time authorization consumption before real invocation?
