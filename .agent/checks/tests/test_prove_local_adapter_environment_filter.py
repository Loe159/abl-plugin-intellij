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
MODULE_PATH = CHECKS_DIR / "prove_local_adapter_environment_filter.py"
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location(
    "prove_local_adapter_environment_filter",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
proof = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = proof
SPEC.loader.exec_module(proof)


class ProveLocalAdapterEnvironmentFilterTest(unittest.TestCase):
    def test_policy_is_exact_env_only_non_authorizing_proof(self) -> None:
        policy = proof.load_policy()

        self.assertEqual(proof.EXPECTED_POLICY, policy)
        self.assertEqual("local_adapter_child_environment_filter", policy["proven_control"])
        self.assertEqual(
            "provider_credential_descendant_noninheritance",
            policy["related_control"],
        )

    def test_fixture_provider_env_vars_do_not_reach_adapter_child(self) -> None:
        result = proof.prove(REPO_ROOT, proof.load_policy())
        assessments = {item["id"]: item["assessment"] for item in result["control_assessments"]}

        self.assertTrue(result["proof_complete"])
        self.assertEqual(
            "verified_enforcement",
            assessments["local_adapter_child_environment_filter"],
        )
        self.assertTrue(result["fixture"]["matched"])
        self.assertTrue(result["scope"]["checks_environment_variables_only"])
        self.assertFalse(result["scope"]["proves_provider_filesystem_credentials_blocked"])
        self.assertFalse(result["scope"]["proves_os_credential_store_blocked"])
        for field in proof.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_policy_drift_and_cli_override_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "policy.json"
            value = json.loads(json.dumps(proof.EXPECTED_POLICY))
            value["sensitive_variable_names"].append("EXTRA_SECRET")
            path.write_text(json.dumps(value), encoding="utf-8")
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
