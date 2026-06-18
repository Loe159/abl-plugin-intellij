from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "validate_implementation_session_approval.py"
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location("validate_implementation_session_approval", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)
import test_approve_implementation_session as approval_helpers
import test_build_implementation_session as implementation_helpers
import test_validate_implementation_session as proposal_helpers


def prepare(temp: Path) -> tuple[Path, Path, str, Path, Path, str, Path, str]:
    repo, proposal, digest, workspace, worktree_receipt, worktree_digest = (
        proposal_helpers.prepare(temp)
    )
    approval_receipt = temp / "session-approval.json"
    policies = validator.load_policies()
    assessment = validator.approve_implementation_session.assess_approval(
        repo,
        proposal,
        digest,
        workspace,
        worktree_receipt,
        worktree_digest,
        approval_receipt,
        policies,
        approval_helpers.ready_runner,
    )
    result = validator.approve_implementation_session.approve(
        argparse.Namespace(
            repo=repo,
            proposal=proposal,
            proposal_sha256=digest,
            workspace=workspace,
            worktree_receipt=worktree_receipt,
            worktree_receipt_sha256=worktree_digest,
            approval_receipt=approval_receipt,
            approver="local-reviewer",
            confirm=assessment["required_confirmation"],
        ),
        policies,
        assessment,
        approval_helpers.ready_runner,
    )
    assert result["session_proposal_approved"], result
    return (
        repo,
        proposal,
        digest,
        workspace,
        worktree_receipt,
        worktree_digest,
        approval_receipt,
        result["approval_receipt_sha256"],
    )


def cli(
    repo: Path,
    proposal: Path,
    digest: str,
    workspace: Path,
    worktree_receipt: Path,
    worktree_digest: str,
    approval_receipt: Path,
    approval_digest: str,
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
            "--format",
            "json",
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


class ValidateImplementationSessionApprovalTest(unittest.TestCase):
    def test_policy_is_exact_and_non_authorizing(self) -> None:
        policy = validator.load_policy()
        self.assertEqual("validation-only", policy["mode"])
        self.assertTrue(policy["require_valid_proposal"])
        self.assertTrue(policy["require_runner_controls_ready"])
        self.assertIn(
            ".agent/checks/validate_implementation_session_approval.py",
            policy["validator_bindings"],
        )

    def test_valid_receipt_is_accepted_without_authorization_or_start(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest, receipt, receipt_digest = (
                prepare(temp)
            )
            before = implementation_helpers.git(
                repo,
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            )
            result = validator.validate(
                repo,
                proposal,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                receipt,
                receipt_digest,
                validator.load_policies(),
                approval_helpers.ready_runner,
            )
            after = implementation_helpers.git(
                repo,
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            )

        self.assertTrue(result["valid"], result["failures"])
        self.assertEqual(before, after)
        self.assertTrue(result["session_proposal_approved"])
        for field in validator.FALSE_AUTHORIZATION_FIELDS:
            self.assertFalse(result[field])

    def test_unready_current_runner_controls_invalidate_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest, receipt, receipt_digest = (
                prepare(temp)
            )
            result = validator.validate(
                repo,
                proposal,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                receipt,
                receipt_digest,
                validator.load_policies(),
                approval_helpers.unready_runner,
            )

        self.assertFalse(result["valid"])
        self.assertIn("runner_controls_ready", [item["rule"] for item in result["failures"]])

    def test_wrong_digest_and_rehashed_receipt_tampering_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest, receipt, receipt_digest = (
                prepare(temp)
            )
            wrong = validator.validate(
                repo,
                proposal,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                receipt,
                "0" * 64,
                validator.load_policies(),
                approval_helpers.ready_runner,
            )
            value = json.loads(receipt.read_text(encoding="utf-8"))
            value["session_start_authorized"] = True
            receipt.write_text(json.dumps(value), encoding="utf-8")
            tampered = validator.validate(
                repo,
                proposal,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                receipt,
                validator.approve_implementation_session.sha256_bytes(receipt.read_bytes()),
                validator.load_policies(),
                approval_helpers.ready_runner,
            )

        self.assertEqual("receipt_sha256", wrong["failures"][0]["rule"])
        self.assertIn("receipt_metadata", [item["rule"] for item in tampered["failures"]])

    def test_rehashed_identity_binding_and_proposal_drift_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest, receipt, receipt_digest = (
                prepare(temp)
            )
            value = json.loads(receipt.read_text(encoding="utf-8"))
            value["proposal_sha256"] = "0" * 64
            receipt.write_text(json.dumps(value), encoding="utf-8")
            identity = validator.validate(
                repo,
                proposal,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                receipt,
                validator.approve_implementation_session.sha256_bytes(receipt.read_bytes()),
                validator.load_policies(),
                approval_helpers.ready_runner,
            )
            value = json.loads(receipt.read_text(encoding="utf-8"))
            value["bindings"][0]["sha256"] = "0" * 64
            receipt.write_text(json.dumps(value), encoding="utf-8")
            binding = validator.validate(
                repo,
                proposal,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                receipt,
                validator.approve_implementation_session.sha256_bytes(receipt.read_bytes()),
                validator.load_policies(),
                approval_helpers.ready_runner,
            )

        self.assertIn("receipt_identity", [item["rule"] for item in identity["failures"]])
        self.assertIn("trusted_binding_mismatch", [item["rule"] for item in binding["failures"]])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest, receipt, receipt_digest = (
                prepare(temp)
            )
            proposal.write_text(proposal.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            drift = validator.validate(
                repo,
                proposal,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                receipt,
                receipt_digest,
                validator.load_policies(),
                approval_helpers.ready_runner,
            )
        self.assertIn("proposal_validation", [item["rule"] for item in drift["failures"]])

    def test_cli_refuses_policy_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest, receipt, receipt_digest = (
                prepare(temp)
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
                "--approval-policy",
                "untrusted",
            )

        self.assertEqual(2, completed.returncode)
        self.assertIn("unrecognized arguments", completed.stderr)


if __name__ == "__main__":
    unittest.main()
