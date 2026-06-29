# Draft PR Publication Readiness

`check_draft_pr_publication_readiness.py` is a local preflight boundary for a
future deterministic draft-PR publisher. It does not push a branch, create a
pull request, call GitHub, authenticate a remote, mutate the repository, or
authorize publication.

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

## Current Boundary

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
publication boundary without pretending that external publication is available
or permitted.

## Honest Boundary

`publication_ready=false` is not a failure to publish. It is the current
state-evidence result. A later publisher must still be reviewed separately and
must preserve the repository rule that pushing, publishing, or creating a PR
requires an explicit human request.
