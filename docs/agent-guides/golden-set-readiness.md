# Golden Set Readiness

`assess_golden_set_readiness.py` evaluates a bounded external candidate
manifest for the historical benchmark described in the workflow plan. It
prevents a convenient commit message, an open issue, or an unauthenticated
snapshot from being promoted into a trusted golden case.

## Required Candidate Shape

The external JSON manifest must contain 5 to 20 unique GitHub issues from
`Loe159/abl-plugin-intellij`. Each case declares:

- the exact issue number and URL;
- a declared `closed` state;
- SHA-256 digests for the title and source snapshot;
- one or more success criteria;
- categories used to prove corpus coverage;
- either a reachable local reference commit or a refusal/escalation decision;
- bounded deterministic verification steps.

Across the corpus, the categories must cover documentation or typo work, a
simple bug, a missing test, a local feature, an ABL task requiring RSSW
research, and one case that should be refused or escalated.

For every commit reference, the checker verifies that the full commit exists,
is reachable from current `HEAD`, has a first parent, and produces a non-empty
patch. It records the reference patch digest, size, and changed paths.

## Run

For the local no-manifest preflight:

```text
python .agent/checks/check_historical_golden_set_readiness.py \
  --repo . \
  --format json
```

The current expected result is exit code `2` with `golden_set_ready=false`.
The preflight binds local files and lists the missing external controls without
selecting a corpus, authenticating GitHub, validating issue closure, or
authorizing benchmark adoption.

For an external candidate manifest:

```text
python .agent/checks/assess_golden_set_readiness.py \
  --repo . \
  --manifest <external-candidate-manifest.json> \
  --format json
```

Exit code `0` means the candidate manifest has complete category coverage and
all local commit references are available. Exit code `2` means the manifest is
well formed but local references or coverage are incomplete. Exit code `1`
means the policy, input, repository, or JSON is invalid.

## Current Repository Audit

The GitHub audit performed on June 18, 2026 found that issues `#2`, `#3`, and
`#7` through `#32` were still open. Several corresponding changes or PRs exist,
but their issue links are not reliable enough for golden evidence. In
particular, local commit `75914f64dfe051e3d19fecab7d40dc5ecc22aba5` says
`closes #8` while its behavior matches issue `#7`; GitHub issue `#8` concerns
`AblSymbolIndex` concurrency instead.

Consequently, no repository golden-set manifest is checked in and the
`historical_golden_set` capability remains incomplete. The local preflight now
records this as an explicit current-state result rather than as absent
evidence.

## Boundary

The checker accepts issue state only as a declaration inside an external
snapshot. It does not authenticate GitHub, independently prove issue closure,
or prove that a commit is the correct fix for the issue. Even a
`candidate_manifest_valid=true` result therefore keeps:

```text
source_state_authenticated=false
issue_closure_independently_verified=false
issue_reference_equivalence_verified=false
golden_set_ready=false
```

The future approved GitHub-ingestion boundary must supply independently
verifiable issue provenance before a candidate corpus can become the actual
golden set. The assessment never invokes an agent, authorizes work, mutates the
repository, or publishes data.
