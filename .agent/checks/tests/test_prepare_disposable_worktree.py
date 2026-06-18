from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "prepare_disposable_worktree.py"
REPO_ROOT = CHECKS_DIR.parents[1]
SPEC = importlib.util.spec_from_file_location("prepare_disposable_worktree", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
preparer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = preparer
SPEC.loader.exec_module(preparer)


def git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def create_repo(path: Path) -> str:
    path.mkdir()
    git(path, "init")
    git(path, "config", "user.email", "tests@example.invalid")
    git(path, "config", "user.name", "Tests")
    (path / "README.md").write_text("base\n", encoding="utf-8")
    git(path, "add", "README.md")
    git(path, "commit", "-m", "base")
    return git(path, "rev-parse", "HEAD")


def cleanup(repo: Path, target: Path) -> None:
    if target.exists():
        git(repo, "worktree", "remove", "--force", str(target))
    git(repo, "worktree", "prune", "--expire", "now")


class PrepareDisposableWorktreeTest(unittest.TestCase):
    def test_repository_policy_is_exact_preparation_only_and_non_authorizing(self) -> None:
        policy = preparer.load_policy()

        self.assertEqual(preparer.EXPECTED_POLICY, policy)
        self.assertEqual("preparation-only", policy["mode"])
        self.assertTrue(policy["rollback_on_failure"])
        self.assertTrue(policy["require_source_clean"])
        self.assertNotIn("codex", json.dumps(policy).lower())

    def test_real_preparation_creates_exact_detached_clean_worktree_and_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            base = create_repo(repo)
            target = temp / "workspace"
            receipt = temp / "receipt.json"
            before_head = git(repo, "rev-parse", "HEAD")
            before_status = git(repo, "status", "--porcelain=v1", "--untracked-files=all")
            before_branches = git(repo, "for-each-ref", "--format=%(refname)", "refs/heads")

            result = preparer.prepare(repo, base, target, receipt, preparer.load_policy())
            value = json.loads(receipt.read_text(encoding="utf-8"))

            self.assertTrue(result["prepared"])
            self.assertTrue(target.is_dir())
            self.assertEqual(base, git(target, "rev-parse", "HEAD"))
            self.assertEqual("HEAD", git(target, "rev-parse", "--abbrev-ref", "HEAD"))
            self.assertEqual("", git(target, "status", "--porcelain=v1", "--untracked-files=all"))
            self.assertEqual(before_head, git(repo, "rev-parse", "HEAD"))
            self.assertEqual(before_status, git(repo, "status", "--porcelain=v1", "--untracked-files=all"))
            self.assertEqual(
                before_branches,
                git(repo, "for-each-ref", "--format=%(refname)", "refs/heads"),
            )
            self.assertTrue(value["workspace_prepared"])
            self.assertTrue(value["cleanup_required"])
            self.assertEqual(
                [
                    ".agent/checks/prepare_disposable_worktree.py",
                    ".agent/policies/disposable-worktree-preparation.json",
                ],
                [record["name"] for record in value["bindings"]],
            )
            for field in preparer.FALSE_FIELDS:
                self.assertFalse(value[field])
            cleanup(repo, target)

    def test_dirty_source_and_head_mismatch_do_not_create_worktree_or_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            base = create_repo(repo)
            (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
            target = temp / "dirty-workspace"
            receipt = temp / "dirty-receipt.json"
            result = preparer.prepare(repo, base, target, receipt, preparer.load_policy())
            self.assertIn("source_clean", [item["rule"] for item in result["failures"]])
            self.assertFalse(target.exists())
            self.assertFalse(receipt.exists())

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            old_base = create_repo(repo)
            (repo / "README.md").write_text("next\n", encoding="utf-8")
            git(repo, "add", "README.md")
            git(repo, "commit", "-m", "next")
            target = temp / "mismatch-workspace"
            receipt = temp / "mismatch-receipt.json"
            result = preparer.prepare(repo, old_base, target, receipt, preparer.load_policy())
            self.assertIn("source_head_match", [item["rule"] for item in result["failures"]])
            self.assertFalse(target.exists())
            self.assertFalse(receipt.exists())

    def test_rejects_internal_existing_and_invalid_paths_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            base = create_repo(repo)
            existing = temp / "existing"
            existing.mkdir()
            cases = [
                (repo / "inside", temp / "a.json", "outside the source"),
                (existing, temp / "b.json", "already exists"),
                (temp / "target", repo / "inside.json", "outside the source"),
                (temp / "target", temp / "target" / "inside.json", "outside the target"),
            ]
            for target, receipt, expected in cases:
                with self.subTest(expected=expected), self.assertRaisesRegex(ValueError, expected):
                    preparer.prepare(repo, base, target, receipt, preparer.load_policy())
            self.assertEqual(1, len(git(repo, "worktree", "list", "--porcelain").split("worktree ")) - 1)

    def test_receipt_failure_rolls_back_created_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            base = create_repo(repo)
            target = temp / "workspace"
            receipt = temp / "receipt.json"

            def failing_writer(_path: Path, _content: bytes) -> None:
                raise OSError("fixture receipt failure")

            with self.assertRaisesRegex(ValueError, "rollback succeeded"):
                preparer.prepare(
                    repo,
                    base,
                    target,
                    receipt,
                    preparer.load_policy(),
                    writer=failing_writer,
                )

            self.assertFalse(target.exists())
            self.assertFalse(receipt.exists())
            self.assertEqual(1, len(git(repo, "worktree", "list", "--porcelain").split("worktree ")) - 1)

    def test_failed_postcondition_rolls_back_created_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            base = create_repo(repo)
            target = temp / "workspace"
            receipt = temp / "receipt.json"
            original = preparer.workspace_snapshot
            changed = False

            def invalid_snapshot(workspace: Path, timeout: int) -> dict[str, object]:
                nonlocal changed
                value = original(workspace, timeout)
                if not changed:
                    value["detached"] = False
                    changed = True
                return value

            with mock.patch.object(
                preparer,
                "workspace_snapshot",
                side_effect=invalid_snapshot,
            ), self.assertRaisesRegex(ValueError, "rollback succeeded"):
                preparer.prepare(repo, base, target, receipt, preparer.load_policy())

            self.assertFalse(target.exists())
            self.assertFalse(receipt.exists())
            self.assertEqual(1, len(git(repo, "worktree", "list", "--porcelain").split("worktree ")) - 1)

    def test_git_wrapper_uses_no_shell_timeout_and_bounded_environment(self) -> None:
        invocation: dict[str, object] = {}

        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            invocation["command"] = command
            invocation.update(kwargs)
            return subprocess.CompletedProcess(command, 0, stdout=b"ok", stderr=b"")

        returncode, output = preparer.run_git(
            REPO_ROOT,
            15,
            "status",
            "--short",
            runner=runner,
        )

        self.assertEqual(0, returncode)
        self.assertEqual(b"ok", output)
        self.assertIs(False, invocation["shell"])
        self.assertEqual(15, invocation["timeout"])
        self.assertEqual("0", invocation["env"]["GIT_OPTIONAL_LOCKS"])

    def test_policy_drift_cli_override_and_invalid_base_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            path = temp / "policy.json"
            policy = json.loads(json.dumps(preparer.EXPECTED_POLICY))
            policy["rollback_on_failure"] = False
            path.write_text(json.dumps(policy), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "pilot contract"):
                preparer.load_policy(path)

            repo = temp / "repo"
            create_repo(repo)
            with self.assertRaisesRegex(ValueError, "40 lowercase"):
                preparer.prepare(
                    repo,
                    "HEAD",
                    temp / "workspace",
                    temp / "receipt.json",
                    preparer.load_policy(),
                )

        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--repo",
                str(REPO_ROOT),
                "--base",
                "0" * 40,
                "--target",
                str(REPO_ROOT.parent / "workspace"),
                "--receipt",
                str(REPO_ROOT.parent / "receipt.json"),
                "--policy",
                "untrusted.json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, completed.returncode)
        self.assertIn("unrecognized arguments", completed.stderr)

    def test_real_cli_prepares_without_authorizing_use(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            base = create_repo(repo)
            target = temp / "workspace"
            receipt = temp / "receipt.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--repo",
                    str(repo),
                    "--base",
                    base,
                    "--target",
                    str(target),
                    "--receipt",
                    str(receipt),
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            result = json.loads(completed.stdout)

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertTrue(result["prepared"])
            self.assertFalse(result["workspace_use_authorized"])
            self.assertFalse(result["agent_invocation_authorized"])
            cleanup(repo, target)


if __name__ == "__main__":
    unittest.main()
