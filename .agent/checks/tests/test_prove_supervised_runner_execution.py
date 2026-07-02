from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = CHECKS_DIR.parents[1]
MODULE_PATH = CHECKS_DIR / "prove_supervised_runner_execution.py"
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("prove_supervised_runner_execution", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
proof = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = proof
SPEC.loader.exec_module(proof)


class ProveSupervisedRunnerExecutionTest(unittest.TestCase):
    def test_policy_is_exact_fixture_only(self) -> None:
        policy = proof.load_policy()

        self.assertEqual(proof.EXPECTED_POLICY, policy)
        self.assertEqual("fixture-only", policy["mode"])
        self.assertEqual("runner_enforced_output_post_validation", policy["proven_control"])

    def test_runner_execution_fixture_proves_post_validation_boundary(self) -> None:
        result = proof.prove(REPO_ROOT, proof.load_policy())
        assessments = {
            item["id"]: item["assessment"] for item in result["control_assessments"]
        }

        self.assertTrue(result["proof_complete"])
        self.assertEqual(
            "verified_enforcement",
            assessments["runner_enforced_output_post_validation"],
        )
        self.assertEqual(
            "verified_fixture",
            assessments["supervised_runner_quality_gate_sequence"],
        )
        self.assertEqual(
            "verified_fixture",
            assessments["cleanup_after_successful_runner_completion"],
        )
        self.assertEqual(
            "verified_fixture",
            assessments["cleanup_after_controlled_blocked_completion"],
        )
        self.assertEqual(
            "verified_fixture",
            assessments["cleanup_receipt_validation_after_runner_cleanup"],
        )
        self.assertEqual(
            "verified_fixture",
            assessments["supervised_runner_consumption_launch_before_adapter_sequence"],
        )
        self.assertEqual(
            "verified_fixture",
            assessments["final_receipt_validation_after_runner_write"],
        )
        self.assertEqual(
            "verified_fixture",
            assessments["controlled_adapter_timeout_blocks_before_patch"],
        )
        self.assertEqual(
            "verified_fixture",
            assessments["cleanup_after_controlled_adapter_timeout"],
        )
        self.assertEqual("not_proven", assessments["real_gradle_quality_gate_execution"])
        self.assertEqual("not_proven", assessments["real_agent_result_compatibility"])
        self.assertEqual("not_proven", assessments["cleanup_after_failed_runner_completion"])
        self.assertEqual("not_proven", assessments["cleanup_after_timeout_or_process_termination"])
        self.assertEqual("not_proven", assessments["cleanup_after_host_crash"])
        self.assertTrue(result["scope"]["uses_fixture_patch_validator"])
        self.assertTrue(result["scope"]["uses_fixture_cleanup_runner"])
        self.assertTrue(result["scope"]["observes_cleanup_after_successful_completion"])
        self.assertTrue(result["scope"]["observes_cleanup_after_controlled_blocked_completion"])
        self.assertTrue(result["scope"]["observes_cleanup_receipt_validation_after_cleanup"])
        self.assertTrue(result["scope"]["observes_consumption_launch_before_adapter_sequence"])
        self.assertTrue(result["scope"]["observes_final_receipt_validation_after_write"])
        self.assertTrue(
            result["scope"]["observes_controlled_adapter_timeout_blocks_before_patch"]
        )
        self.assertTrue(result["scope"]["observes_cleanup_after_controlled_adapter_timeout"])
        self.assertFalse(result["scope"]["proves_cleanup_after_failure_timeout_or_crash"])
        self.assertTrue(all(item["matched"] for item in result["fixtures"]))
        for field in proof.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_cli_refuses_policy_override(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--repo",
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


if __name__ == "__main__":
    unittest.main()
