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
MODULE_PATH = CHECKS_DIR / "cleanup_disposable_worktree.py"
REPO_ROOT = CHECKS_DIR.parents[1]
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location("cleanup_disposable_worktree", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
cleaner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cleaner
SPEC.loader.exec_module(cleaner)
import test_validate_disposable_worktree as validation_helpers


def prepare(temp: Path) -> tuple[Path, Path, Path, str]:
    return validation_helpers.prepare(temp)


def run_cleanup(
    source: Path,
    workspace: Path,
    receipt: Path,
    digest: str,
    cleanup_receipt: Path,
    confirmation: str | None = None,
) -> dict[str, object]:
    return cleaner.cleanup(
        source,
        workspace,
        receipt,
        digest,
        cleanup_receipt,
        str(workspace.resolve()) if confirmation is None else confirmation,
        cleaner.load_policy(),
    )


class CleanupDisposableWorktreeTest(unittest.TestCase):
    def test_repository_policy_is_exact_destructive_cleanup_only(self) -> None:
        policy = cleaner.load_policy()

        self.assertEqual(cleaner.EXPECTED_POLICY, policy)
        self.assertEqual("destructive-cleanup-only", policy["mode"])
        self.assertTrue(policy["allow_dirty_workspace"])
        self.assertTrue(policy["require_exact_workspace_confirmation"])
        self.assertNotIn("codex", json.dumps(policy).lower())

    def test_real_dirty_cleanup_removes_only_workspace_and_writes_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source, workspace, receipt, digest = prepare(temp)
            cleanup_receipt = temp / "cleanup.json"
            before_source = cleaner.prepare_disposable_worktree.source_snapshot(source, 15)
            original_receipt = receipt.read_bytes()
            (workspace / "dirty.txt").write_text("discard me\n", encoding="utf-8")

            result = run_cleanup(source, workspace, receipt, digest, cleanup_receipt)
            value = json.loads(cleanup_receipt.read_text(encoding="utf-8"))
            after_source = cleaner.prepare_disposable_worktree.source_snapshot(source, 15)

            self.assertTrue(result["cleaned"], result["failures"])
            self.assertTrue(result["discarded_uncommitted_changes"])
            self.assertFalse(workspace.exists())
            self.assertEqual(original_receipt, receipt.read_bytes())
            self.assertEqual(before_source["head"], after_source["head"])
            self.assertEqual(before_source["branches"], after_source["branches"])
            self.assertEqual(before_source["status"], after_source["status"])
            self.assertTrue(value["cleanup_performed"])
            self.assertTrue(value["postconditions"]["workspace_registration_removed"])
            for field in cleaner.FALSE_FIELDS:
                self.assertFalse(value[field])

    def test_wrong_confirmation_digest_or_rehashed_identity_never_removes_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source, workspace, receipt, digest = prepare(temp)
            result = run_cleanup(
                source,
                workspace,
                receipt,
                digest,
                temp / "cleanup.json",
                confirmation="wrong",
            )
            self.assertIn("workspace_confirmation", [item["rule"] for item in result["failures"]])
            self.assertTrue(workspace.exists())
            validation_helpers.cleanup(source, workspace)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source, workspace, receipt, _digest = prepare(temp)
            result = run_cleanup(source, workspace, receipt, "0" * 64, temp / "cleanup.json")
            self.assertIn("receipt_sha256", [item["rule"] for item in result["failures"]])
            self.assertTrue(workspace.exists())
            validation_helpers.cleanup(source, workspace)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source, workspace, receipt, _digest = prepare(temp)
            value = json.loads(receipt.read_text(encoding="utf-8"))
            value["workspace"] = str(temp / "other")
            receipt.write_text(json.dumps(value), encoding="utf-8")
            digest = cleaner.validate_disposable_worktree.sha256_bytes(receipt.read_bytes())
            result = run_cleanup(source, workspace, receipt, digest, temp / "cleanup.json")
            self.assertIn("receipt_identity", [item["rule"] for item in result["failures"]])
            self.assertTrue(workspace.exists())
            validation_helpers.cleanup(source, workspace)

    def test_branched_or_committed_workspace_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source, workspace, receipt, digest = prepare(temp)
            validation_helpers.helpers.git(workspace, "switch", "-c", "unexpected")
            result = run_cleanup(source, workspace, receipt, digest, temp / "cleanup.json")
            self.assertIn("workspace_detached", [item["rule"] for item in result["failures"]])
            self.assertTrue(workspace.exists())
            validation_helpers.cleanup(source, workspace)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source, workspace, receipt, digest = prepare(temp)
            validation_helpers.helpers.git(workspace, "config", "user.email", "tests@example.invalid")
            validation_helpers.helpers.git(workspace, "config", "user.name", "Tests")
            (workspace / "README.md").write_text("commit\n", encoding="utf-8")
            validation_helpers.helpers.git(workspace, "add", "README.md")
            validation_helpers.helpers.git(workspace, "commit", "-m", "detached commit")
            result = run_cleanup(source, workspace, receipt, digest, temp / "cleanup.json")
            self.assertIn("workspace_head_match", [item["rule"] for item in result["failures"]])
            self.assertTrue(workspace.exists())
            validation_helpers.cleanup(source, workspace)

    def test_dirty_source_and_unregistered_clone_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source, workspace, receipt, digest = prepare(temp)
            (source / "dirty.txt").write_text("dirty\n", encoding="utf-8")
            result = run_cleanup(source, workspace, receipt, digest, temp / "cleanup.json")
            self.assertIn("source_clean", [item["rule"] for item in result["failures"]])
            self.assertTrue(workspace.exists())
            (source / "dirty.txt").unlink()
            validation_helpers.cleanup(source, workspace)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source, workspace, receipt, digest = prepare(temp)
            base = validation_helpers.helpers.git(source, "rev-parse", "HEAD")
            validation_helpers.helpers.git(source, "worktree", "remove", "--force", str(workspace))
            subprocess.run(
                ["git", "clone", "--no-checkout", str(source), str(workspace)],
                check=True,
                capture_output=True,
            )
            validation_helpers.helpers.git(workspace, "checkout", "--detach", base)
            result = run_cleanup(source, workspace, receipt, digest, temp / "cleanup.json")
            self.assertIn("workspace_registered", [item["rule"] for item in result["failures"]])
            self.assertTrue(workspace.exists())

    def test_cleanup_receipt_path_protections_are_checked_before_removal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source, workspace, receipt, digest = prepare(temp)
            cases = [
                source / "cleanup.json",
                workspace / "cleanup.json",
                temp / "missing-parent" / "cleanup.json",
            ]
            existing = temp / "existing.json"
            existing.write_text("existing\n", encoding="utf-8")
            cases.append(existing)
            for path in cases:
                with self.subTest(path=path), self.assertRaises(ValueError):
                    run_cleanup(source, workspace, receipt, digest, path)
                self.assertTrue(workspace.exists())
            validation_helpers.cleanup(source, workspace)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source, workspace, receipt, digest = prepare(temp)
            inside_workspace = workspace / "preparation.json"
            inside_workspace.write_bytes(receipt.read_bytes())
            with self.assertRaisesRegex(ValueError, "Preparation receipt must be outside"):
                run_cleanup(source, workspace, inside_workspace, digest, temp / "cleanup.json")
            self.assertTrue(workspace.exists())
            validation_helpers.cleanup(source, workspace)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source, workspace, receipt, digest = prepare(temp)
            with self.assertRaisesRegex(ValueError, "workspace must be outside"):
                cleaner.cleanup(
                    source,
                    source,
                    receipt,
                    digest,
                    temp / "cleanup.json",
                    str(source.resolve()),
                    cleaner.load_policy(),
                )
            self.assertTrue(source.exists())
            self.assertTrue(workspace.exists())
            validation_helpers.cleanup(source, workspace)

    def test_state_drift_before_removal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source, workspace, receipt, digest = prepare(temp)
            original = cleaner.prepare_disposable_worktree.workspace_snapshot
            calls = 0

            def drifting_snapshot(path: Path, timeout: int) -> dict[str, object]:
                nonlocal calls
                value = original(path, timeout)
                calls += 1
                if calls == 2:
                    value["detached"] = False
                return value

            with mock.patch.object(
                cleaner.prepare_disposable_worktree,
                "workspace_snapshot",
                side_effect=drifting_snapshot,
            ):
                result = run_cleanup(source, workspace, receipt, digest, temp / "cleanup.json")

            self.assertIn("state_changed", [item["rule"] for item in result["failures"]])
            self.assertTrue(workspace.exists())
            validation_helpers.cleanup(source, workspace)

    def test_receipt_write_failure_reports_irreversible_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source, workspace, receipt, digest = prepare(temp)
            cleanup_receipt = temp / "cleanup.json"

            def failing_writer(_path: Path, _content: bytes) -> None:
                raise OSError("fixture failure")

            with self.assertRaisesRegex(ValueError, "Cleanup succeeded but cleanup receipt"):
                cleaner.cleanup(
                    source,
                    workspace,
                    receipt,
                    digest,
                    cleanup_receipt,
                    str(workspace.resolve()),
                    cleaner.load_policy(),
                    writer=failing_writer,
                )

            self.assertFalse(workspace.exists())
            self.assertFalse(cleanup_receipt.exists())
            self.assertTrue(receipt.exists())

    def test_policy_drift_cli_override_and_invalid_digest_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            path = temp / "policy.json"
            policy = json.loads(json.dumps(cleaner.EXPECTED_POLICY))
            policy["allow_dirty_workspace"] = False
            path.write_text(json.dumps(policy), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "pilot contract"):
                cleaner.load_policy(path)

            source, workspace, receipt, _digest = prepare(temp)
            with self.assertRaisesRegex(ValueError, "64 lowercase"):
                run_cleanup(source, workspace, receipt, "bad", temp / "cleanup.json")
            validation_helpers.cleanup(source, workspace)

        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--source",
                str(REPO_ROOT),
                "--workspace",
                str(REPO_ROOT),
                "--receipt",
                str(REPO_ROOT / "none.json"),
                "--receipt-sha256",
                "0" * 64,
                "--cleanup-receipt",
                str(REPO_ROOT / "cleanup.json"),
                "--confirm-workspace",
                str(REPO_ROOT),
                "--policy",
                "untrusted.json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, completed.returncode)
        self.assertIn("unrecognized arguments", completed.stderr)

    def test_real_cli_cleans_after_exact_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source, workspace, receipt, digest = prepare(temp)
            cleanup_receipt = temp / "cleanup.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--source",
                    str(source),
                    "--workspace",
                    str(workspace),
                    "--receipt",
                    str(receipt),
                    "--receipt-sha256",
                    digest,
                    "--cleanup-receipt",
                    str(cleanup_receipt),
                    "--confirm-workspace",
                    str(workspace.resolve()),
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            result = json.loads(completed.stdout)

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertTrue(result["cleaned"])
            self.assertFalse(result["agent_invocation_authorized"])
            self.assertFalse(workspace.exists())


if __name__ == "__main__":
    unittest.main()
