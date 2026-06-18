# Complete Patch Generator

`generate_complete_patch.py` creates one Git patch representing the complete
checkout state relative to an explicit base commit. It includes tracked,
staged, deleted, and non-ignored untracked files.

## Guarantees

The generator:

- requires the output patch to be outside the checkout;
- uses a temporary Git index and temporary object database;
- does not modify the checkout, real index, `HEAD`, or repository object store;
- disables external diff, textconv, and fsmonitor helpers;
- refuses content filters assigned to changed files;
- generates the patch with Git;
- validates diff policy and worktree state;
- validates paths, content, and base commit for candidates that do not trigger
  the early secret stop;
- reports the patch SHA-256 and byte size.

The generated artifact normally remains available when policy validation blocks
it. A patch with a high-confidence secret signature is the exception: the
requested artifact is not retained. Exit code `2` means policy blocked the
candidate, not that generation failed. For a secret violation, it deliberately
does not claim that content/base application checks passed.

## Run

Use an output path outside the checkout:

```text
python .agent/checks/generate_complete_patch.py \
  --repo . \
  --base <base-commit> \
  --output <external-path>/patch.diff \
  --format json
```

Use `--force` only when replacing the named external artifact is intentional.

After generating an ordinary retained artifact, classify its supervision route:

```text
python .agent/checks/classify_patch_risk.py \
  --patch <external-path>/patch.diff \
  --repo . \
  --base <base-commit> \
  --format json
```

Classification never overrides the generator's policy result.

## Trust Boundary

This is a deterministic local tool, not an agent. It does not push, commit,
publish, contact GitHub, or call an LLM.

It reads the complete checkout state. Therefore, run it only after deciding
that every non-ignored worktree change belongs to the candidate patch.

## Current Limits

- Patches must be UTF-8 or Git binary patches.
- The repository policy blocks binary files and symbolic links for explicit
  human approval; it does not inspect their contents or link targets.
- The repository policy blocks configured explicit test-disable annotations,
  test-file deletion, and test-file rename, but does not prove that test
  coverage or assertions remain adequate.
- The generator does not run build, tests, lint, repository-history secret
  scanning, or a full tool such as Gitleaks.
