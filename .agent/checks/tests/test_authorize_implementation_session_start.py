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
MODULE_PATH = CHECKS_DIR / "authorize_implementation_session_start.py"
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location(
    "authorize_implementation_session_start",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
authorization = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = authorization
SPEC.loader.exec_module(authorization)
import test_approve_implementation_session as approval_helpers
import test_validate_implementation_invocation_preflight as preflight_helpers


def prepare(
    temp: Path,
) -> tuple[
    Path,
    Path,
    str,
    Path,
    Path,
    str,
    Path,
    str,
    Path,
    str,
    Path,
    dict[str, object],
]:
    (
        repo,
        proposal,
        proposal_digest,
        workspace,
        worktree_receipt,
        worktree_digest,
        approval_receipt,
        approval_digest,
        preflight,
        preflight_digest,
    ) = preflight_helpers.prepare(temp)
    authorization_receipt = temp / "session-start-authorization.json"
    policies = authorization.load_policies()
    assessment = authorization.assess_authorization(
        repo,
        proposal,
        proposal_digest,
        workspace,
        worktree_receipt,
        worktree_digest,
        approval_receipt,
        approval_digest,
        preflight,
        preflight_digest,
        authorization_receipt,
        policies,
        approval_helpers.ready_runner,
    )
    return (
        repo,
        proposal,
        proposal_digest,
        workspace,
        worktree_receipt,
        worktree_digest,
        approval_receipt,
        approval_digest,
        preflight,
        preflight_digest,
        authorization_receipt,
        assessment,
    )


def write_authorization(
    temp: Path,
) -> tuple[
    Path,
    Path,
    str,
    Path,
    Path,
    str,
    Path,
    str,
    Path,
    str,
    Path,
    str,
]:
    (
        repo,
        proposal,
        proposal_digest,
        workspace,
        worktree_receipt,
        worktree_digest,
        approval_receipt,
        approval_digest,
        preflight,
        preflight_digest,
        authorization_receipt,
        assessment,
    ) = prepare(temp)
    result = authorization.authorize(
        argparse.Namespace(
            repo=repo,
            proposal=proposal,
            proposal_sha256=proposal_digest,
            workspace=workspace,
            worktree_receipt=worktree_receipt,
            worktree_receipt_sha256=worktree_digest,
            approval_receipt=approval_receipt,
            approval_receipt_sha256=approval_digest,
            preflight=preflight,
            preflight_sha256=preflight_digest,
            authorization_receipt=authorization_receipt,
            authorizer="local-reviewer",
            confirm=assessment["required_confirmation"],
        ),
        authorization.load_policies(),
        assessment,
        approval_helpers.ready_runner,
    )
    assert result["receipt_written"], result
    return (
        repo,
        proposal,
        proposal_digest,
        workspace,
        worktree_receipt,
        worktree_digest,
        approval_receipt,
        approval_digest,
        preflight,
        preflight_digest,
        authorization_receipt,
        result["authorization_receipt_sha256"],
    )


class AuthorizeImplementationSessionStartTest(unittest.TestCase):
    def test_policy_is_exact_and_does_not_overclaim_runtime_enforcement(self) -> None:
        policy = authorization.load_policy()

        self.assertEqual("exact-local-start-authorization-only", policy["mode"])
        self.assertTrue(policy["require_session_start_ready"])
        self.assertFalse(policy["replay_prevention_enforced"])
        self.assertIn(
            ".agent/checks/check_implementation_session_start.py",
            policy["bindings"],
        )

    def test_unready_runner_controls_block_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            (
                repo,
                proposal,
                proposal_digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                approval_receipt,
                approval_digest,
                preflight,
                preflight_digest,
            ) = preflight_helpers.prepare(temp)
            result = authorization.assess_authorization(
                repo,
                proposal,
                proposal_digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                approval_receipt,
                approval_digest,
                preflight,
                preflight_digest,
                temp / "authorization.json",
                authorization.load_policies(),
                approval_helpers.unready_runner,
            )

        self.assertFalse(result["authorizable"])
        self.assertIn(
            "session_start_readiness",
            [item["rule"] for item in result["failures"]],
        )

    def test_exact_authorization_writes_bounded_receipt_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            (
                _repo,
                _proposal,
                _proposal_digest,
                _workspace,
                _worktree_receipt,
                _worktree_digest,
                _approval_receipt,
                _approval_digest,
                _preflight,
                _preflight_digest,
                receipt,
                receipt_digest,
            ) = write_authorization(Path(temp_dir))
            value = json.loads(receipt.read_text(encoding="utf-8"))

        self.assertRegex(receipt_digest, r"^[0-9a-f]{64}$")
        self.assertTrue(value["session_start_authorized"])
        self.assertFalse(value["authorizer_authenticated"])
        self.assertFalse(value["replay_prevention_enforced"])
        for field in authorization.FALSE_FIELDS:
            self.assertFalse(value[field])

    def test_confirmation_mismatch_and_existing_receipt_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            (
                repo,
                proposal,
                proposal_digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                approval_receipt,
                approval_digest,
                preflight,
                preflight_digest,
                receipt,
                assessment,
            ) = prepare(temp)
            mismatch = authorization.authorize(
                argparse.Namespace(
                    repo=repo,
                    proposal=proposal,
                    proposal_sha256=proposal_digest,
                    workspace=workspace,
                    worktree_receipt=worktree_receipt,
                    worktree_receipt_sha256=worktree_digest,
                    approval_receipt=approval_receipt,
                    approval_receipt_sha256=approval_digest,
                    preflight=preflight,
                    preflight_sha256=preflight_digest,
                    authorization_receipt=receipt,
                    authorizer="local-reviewer",
                    confirm="wrong",
                ),
                authorization.load_policies(),
                assessment,
                approval_helpers.ready_runner,
            )
            receipt.write_text("existing", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already exists"):
                authorization.assess_authorization(
                    repo,
                    proposal,
                    proposal_digest,
                    workspace,
                    worktree_receipt,
                    worktree_digest,
                    approval_receipt,
                    approval_digest,
                    preflight,
                    preflight_digest,
                    receipt,
                    authorization.load_policies(),
                    approval_helpers.ready_runner,
                )

        self.assertFalse(mismatch["authorizable"])
        self.assertIn(
            "confirmation_mismatch",
            [item["rule"] for item in mismatch["failures"]],
        )

    def test_cli_refuses_policy_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            (
                repo,
                proposal,
                proposal_digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                approval_receipt,
                approval_digest,
                preflight,
                preflight_digest,
                receipt,
                _assessment,
            ) = prepare(temp)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "check",
                    "--repo",
                    str(repo),
                    "--proposal",
                    str(proposal),
                    "--proposal-sha256",
                    proposal_digest,
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
                    "--authorization-receipt",
                    str(receipt),
                    "--authorization-policy",
                    "untrusted",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(2, completed.returncode)
        self.assertIn("unrecognized arguments", completed.stderr)


if __name__ == "__main__":
    unittest.main()
