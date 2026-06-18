from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "build_implementation_invocation_preflight.py"
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location(
    "build_implementation_invocation_preflight",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
preflight = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = preflight
SPEC.loader.exec_module(preflight)
import test_approve_implementation_session as approval_helpers
import test_build_implementation_session as implementation_helpers
import test_validate_implementation_session_approval as validation_helpers


def cli(
    repo: Path,
    proposal: Path,
    digest: str,
    workspace: Path,
    worktree_receipt: Path,
    worktree_digest: str,
    approval_receipt: Path,
    approval_digest: str,
    output: Path,
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
            "--output",
            str(output),
            "--format",
            "json",
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


class BuildImplementationInvocationPreflightTest(unittest.TestCase):
    def test_policy_is_exact_and_non_authorizing(self) -> None:
        policy = preflight.load_policy()
        self.assertEqual("preflight-only", policy["mode"])
        self.assertTrue(policy["require_valid_approval_validation"])
        self.assertTrue(policy["require_external_output"])
        self.assertIn(
            ".agent/checks/validate_implementation_session_approval.py",
            policy["policy_bindings"],
        )

    def test_valid_approval_validation_builds_preflight_without_starting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest, receipt, receipt_digest = (
                validation_helpers.prepare(temp)
            )
            output = temp / "implementation-invocation-preflight.json"
            before = implementation_helpers.git(
                repo,
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            )
            result = preflight.build_preflight(
                repo,
                proposal,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                receipt,
                receipt_digest,
                output,
                preflight.load_policies(),
                approval_helpers.ready_runner,
            )
            after = implementation_helpers.git(
                repo,
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            )
            value = json.loads(output.read_text(encoding="utf-8"))

        self.assertTrue(result["produced"], result["failures"])
        self.assertTrue(result["preflight_passed"])
        self.assertEqual(before, after)
        self.assertEqual(digest, value["proposal"]["sha256"])
        self.assertEqual(receipt_digest, value["approval_receipt"]["sha256"])
        self.assertFalse(value["runner_selection"]["authorized"])
        self.assertFalse(value["session_start"]["authorized"])
        for field in preflight.FALSE_AUTHORIZATION_FIELDS:
            self.assertFalse(value[field])

    def test_invalid_approval_validation_blocks_preflight_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest, receipt, receipt_digest = (
                validation_helpers.prepare(temp)
            )
            output = temp / "implementation-invocation-preflight.json"
            result = preflight.build_preflight(
                repo,
                proposal,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                receipt,
                receipt_digest,
                output,
                preflight.load_policies(),
                approval_helpers.unready_runner,
            )

        self.assertFalse(result["produced"])
        self.assertFalse(output.exists())
        self.assertIn("approval_validation", [item["rule"] for item in result["failures"]])

    def test_tampered_proposal_digest_blocks_preflight_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest, receipt, receipt_digest = (
                validation_helpers.prepare(temp)
            )
            output = temp / "implementation-invocation-preflight.json"
            result = preflight.build_preflight(
                repo,
                proposal,
                "0" * 64,
                workspace,
                worktree_receipt,
                worktree_digest,
                receipt,
                receipt_digest,
                output,
                preflight.load_policies(),
                approval_helpers.ready_runner,
            )

        self.assertFalse(result["produced"])
        self.assertFalse(output.exists())
        self.assertIn("approval_validation", [item["rule"] for item in result["failures"]])

    def test_cli_refuses_policy_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest, receipt, receipt_digest = (
                validation_helpers.prepare(temp)
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
                temp / "implementation-invocation-preflight.json",
                "--preflight-policy",
                "untrusted",
            )

        self.assertEqual(2, completed.returncode)
        self.assertIn("unrecognized arguments", completed.stderr)


if __name__ == "__main__":
    unittest.main()
