from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "check_implementation_runner_selection.py"
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location(
    "check_implementation_runner_selection",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
selection = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = selection
SPEC.loader.exec_module(selection)
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


class CheckImplementationRunnerSelectionTest(unittest.TestCase):
    def test_policy_is_exact_and_non_authorizing(self) -> None:
        policy = selection.load_policy()
        self.assertEqual("runner-selection-readiness-only", policy["mode"])
        self.assertTrue(policy["candidate_runner"]["requires_valid_preflight"])
        self.assertFalse(policy["candidate_runner"]["requires_runner_controls_ready"])
        self.assertIn(
            ".agent/checks/validate_implementation_invocation_preflight.py",
            policy["bindings"],
        )

    def test_valid_preflight_makes_runner_selection_ready_without_selecting(self) -> None:
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
            result = selection.check_selection(
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
                selection.load_policies(),
                approval_helpers.ready_runner,
            )
            after = implementation_helpers.git(
                repo,
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            )

        self.assertEqual(before, after)
        self.assertTrue(result["preflight_valid"], result["failures"])
        self.assertTrue(result["runner_selection_ready"], result["failures"])
        self.assertEqual("codex-cli-disposable-worktree", result["candidate_runner"]["id"])
        self.assertEqual([], result["failures"])
        for field in selection.FALSE_AUTHORIZATION_FIELDS:
            self.assertFalse(result[field])

    def test_invalid_preflight_and_stale_runner_readiness_block_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest, receipt, receipt_digest, preflight, preflight_digest = (
                preflight_helpers.prepare(temp)
            )
            invalid_preflight = selection.check_selection(
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
                selection.load_policies(),
                approval_helpers.ready_runner,
            )
            unready = selection.check_selection(
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
                selection.load_policies(),
                approval_helpers.unready_runner,
            )

        self.assertFalse(invalid_preflight["runner_selection_ready"])
        self.assertIn("preflight_validation", [item["rule"] for item in invalid_preflight["failures"]])
        self.assertFalse(unready["runner_selection_ready"])
        self.assertIn("preflight_validation", [item["rule"] for item in unready["failures"]])

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
                "--runner-selection-policy",
                "untrusted",
            )

        self.assertEqual(2, completed.returncode)
        self.assertIn("unrecognized arguments", completed.stderr)


if __name__ == "__main__":
    unittest.main()
