# Draft PR Publication Readiness

`check_draft_pr_publication_readiness.py` is a local preflight boundary for the
deterministic draft-PR publisher. It does not push a branch, create a pull
request, call GitHub, authenticate a remote, mutate the repository, or authorize
publication.

`publish_draft_pr.py` is the reviewed publication component. By default it
performs a dry run: it validates the retained implementation evidence, writes a
deterministic PR body, records the exact commands that would be run, and writes
a publication receipt. It performs external writes only when called with
`--execute` by a human who is deliberately requesting publication.

## Run

```text
python .agent/checks/check_draft_pr_publication_readiness.py \
  --repo . \
  --format json
```

Exit code `0` would mean the exact local preflight reports
`publication_ready=true`. The current expected result is exit code `2` with
`publication_ready=false`. Exit code `1` means policy, repository, or I/O
failure. The CLI accepts no policy, network, remote, branch, push, or PR
creation override.

## Readiness Boundary

The preflight binds only local files and reports the external controls that are
still missing:

- an explicit publication request;
- authenticated remote repository evidence;
- a policy-allowed candidate patch;
- a validated quality-gate receipt;
- an exact branch push result;
- an exact draft-PR creation result.

Every output keeps these fields false:

```text
authorized=false
repository_mutation_authorized=false
network_authorized=false
publication_authorized=false
draft_pr_created=false
branch_pushed=false
external_service_written=false
```

This check is useful because it gives the workflow ledger a deterministic local
publication boundary without pretending that external publication is available,
permitted, or already requested.

## Publisher

Dry-run publication plan:

```text
python .agent/checks/publish_draft_pr.py \
  --repo . \
  --result <external-run>/result.json \
  --expected-session <external-run>/expected-session.json \
  --patch <external-run>/patch.diff \
  --patch-receipt <external-run>/patch-validation.json \
  --patch-receipt-sha256 <sha256> \
  --quality-gate-receipt <external-run>/quality-gate.json \
  --quality-gate-receipt-sha256 <sha256> \
  --gradle-user-home <external-gradle-cache> \
  --branch codex/agent-ISSUE-123 \
  --title "Fix ABL completion edge case" \
  --summary "Human-reviewed summary for the draft PR." \
  --body-output <external-run>/draft-pr-body.md \
  --receipt-output <external-run>/draft-pr-publication.json \
  --format json
```

External publication requires the same command plus `--execute`. The executed
path runs, in the implementation workspace, the deterministic sequence:

```text
git checkout -B <branch> <base_commit>
git add -A
git commit -m <title>
git push --set-upstream <remote> <branch>
gh pr create --draft --base <base> --head <branch> --title <title> --body-file <body>
```

In an executed run, `publication_requested`, `publication_authorized`,
`network_authorized`, and `repository_mutation_authorized` record only that the
human deliberately requested the publication path. Outcome fields stay
evidence-based: `branch_pushed`, `draft_pr_created`, and
`external_service_written` remain `false` when validation blocks before the
commands run, and are set from the observed command results rather than from
the presence of `--execute`.

The publisher still does not approve the patch, merge it, publish a release, or
override branch protection. It depends on the independently validated quality
gate receipt and creates only a draft PR.

## Honest Boundary

`publication_ready=false` is not a failure to publish. It is the current
state-evidence result. The publisher preserves the repository rule that pushing,
publishing, or creating a PR requires an explicit human request.
