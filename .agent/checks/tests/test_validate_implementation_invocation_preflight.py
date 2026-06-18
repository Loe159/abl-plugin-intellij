from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "validate_implementation_invocation_preflight.py"
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location(
    "validate_implementation_invocation_preflight",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)
import test_approve_implementation_session as approval_helpers
import test_build_implementation_session as implementation_helpers
import test_validate_implementation_session_approval as validation_helpers


def prepare(temp: Path) -> tuple[Path, Path, str, Path, Path, str, Path, str, Path, str]:
    repo, proposal, digest, workspace, worktree_receipt, worktree_digest, receipt, receipt_digest = (
        validation_helpers.prepare(temp)
    )
    preflight = temp / "implementation-invocation-preflight.json"
    result = validator.build_implementation_invocation_preflight.build_preflight(
        repo,
        proposal,
        digest,
        workspace,
        worktree_receipt,
        worktree_digest,
        receipt,
        receipt_digest,
        preflight,
        validator.load_policies(),
        approval_helpers.ready_runner,
    )
    assert result["produced"], result
    return (
        repo,
        proposal,
        digest,
        workspace,
        worktree_receipt,
        worktree_digest,
        receipt,
        receipt_digest,
        preflight,
        result["sha256"],
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


class ValidateImplementationInvocationPreflightTest(unittest.TestCase):
    def test_policy_is_exact_and_non_authorizing(self) -> None:
        policy = validator.load_policy()
        self.assertEqual("validation-only", policy["mode"])
        self.assertTrue(policy["require_valid_approval_validation"])
        self.assertIn(
            ".agent/checks/validate_implementation_invocation_preflight.py",
            policy["validator_bindings"],
        )

    def test_valid_preflight_is_accepted_without_authorization_or_start(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest, receipt, receipt_digest, preflight, preflight_digest = (
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
                preflight,
                preflight_digest,
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
        self.assertTrue(result["preflight_passed"])
        self.assertTrue(result["runner_controls_ready"])
        self.assertRegex(result["runner_readiness_sha256"], r"^[0-9a-f]{64}$")
        for field in validator.FALSE_AUTHORIZATION_FIELDS:
            self.assertFalse(result[field])

    def test_unready_current_runner_controls_invalidate_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest, receipt, receipt_digest, preflight, preflight_digest = (
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
                preflight,
                preflight_digest,
                validator.load_policies(),
                approval_helpers.unready_runner,
            )

        self.assertFalse(result["valid"])
        self.assertIn("approval_validation", [item["rule"] for item in result["failures"]])

    def test_wrong_digest_and_rehashed_overclaim_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest, receipt, receipt_digest, preflight, preflight_digest = (
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
                receipt_digest,
                preflight,
                "0" * 64,
                validator.load_policies(),
                approval_helpers.ready_runner,
            )
            value = json.loads(preflight.read_text(encoding="utf-8"))
            value["session_start_authorized"] = True
            preflight.write_text(json.dumps(value), encoding="utf-8")
            overclaim = validator.validate(
                repo,
                proposal,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                receipt,
                receipt_digest,
                preflight,
                validator.sha256_bytes(preflight.read_bytes()),
                validator.load_policies(),
                approval_helpers.ready_runner,
            )

        self.assertEqual("preflight_sha256", wrong["failures"][0]["rule"])
        self.assertIn("preflight_metadata", [item["rule"] for item in overclaim["failures"]])

    def test_rehashed_approval_validation_and_policy_binding_drift_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest, receipt, receipt_digest, preflight, preflight_digest = (
                prepare(temp)
            )
            value = json.loads(preflight.read_text(encoding="utf-8"))
            value["approval_validation"]["proposal_sha256"] = "0" * 64
            preflight.write_text(json.dumps(value), encoding="utf-8")
            stale = validator.validate(
                repo,
                proposal,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                receipt,
                receipt_digest,
                preflight,
                validator.sha256_bytes(preflight.read_bytes()),
                validator.load_policies(),
                approval_helpers.ready_runner,
            )
            value = json.loads(preflight.read_text(encoding="utf-8"))
            value["policy_bindings"][0]["sha256"] = "0" * 64
            preflight.write_text(json.dumps(value), encoding="utf-8")
            binding = validator.validate(
                repo,
                proposal,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                receipt,
                receipt_digest,
                preflight,
                validator.sha256_bytes(preflight.read_bytes()),
                validator.load_policies(),
                approval_helpers.ready_runner,
            )

        self.assertIn("approval_validation_record", [item["rule"] for item in stale["failures"]])
        self.assertIn("policy_bindings", [item["rule"] for item in binding["failures"]])

    def test_cli_refuses_policy_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest, receipt, receipt_digest, preflight, preflight_digest = (
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
                preflight,
                preflight_digest,
                "--preflight-validation-policy",
                "untrusted",
            )

        self.assertEqual(2, completed.returncode)
        self.assertIn("unrecognized arguments", completed.stderr)


if __name__ == "__main__":
    unittest.main()
