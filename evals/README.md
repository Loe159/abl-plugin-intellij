# Evaluation Scaffolding

This directory is reserved for future agent-comparison assets.

There is currently no adopted historical golden set checked into this
repository. `evals/golden-set.yaml` is only a versioned status marker: it
records that no corpus is adopted, no issue state has been authenticated, and
no benchmark adoption is authorized. The current pilot defers this requirement
because the repository is too young to provide a trustworthy historical issue
corpus. If useful historical commits exist before an external candidate
manifest has been written, a local shortlist draft can be produced with:

```text
python .agent/checks/draft_golden_set_manifest.py \
  --repo . \
  --output <external-absent-draft.json> \
  --format json
```

The draft output is only a local commit shortlist. It is not an adopted corpus
and cannot substitute for closed issue evidence.

When merged PRs exist, a separate draft can be produced with:

```text
python .agent/checks/draft_pr_golden_set_manifest.py \
  --repo . \
  --output <external-absent-pr-draft.json> \
  --format json
```

The PR draft is also not an adopted corpus; it exists to help a human create
or map proper benchmark cases. It reads merged PR metadata through `gh`.

Historical cases must still be supplied as an external candidate manifest and
assessed with:

```text
python .agent/checks/assess_golden_set_readiness.py \
  --repo . \
  --manifest <external-candidate-manifest.json> \
  --format json
```

The manifest must contain only bounded, human-written normalized task sections
plus source digests. Raw issue bodies and comments remain untrusted source data
and should not be copied into normalized benchmark tasks.

Even a valid candidate manifest is not an adopted golden set until source state
is authenticated, issue closure is independently verified, issue-to-reference
equivalence is reviewed, and a human adoption decision is recorded.
