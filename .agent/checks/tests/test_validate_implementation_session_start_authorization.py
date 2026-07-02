from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "validate_implementation_session_start_authorization.py"
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location(
    "validate_implementation_session_start_authorization",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)
import test_approve_implementation_session as approval_helpers
import test_authorize_implementation_session_start as authorization_helpers


class ValidateImplementationSessionStartAuthorizationTest(unittest.TestCase):
    def test_policy_is_exact_and_validation_only(self) -> None:
        policy = validator.load_policy()

        self.assertEqual("validation-only", policy["mode"])
        self.assertTrue(policy["require_session_start_ready"])
        self.assertIn(
            ".agent/checks/validate_implementation_session_start_authorization.py",
            policy["validator_bindings"],
        )

    def test_real_receipt_is_validated_without_invocation_or_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
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
                authorization_digest,
            ) = authorization_helpers.write_authorization(Path(temp_dir))
            result = validator.validate(
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
                authorization_digest,
                validator.load_policies(),
                approval_helpers.ready_runner,
            )

        self.assertTrue(result["valid"], result["failures"])
        self.assertTrue(result["session_start_authorized"])
        self.assertFalse(result["authorizer_authenticated"])
        self.assertFalse(result["replay_prevention_enforced"])
        for field in validator.authorize_implementation_session_start.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_wrong_digest_and_rehashed_overclaim_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
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
                authorization_digest,
            ) = authorization_helpers.write_authorization(Path(temp_dir))
            wrong = validator.validate(
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
                "0" * 64,
                validator.load_policies(),
                approval_helpers.ready_runner,
            )
            value = json.loads(authorization_receipt.read_text(encoding="utf-8"))
            value["agent_invocation_authorized"] = True
            authorization_receipt.write_text(json.dumps(value), encoding="utf-8")
            overclaim = validator.validate(
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
                validator.authorize_implementation_session_start.sha256_bytes(
                    authorization_receipt.read_bytes()
                ),
                validator.load_policies(),
                approval_helpers.ready_runner,
            )

        self.assertEqual("receipt_sha256", wrong["failures"][0]["rule"])
        self.assertIn(
            "receipt_metadata",
            [item["rule"] for item in overclaim["failures"]],
        )
        self.assertRegex(authorization_digest, r"^[0-9a-f]{64}$")

    def test_runner_readiness_drift_invalidates_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
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
                authorization_digest,
            ) = authorization_helpers.write_authorization(Path(temp_dir))
            result = validator.validate(
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
                authorization_digest,
                validator.load_policies(),
                approval_helpers.unready_runner,
            )

        self.assertFalse(result["valid"])
        self.assertIn(
            "session_start_readiness",
            [item["rule"] for item in result["failures"]],
        )


if __name__ == "__main__":
    unittest.main()
