---
name: agentic-workflow-pilot
description: Use when planning, extending, or validating the local ABL IntelliJ plugin agentic workflow guardrails, portable-run artifacts, implementation-session checks, or repo-local skills; keeps increments small, deterministic, non-authorizing, and honest about what is unproven.
---

# Agentic Workflow Pilot

Use this skill to keep the local workflow pilot incremental and honest. The
goal is to improve deterministic guardrails and learning artifacts without
turning evidence into permission.

## Workflow

1. Read `AGENTS.md`, then only the relevant `docs/agent-guides/*.md` files for
   the stage being touched.
   Read `docs/agent-guides/workflow-status.md` before making a broad completion
   or end-to-end readiness claim.
   Read `docs/agent-guides/run-metrics.md` before recording or comparing a run.
   Read `docs/agent-guides/golden-set-readiness.md` before selecting historical
   benchmark cases.
   Read `docs/agent-guides/github-issue-ingestion.md` before normalizing an
   external GitHub issue snapshot.
   Read `docs/agent-guides/implementation-session-start-authorization.md`
   before producing or consuming explicit local start consent.
   Read `docs/agent-guides/parent-environment-isolation.md` before changing
   child-process environment handling or credential-isolation claims.
   Read `docs/agent-guides/bounded-output-capture.md` before changing runtime
   output handling or claiming implementation-result validation.
   Read `docs/agent-guides/implementation-result-validation.md` before
   changing the portable implementation result or its post-capture checks.
   Read `docs/agent-guides/implementation-patch-post-validation.md` before
   connecting a candidate result to patch generation or policy validation.
   Read
   `docs/agent-guides/implementation-patch-post-validation-validation.md`
   before consuming a post-validation receipt.
   Read `docs/agent-guides/implementation-quality-gate.md` before changing or
   running deterministic implementation checks.
2. Identify the next smallest useful guardrail, skill, receipt, validator, or
   documentation increment. Prefer one boundary over a broad workflow rewrite.
3. Preserve these separations:
   - readiness is not authorization;
   - validation is not approval;
   - runner selection readiness is not runner selection;
   - session-start readiness is not session-start authorization;
   - session-start authorization is not invocation or replay protection;
   - parent-environment isolation is not provider-credential noninheritance;
   - bounded output capture is not result-contract validation;
   - result-contract validation is not runner-enforced post-validation;
   - a valid implementation result is not a validated patch;
   - an empty validated patch is not an implementation candidate;
   - a policy-allowed patch is not a passed quality gate;
   - patch post-validation is not approval or publication authorization;
   - a valid patch receipt is current-state evidence, not historical producer
     proof, quality approval, or runner enforcement;
   - a bounded quality-gate fixture is not a real Gradle execution;
   - a passed quality gate is not patch approval or publication authorization;
   - a valid quality-gate receipt does not authenticate historical build logs;
   - any `valid=true`, `ready=true`, `produced=true`, or `accepted=true` result
     is current-state evidence only unless a later guide says otherwise.
4. Keep every implementation-session, runner, invocation, network, mutation,
   publication, and session-start authorization field false unless the task is
   explicitly to design a reviewed authorization gate.
5. When changing ABL language behavior, stop and use `proparse-research` first.
6. Add focused standard-library tests for new Python checks or policy
   contracts. For documentation-only changes, prefer a structural test only
   when it prevents a real regression such as stale template markers or missing
   metadata.
7. Run the smallest relevant tests first, then the full Python check suite and
   Gradle quality gate when the environment permits.
8. Produce complete patch artifacts with `generate_complete_patch.py`; never
   hand-assemble a candidate patch.
9. Preserve unknown measurements as `unavailable` or `not_assessed`; never
   encode missing provider, human-review, or regression evidence as zero.
10. Reject open issues, mismatched issue references, and unauthenticated remote
    snapshots as golden evidence even when a related local patch exists.
11. Keep raw issue bodies and comments out of normalized task sections; require
    exact human-written normalization and preserve the source snapshot digest.

## Output

Report:

```text
Increment
What changed
What remains explicitly unproven
Validation run
Patch artifact and policy/risk result, when produced
```

Keep the summary concrete. Do not say the workflow is safe, autonomous,
authorized, enforced, or ready to run unless the exact current gate proves that
claim.
