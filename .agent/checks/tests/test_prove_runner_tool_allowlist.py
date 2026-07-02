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
MODULE_PATH = CHECKS_DIR / "prove_runner_tool_allowlist.py"
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("prove_runner_tool_allowlist", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
proof = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = proof
SPEC.loader.exec_module(proof)


class ProveRunnerToolAllowlistTest(unittest.TestCase):
    def test_policy_is_exact_and_non_authorizing(self) -> None:
        policy = proof.load_policy()

        self.assertEqual(proof.EXPECTED_POLICY, policy)
        self.assertEqual("tool_allowlist", policy["proven_control"])
        self.assertIn(".agent/adapters/local_implementation_adapter.py", policy["bindings"])

    def test_proof_blocks_untrusted_adapter_before_consumption(self) -> None:
        result = proof.prove(REPO_ROOT, proof.load_policy())
        assessments = {item["id"]: item["assessment"] for item in result["control_assessments"]}

        self.assertTrue(result["proof_complete"])
        self.assertEqual("verified_enforcement", assessments["tool_allowlist"])
        self.assertFalse(result["scope"]["executes_adapter"])
        self.assertFalse(result["scope"]["consumes_authorization"])
        fixtures = {item["id"]: item for item in result["fixtures"]}
        self.assertTrue(fixtures["non_allowlisted_adapter_blocked_before_consumption"]["matched"])
        self.assertTrue(fixtures["allowlisted_local_adapter_entrypoint_resolves"]["matched"])
        for field in proof.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_policy_drift_and_cli_override_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "policy.json"
            value = json.loads(json.dumps(proof.EXPECTED_POLICY))
            value["proven_control"] = "network_isolation"
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
