# Golden Set Readiness

`assess_golden_set_readiness.py` evaluates a bounded external candidate
manifest for the historical benchmark described in the workflow plan. It
rejects local shortcuts such as convenient commit messages, open issue
declarations, in-checkout manifests, and malformed snapshots before they can be
mistaken for candidate evidence. It does not authenticate GitHub state or turn
a candidate into an adopted golden case.

## Required Candidate Shape

The external JSON manifest must contain 5 to 20 unique GitHub issues from
`Loe159/abl-plugin-intellij`. Each case declares:

- the exact issue number and URL;
- a declared `closed` state;
- SHA-256 digests for the title and source snapshot;
- human-written normalized task sections for agent comparison, without raw
  issue bodies or comments;
- one or more success criteria;
- declared categories used to check required corpus-shape coverage;
- either a reachable local reference commit or a refusal/escalation decision;
- bounded verification-step text.

Across the corpus, the categories must cover documentation or typo work, a
simple bug, a missing test, a local feature, an ABL task requiring RSSW
research, and one case that should be refused or escalated.

For every commit reference, the checker verifies that the full commit exists,
is reachable from current `HEAD`, has a first parent, and produces a non-empty
patch. It records the reference patch digest, size, and changed paths.

Each candidate case must include a bounded `task` object with:

- `title`, `goal`, and `background`;
- one or more human-written `acceptance_criteria`;
- bounded `constraints` and `out_of_scope` lists, which may be empty.

The assessment output records only a digest summary of each normalized task.
It deliberately does not echo raw issue text, task prose, or comments into the
result.

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

## Draft From Local Commits

When the repository has useful historical commits but no closed GitHub issues,
create a non-authoritative draft shortlist outside the checkout:

```text
python .agent/checks/draft_golden_set_manifest.py \
  --repo . \
  --output <external-absent-draft.json> \
  --format json
```

The draft records local commit patch digests and category hints. It is not a
candidate manifest, cannot be adopted, and always keeps
`candidate_manifest_valid=false` and `golden_set_ready=false`. A human must
still supply closed issue snapshots, normalized task sections, success
criteria, and issue-to-reference review before using
`assess_golden_set_readiness.py`.

When the repository has merged pull requests but no closed issues, create a
second draft from GitHub PR metadata:

```text
python .agent/checks/draft_pr_golden_set_manifest.py \
  --repo . \
  --output <external-absent-pr-draft.json> \
  --format json
```

This draft binds PR numbers, titles by digest, merge commits, changed paths,
bounded title text, and local merge-commit availability. It reads merged PR
metadata through the GitHub CLI, so it is a networked drafting aid rather than
a local readiness validator. It remains non-adoptable because merged PRs do
not provide the issue-shaped corpus, refusal/escalation case, and
human-normalized task sections required by the current historical golden-set
contract.

## Adopt An Exact Candidate

After a candidate manifest is valid and a human has independently authenticated
the source issue state, verified that the issues are closed, and reviewed the
issue-to-reference equivalence, record the exact local adoption receipt in two
steps:

```text
python .agent/checks/approve_golden_set.py check \
  --repo . \
  --manifest <external-candidate-manifest.json> \
  --receipt <external-absent-adoption-receipt.json> \
  --format json
```

Then rerun with the exact confirmation string:

```text
python .agent/checks/approve_golden_set.py adopt \
  --repo . \
  --manifest <external-candidate-manifest.json> \
  --receipt <external-absent-adoption-receipt.json> \
  --approver <human-declaration> \
  --source-state-authenticated \
  --issue-closure-independently-verified \
  --issue-reference-equivalence-reviewed \
  --confirm <exact-confirmation-from-check> \
  --format json
```

The adoption receipt does not authenticate the approver, contact GitHub, invoke
an agent, select a model, authorize publication, or merge anything. It records
only that the exact current manifest and local reference evidence were adopted
with the required human attestations.

For `assess_golden_set_readiness.py`, exit code `0` means the candidate
manifest has complete declared category coverage and all local commit
references are available. It still keeps `golden_set_ready=false` until a
separate exact adoption receipt records the required human attestations. Exit
code `2` means the manifest is well formed but local references or coverage
are incomplete. Exit code `1` means the policy, input, repository, or JSON is
invalid.

## Current Repository Audit

The GitHub audit performed on June 18, 2026 found that issues `#2`, `#3`, and
`#7` through `#32` were still open. Several corresponding changes or PRs exist,
but their issue links are not reliable enough for golden evidence. In
particular, local commit `75914f64dfe051e3d19fecab7d40dc5ecc22aba5` says
`closes #8` while its behavior matches issue `#7`; GitHub issue `#8` concerns
`AblSymbolIndex` concurrency instead.

Consequently, no adopted repository golden-set corpus is checked in and the
`historical_golden_set` capability remains incomplete. The local preflight now
records this as an explicit current-state result rather than as absent
evidence.

The `evals/` directory is reserved for benchmark scaffolding.
`evals/golden-set.yaml` is a status marker, not a corpus: it records
`adoption_status: not_adopted`, `case_count: 0`, and the required external
candidate/adoption boundary. The readiness checker hashes this file as current
state evidence while keeping `golden_set_ready=false`.

## Boundary

The checker accepts issue state only as a declaration inside an external
snapshot. It does not authenticate GitHub, independently prove issue closure,
or prove that a commit is the correct fix for the issue. Even a
`candidate_manifest_valid=true` result therefore keeps:

```text
source_state_authenticated=false
issue_closure_independently_verified=false
issue_reference_equivalence_verified=false
candidate_manifest_approved=false
golden_set_ready=false
```

The future approved GitHub-ingestion boundary must supply independently
verifiable issue provenance before a candidate corpus can become the actual
golden set. The assessment never invokes an agent, authorizes work, mutates the
repository, or publishes data.
