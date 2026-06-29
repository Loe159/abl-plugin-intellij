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
MODULE_PATH = CHECKS_DIR / "check_multi_adapter_comparison_readiness.py"
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location(
    "check_multi_adapter_comparison_readiness",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


class CheckMultiAdapterComparisonReadinessTest(unittest.TestCase):
    def test_policy_is_exact_local_preflight_only(self) -> None:
        policy = checker.load_policy()

        self.assertEqual(checker.EXPECTED_POLICY, policy)
        self.assertEqual("local-preflight-only", policy["mode"])
        self.assertIn("explicit_comparison_task", policy["required_missing_controls"])
        self.assertIn("manual_metric_interpretation", policy["required_missing_controls"])

    def test_current_readiness_is_false_and_non_invoking(self) -> None:
        result = checker.check_readiness(REPO_ROOT, checker.load_policy())

        self.assertFalse(result["comparison_ready"])
        self.assertTrue(result["repo_unchanged"])
        self.assertEqual(
            checker.load_policy()["required_missing_controls"],
            result["missing_controls"],
        )
        for field in checker.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_policy_drift_and_cli_override_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "policy.json"
            value = json.loads(json.dumps(checker.EXPECTED_POLICY))
            value["mode"] = "invoking"
            path.write_text(json.dumps(value), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "does not match"):
                checker.load_policy(path)

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
