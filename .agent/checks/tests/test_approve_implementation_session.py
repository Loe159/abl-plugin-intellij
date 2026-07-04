from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "approve_implementation_session.py"
REPO_ROOT = CHECKS_DIR.parents[1]
POLICY_DIR = REPO_ROOT / ".agent" / "policies"
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location("approve_implementation_session", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
approval = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = approval
SPEC.loader.exec_module(approval)
import test_validate_implementation_session as proposal_helpers


def ready_runner(repo: Path, policy: dict[str, object]) -> dict[str, object]:
    controls = []
    for control in policy["required_runtime_controls"]:
        evidence = policy["satisfaction_rules"][control][0]
        controls.append(
            {
                "id": control,
                "status": "satisfied",
                "satisfaction_evidence": [evidence],
                "related_evidence": [],
            }
        )
    return {
        "assessment_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        "authorized": False,
        "agent_invocation_authorized": False,
        "implementation_authorized": False,
        "runner_selected": False,
        "session_start_authorized": False,
        "assessment_complete": True,
        "controls_ready": True,
        "repo_unchanged": True,
        "controls": controls,
        "evidence_sources": [],
        "policy_bindings": approval.assess_runner_readiness.binding_records(
            REPO_ROOT,
            policy["policy_bindings"],
        ),
    }


def unready_runner(repo: Path, policy: dict[str, object]) -> dict[str, object]:
    result = ready_runner(repo, policy)
    result["controls_ready"] = False
    for control in result["controls"]:
        control["status"] = "missing_evidence"
        control["satisfaction_evidence"] = []
    return result


def cli(
    repo: Path,
    proposal: Path,
    digest: str,
    workspace: Path,
    worktree_receipt: Path,
    worktree_digest: str,
    approval_receipt: Path,
    *extra: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "check",
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
            "--format",
            "json",
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


class ApproveImplementationSessionTest(unittest.TestCase):
    def test_policy_is_exact_and_non_authorizing(self) -> None:
        policy = approval.load_policy()
        self.assertEqual("exact-local-approval-only", policy["mode"])
        self.assertTrue(policy["require_valid_proposal"])
        self.assertFalse(policy["require_runner_controls_ready"])
        self.assertIn(".agent/checks/validate_implementation_session.py", policy["bindings"])

    def test_unready_runner_controls_are_recorded_without_blocking_pilot_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest = (
                proposal_helpers.prepare(temp)
            )
            receipt = temp / "session-approval.json"
            result = approval.assess_approval(
                repo,
                proposal,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                receipt,
                approval.load_policies(),
                unready_runner,
            )

        self.assertTrue(result["approvable"], result["failures"])
        self.assertFalse(result["runner_controls_ready"])
        self.assertFalse(receipt.exists())
        self.assertNotIn("runner_controls_ready", [item["rule"] for item in result["failures"]])

    def test_exact_approval_writes_external_receipt_without_authorizing_start(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest = (
                proposal_helpers.prepare(temp)
            )
            receipt = temp / "session-approval.json"
            policies = approval.load_policies()
            assessment = approval.assess_approval(
                repo,
                proposal,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                receipt,
                policies,
                ready_runner,
            )
            result = approval.approve(
                argparse.Namespace(
                    repo=repo,
                    proposal=proposal,
                    proposal_sha256=digest,
                    workspace=workspace,
                    worktree_receipt=worktree_receipt,
                    worktree_receipt_sha256=worktree_digest,
                    approval_receipt=receipt,
                    approver="local-reviewer",
                    confirm=assessment["required_confirmation"],
                ),
                policies,
                assessment,
                ready_runner,
            )
            value = json.loads(receipt.read_text(encoding="utf-8"))

        self.assertTrue(assessment["approvable"], assessment["failures"])
        self.assertTrue(result["session_proposal_approved"], result["failures"])
        self.assertTrue(result["receipt_written"])
        self.assertEqual(digest, value["proposal_sha256"])
        self.assertEqual(worktree_digest, value["worktree_receipt_sha256"])
        for field in approval.FALSE_AUTHORIZATION_FIELDS:
            self.assertFalse(value[field])

    def test_confirmation_mismatch_existing_receipt_and_dirty_proposal_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest = (
                proposal_helpers.prepare(temp)
            )
            receipt = temp / "session-approval.json"
            policies = approval.load_policies()
            assessment = approval.assess_approval(
                repo,
                proposal,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                receipt,
                policies,
                ready_runner,
            )
            mismatch = approval.approve(
                argparse.Namespace(
                    repo=repo,
                    proposal=proposal,
                    proposal_sha256=digest,
                    workspace=workspace,
                    worktree_receipt=worktree_receipt,
                    worktree_receipt_sha256=worktree_digest,
                    approval_receipt=receipt,
                    approver="local-reviewer",
                    confirm="wrong",
                ),
                policies,
                assessment,
                ready_runner,
            )
            receipt.write_text("existing", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already exists"):
                approval.assess_approval(
                    repo,
                    proposal,
                    digest,
                    workspace,
                    worktree_receipt,
                    worktree_digest,
                    receipt,
                    policies,
                    ready_runner,
                )

        self.assertFalse(mismatch["approvable"])
        self.assertIn("confirmation_mismatch", [item["rule"] for item in mismatch["failures"]])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest = (
                proposal_helpers.prepare(temp)
            )
            value = json.loads(proposal.read_text(encoding="utf-8"))
            value["session_start_authorized"] = True
            proposal.write_text(json.dumps(value), encoding="utf-8")
            result = approval.assess_approval(
                repo,
                proposal,
                approval.sha256_bytes(proposal.read_bytes()),
                workspace,
                worktree_receipt,
                worktree_digest,
                temp / "session-approval.json",
                approval.load_policies(),
                ready_runner,
            )
        self.assertFalse(result["approvable"])
        self.assertIn("proposal_validation", [item["rule"] for item in result["failures"]])

    def test_cli_refuses_policy_override_and_reports_not_approvable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest = (
                proposal_helpers.prepare(temp)
            )
            receipt = temp / "session-approval.json"
            completed = cli(
                repo,
                proposal,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                receipt,
                "--session-policy",
                "untrusted",
            )

        self.assertEqual(2, completed.returncode)
        self.assertIn("unrecognized arguments", completed.stderr)


if __name__ == "__main__":
    unittest.main()
