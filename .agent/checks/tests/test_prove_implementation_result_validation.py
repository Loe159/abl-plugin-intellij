from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "prove_implementation_result_validation.py"
REPO_ROOT = CHECKS_DIR.parents[1]
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location(
    "prove_implementation_result_validation",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
proof = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = proof
SPEC.loader.exec_module(proof)


class ProveImplementationResultValidationTest(unittest.TestCase):
    def test_policy_is_exact_and_preserves_unproven_runner_boundary(self) -> None:
        policy = proof.load_policy()

        self.assertEqual("implementation_result_contract_validation", policy["proven_control"])
        self.assertIn("runner_enforced_output_post_validation", policy["unproven_controls"])
        self.assertIn("implementation_patch_post_validation", policy["unproven_controls"])

    def test_all_adversarial_fixtures_match(self) -> None:
        result = proof.prove(REPO_ROOT, proof.load_policy())

        self.assertEqual(
            "verified_enforcement",
            result["control_assessments"][0]["assessment"],
        )
        self.assertTrue(all(item["matched"] for item in result["fixtures"]))
        self.assertFalse(result["scope"]["proves_runner_calls_validator"])
        self.assertFalse(result["scope"]["generates_or_validates_patch"])
        for field in proof.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_policy_drift_and_cli_override_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "policy.json"
            policy = json.loads(json.dumps(proof.EXPECTED_POLICY))
            policy["unproven_controls"].remove("implementation_patch_post_validation")
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

    def test_real_cli_preserves_repository_state(self) -> None:
        status_command = [
            "git",
            "-c",
            f"safe.directory={REPO_ROOT.as_posix()}",
            "-C",
            str(REPO_ROOT),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ]
        before = subprocess.run(
            status_command,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--repo",
                str(REPO_ROOT),
                "--format",
                "json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        after = subprocess.run(
            status_command,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        result = json.loads(completed.stdout)

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(before, after)
        self.assertEqual(
            "verified_enforcement",
            result["control_assessments"][0]["assessment"],
        )


if __name__ == "__main__":
    unittest.main()
