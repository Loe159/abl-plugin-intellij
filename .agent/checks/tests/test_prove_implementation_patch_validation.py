from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "prove_implementation_patch_validation.py"
REPO_ROOT = CHECKS_DIR.parents[1]
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location(
    "prove_implementation_patch_validation",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
proof = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = proof
SPEC.loader.exec_module(proof)


class ProveImplementationPatchValidationTest(unittest.TestCase):
    def test_policy_is_exact_and_keeps_quality_gate_unproven(self) -> None:
        policy = proof.load_policy()

        self.assertEqual("implementation_patch_post_validation", policy["proven_control"])
        self.assertIn("implementation_quality_gate_execution", policy["unproven_controls"])

    def test_real_synthetic_repositories_match_all_fixtures(self) -> None:
        result = proof.prove(REPO_ROOT, proof.load_policy())

        self.assertEqual(
            "verified_enforcement",
            result["control_assessments"][0]["assessment"],
        )
        self.assertTrue(all(item["matched"] for item in result["fixtures"]))
        self.assertFalse(result["scope"]["runs_quality_gate"])
        self.assertFalse(result["scope"]["invokes_agent"])
        for field in proof.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_policy_drift_and_cli_override_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "policy.json"
            policy = json.loads(json.dumps(proof.EXPECTED_POLICY))
            policy["unproven_controls"].remove("implementation_quality_gate_execution")
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
