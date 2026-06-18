from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "check_implementation_invocation_readiness.py"
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location(
    "check_implementation_invocation_readiness",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
readiness = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = readiness
SPEC.loader.exec_module(readiness)
import test_approve_implementation_session as approval_helpers
import test_authorize_implementation_session_start as authorization_helpers
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


class CheckImplementationInvocationReadinessTest(unittest.TestCase):
    def test_policy_is_exact_and_non_authorizing(self) -> None:
        policy = readiness.load_policy()
        self.assertEqual("readiness-check-only", policy["mode"])
        self.assertTrue(policy["runner_selection_gate_available"])
        self.assertTrue(policy["session_start_gate_available"])
        self.assertTrue(policy["explicit_start_authorization_available"])
        self.assertIn(
            ".agent/checks/check_implementation_session_start.py",
            policy["bindings"],
        )
        self.assertIn(
            ".agent/checks/validate_implementation_invocation_preflight.py",
            policy["bindings"],
        )

    def test_valid_preflight_has_start_gate_but_still_needs_start_authorization(self) -> None:
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
            result = readiness.check_readiness(
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
                readiness.load_policies(),
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
        self.assertTrue(result["session_start_ready"], result["failures"])
        self.assertFalse(result["invocation_ready"])
        self.assertEqual(["session_start_authorization_gate"], result["missing_gates"])
        self.assertEqual(["session_start_authorization"], result["missing_authorizations"])
        for field in readiness.FALSE_AUTHORIZATION_FIELDS:
            self.assertFalse(result[field])

    def test_invalid_preflight_is_not_invocation_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest, receipt, receipt_digest, preflight, preflight_digest = (
                preflight_helpers.prepare(temp)
            )
            result = readiness.check_readiness(
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
                readiness.load_policies(),
                approval_helpers.ready_runner,
            )

        self.assertFalse(result["preflight_valid"])
        self.assertFalse(result["runner_selection_ready"])
        self.assertFalse(result["invocation_ready"])
        self.assertIn("preflight_validation", [item["rule"] for item in result["failures"]])

    def test_valid_exact_start_authorization_makes_readiness_reachable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            (
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
                authorization_receipt,
                authorization_digest,
            ) = authorization_helpers.write_authorization(Path(temp_dir))
            result = readiness.check_readiness(
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
                readiness.load_policies(),
                approval_helpers.ready_runner,
                authorization_receipt,
                authorization_digest,
            )

        self.assertTrue(result["start_authorization_valid"], result["failures"])
        self.assertTrue(result["invocation_ready"], result["failures"])
        self.assertEqual([], result["missing_gates"])
        for field in readiness.FALSE_AUTHORIZATION_FIELDS:
            self.assertFalse(result[field])

    def test_unready_runner_controls_keep_invocation_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest, receipt, receipt_digest, preflight, preflight_digest = (
                preflight_helpers.prepare(temp)
            )
            result = readiness.check_readiness(
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
                readiness.load_policies(),
                approval_helpers.unready_runner,
            )

        self.assertFalse(result["preflight_valid"])
        self.assertFalse(result["runner_selection_ready"])
        self.assertFalse(result["invocation_ready"])
        self.assertIn("runner_selection_gate", [item["rule"] for item in result["failures"]])

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
                "--invocation-readiness-policy",
                "untrusted",
            )

        self.assertEqual(2, completed.returncode)
        self.assertIn("unrecognized arguments", completed.stderr)


if __name__ == "__main__":
    unittest.main()
