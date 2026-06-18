# Local Diff Policy

This is the first executable agentic guardrail. It validates a Git unified diff
without invoking an LLM, changing the worktree, or contacting an external
service.

## Purpose

The validator answers one narrow question:

> Is this patch small enough and free of protected-path changes to continue to
> human review and deterministic checks?

It does not prove correctness, security, test coverage, or suitability for
merge.

By default it validates only the supplied patch. Unless a secret signature
causes an early fail-closed stop, the reinforced worktree mode also proves that:

- patch paths exactly equal all tracked and untracked worktree changes;
- the patch pre-image applies to the declared base commit;
- the patch post-image matches the current worktree.

The content checks use `git apply --check`; the base check uses a temporary Git
index. They do not modify the checkout or its real index. Secret-blocked
candidates skip those application checks and remain blocked.

## Policy

`.agent/policies/diff-policy.json` currently blocks:

- changes to agent instructions and orchestration files;
- changes to trusted agent guides;
- changes to `.github/**`, Gradle, wrapper, plugin manifest, quality configuration,
  build scripts, and `.gitignore`;
- paths containing `..` or absolute paths;
- binary file changes;
- symbolic link creation, deletion, target changes, and type changes;
- explicit test disabling in `src/test/**` by adding `@Ignore` or `@Disabled`,
  or removing `@Test`;
- deletion or rename of files under `src/test/**`;
- high-confidence secret signatures on added lines, without echoing values;
- patches changing more than 12 files;
- patches changing more than 500 added and removed lines.

Protected-path changes are not forbidden forever. They require a human-led task
outside an autonomous implementation patch.

Binary files and symbolic links also require explicit human approval. The
validator identifies them from canonical Git patch metadata and reports their
paths. It does not inspect binary content, follow links, or decide that an
approved file is safe.

The policy fields `allow_binary_files` and `allow_symlinks` make these decisions
explicit. The repository policy sets both to `false`; omitting either field is a
policy input error rather than an implicit default.

Test-disable detection inspects only added and removed patch lines under the
configured `test_path_patterns`. The configured regular expressions cover the
JUnit 4, JUnit 5, and Kotlin Test annotation forms used or plausible in this
repository. Existing ignored tests are not blocked unless the patch adds their
ignore annotation again.

Secret detection is documented in `docs/agent-guides/secret-scan.md`. It is a
small local complement to, not a replacement for, Gitleaks or provider-side
push protection. `secret_patterns` is a required, explicit policy field; each
entry has a unique ID and a validated regular expression.

## Exit Codes

| Code | Meaning |
| --- | --- |
| `0` | Patch is allowed by this policy. |
| `1` | Validator or policy input error. |
| `2` | Patch is well-formed but blocked by policy. |

## Run Locally

Use any Python 3 installation:

```text
python .agent/checks/diff_policy.py --patch patch.diff
python .agent/checks/diff_policy.py --patch patch.diff --format json
python .agent/checks/diff_policy.py --patch patch.diff --repo . --base <base-commit>
python -m unittest discover -s .agent/checks/tests -p "test_*.py" -v
```

Always use `--repo` and `--base` together for an agent-produced implementation
patch. Pass the checkout root as `--repo`. Omitting both is useful only for
testing a standalone patch artifact. Git's `safe.directory` exception is scoped
to each read-only validator subprocess; the validator does not edit global Git
configuration.

Create the patch from a clean base explicitly. For example:

```text
git diff --binary --output=patch.diff <base-commit>...HEAD
```

Let Git write the patch directly. Shell redirection, especially Windows
PowerShell redirection, can silently change the patch encoding. Do not validate
an implicit or unknown base. Store `patch.diff` outside the checkout, otherwise
the reinforced worktree mode correctly treats the patch artifact itself as an
untracked worktree change.

`git diff` does not include untracked files. If the worktree contains any, the
reinforced mode intentionally blocks this patch as incomplete. Use the
deterministic generator documented in `docs/agent-guides/complete-patch.md`.

## Deliberate Limits

This increment does not detect renamed test methods, weakened assertions,
commented-out test bodies, generic passwords, high-entropy unknown credentials,
repository-history secrets, or missing matching tests. It also does not inspect
binary content or validate symbolic-link targets. Each should be added only with
focused fixtures and clear failure behavior.
