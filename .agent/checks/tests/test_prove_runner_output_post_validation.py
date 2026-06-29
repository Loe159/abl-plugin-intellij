from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = CHECKS_DIR.parents[1]
MODULE_PATH = CHECKS_DIR / "prove_runner_output_post_validation.py"
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location(
    "prove_runner_output_post_validation",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
proof = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = proof
SPEC.loader.exec_module(proof)


class ProveRunnerOutputPostValidationTest(unittest.TestCase):
    def test_policy_is_exact_fixture_only_and_non_authorizing(self) -> None:
        policy = proof.load_policy()

        self.assertEqual(proof.EXPECTED_POLICY, policy)
        self.assertEqual("runner_output_post_validation_fixture", policy["proven_control"])
        self.assertIn("runner_enforced_output_post_validation", policy["unproven_controls"])

    def test_fixture_matches_without_claiming_real_runner_enforcement(self) -> None:
        result = proof.prove(REPO_ROOT, proof.load_policy())

        self.assertEqual(
            "verified_fixture",
            result["control_assessments"][0]["assessment"],
        )
        self.assertTrue(all(item["matched"] for item in result["fixtures"]))
        self.assertFalse(result["scope"]["proves_real_runner_enforcement"])
        self.assertFalse(result["scope"]["proves_real_agent_result_compatibility"])
        for field in proof.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_policy_drift_and_cli_override_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "policy.json"
            policy = json.loads(json.dumps(proof.EXPECTED_POLICY))
            policy["mode"] = "enforcement-proof"
            path.write_text(json.dumps(policy), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match"):
                proof.load_policy(path)

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
