from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "check_implementation_session_start.py"
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location(
    "check_implementation_session_start",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
session_start = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = session_start
SPEC.loader.exec_module(session_start)
import test_approve_implementation_session as approval_helpers
import test_build_implementation_session as implementation_helpers
import test_validate_implementation_invocation_preflight as preflight_helpers


def cli(
    repo: Path,
    proposal: Path,
    digest: str,
    workspace: Path,
    worktree_receipt: Path,
    worktree_digest: str,
    approval_receipt: Path,
    approval_digest: str,
    preflight: Path,
    preflight_digest: str,
    *extra: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "--repo",
            str(repo),
            "--proposal",
            str(proposal),
            "--proposal-sha256",
            digest,
            "--workspace",
            str(workspace),
            "--worktree-receipt",
            str(worktree_receipt),
            "--worktree-receipt-sha256",
            worktree_digest,
            "--approval-receipt",
            str(approval_receipt),
            "--approval-receipt-sha256",
            approval_digest,
            "--preflight",
            str(preflight),
            "--preflight-sha256",
            preflight_digest,
            "--format",
            "json",
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


class CheckImplementationSessionStartTest(unittest.TestCase):
    def test_policy_is_exact_and_non_authorizing(self) -> None:
        policy = session_start.load_policy()
        self.assertEqual("session-start-readiness-only", policy["mode"])
        self.assertTrue(policy["require_runner_selection_ready"])
        self.assertTrue(policy["track_explicit_start_authorization"])
        self.assertTrue(policy["explicit_start_authorization_available"])
        self.assertIn(
            ".agent/checks/check_implementation_runner_selection.py",
            policy["bindings"],
        )

    def test_valid_selection_makes_session_start_ready_without_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest, receipt, receipt_digest, preflight, preflight_digest = (
                preflight_helpers.prepare(temp)
            )
            before = implementation_helpers.git(
                repo,
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            )
            result = session_start.check_start(
                repo,
                proposal,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                receipt,
                receipt_digest,
                preflight,
                preflight_digest,
                session_start.load_policies(),
                approval_helpers.ready_runner,
            )
            after = implementation_helpers.git(
                repo,
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            )

        self.assertEqual(before, after)
        self.assertTrue(result["runner_selection_ready"], result["failures"])
        self.assertTrue(result["session_start_ready"], result["failures"])
        self.assertEqual(["session_start_authorization"], result["missing_authorizations"])
        self.assertEqual([], result["failures"])
        for field in session_start.FALSE_AUTHORIZATION_FIELDS:
            self.assertFalse(result[field])

    def test_invalid_preflight_and_unready_runner_controls_block_session_start(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest, receipt, receipt_digest, preflight, preflight_digest = (
                preflight_helpers.prepare(temp)
            )
            invalid_preflight = session_start.check_start(
                repo,
                proposal,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                receipt,
                receipt_digest,
                preflight,
                "0" * 64,
                session_start.load_policies(),
                approval_helpers.ready_runner,
            )
            unready = session_start.check_start(
                repo,
                proposal,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                receipt,
                receipt_digest,
                preflight,
                preflight_digest,
                session_start.load_policies(),
                approval_helpers.unready_runner,
            )

        self.assertFalse(invalid_preflight["session_start_ready"])
        self.assertIn("runner_selection_gate", [item["rule"] for item in invalid_preflight["failures"]])
        self.assertFalse(unready["session_start_ready"])
        self.assertIn("runner_selection_gate", [item["rule"] for item in unready["failures"]])

    def test_cli_refuses_policy_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest, receipt, receipt_digest, preflight, preflight_digest = (
                preflight_helpers.prepare(temp)
            )
            completed = cli(
                repo,
                proposal,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                receipt,
                receipt_digest,
                preflight,
                preflight_digest,
                "--session-start-policy",
                "untrusted",
            )

        self.assertEqual(2, completed.returncode)
        self.assertIn("unrecognized arguments", completed.stderr)


if __name__ == "__main__":
    unittest.main()
