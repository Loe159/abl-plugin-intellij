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
MODULE_PATH = CHECKS_DIR / "check_historical_golden_set_readiness.py"
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location(
    "check_historical_golden_set_readiness",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


class CheckHistoricalGoldenSetReadinessTest(unittest.TestCase):
    def test_policy_is_exact_local_preflight_only(self) -> None:
        policy = checker.load_policy()

        self.assertEqual(checker.EXPECTED_POLICY, policy)
        self.assertEqual("local-preflight-only", policy["mode"])
        self.assertIn("external_candidate_manifest", policy["required_missing_controls"])
        self.assertIn("human_normalized_task_corpus", policy["required_missing_controls"])
        self.assertIn(
            "human_golden_set_adoption_decision",
            policy["required_missing_controls"],
        )
        self.assertIn("evals/golden-set.yaml", policy["bindings"])

    def test_current_readiness_is_false_and_non_authorizing(self) -> None:
        result = checker.check_readiness(REPO_ROOT, checker.load_policy())

        self.assertFalse(result["golden_set_ready"])
        self.assertFalse(result["candidate_manifest_valid"])
        self.assertTrue(result["repo_unchanged"])
        self.assertEqual(
            checker.load_policy()["required_missing_controls"],
            result["missing_controls"],
        )
        for field in checker.FALSE_FIELDS:
            self.assertFalse(result[field])
        self.assertIn(
            "evals/golden-set.yaml",
            [record["name"] for record in result["bindings"]],
        )

    def test_cli_json_reports_current_not_ready_marker(self) -> None:
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

        self.assertEqual(2, completed.returncode, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertFalse(result["golden_set_ready"])
        self.assertFalse(result["candidate_manifest_valid"])
        self.assertIn(
            "evals/golden-set.yaml",
            [record["name"] for record in result["bindings"]],
        )

    def test_policy_drift_and_cli_override_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "policy.json"
            value = json.loads(json.dumps(checker.EXPECTED_POLICY))
            value["required_missing_controls"].remove("external_candidate_manifest")
            path.write_text(json.dumps(value), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "does not match"):
                checker.load_policy(path)

        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--repo",
                str(REPO_ROOT),
                "--manifest",
                "candidate.json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, completed.returncode)
        self.assertIn("unrecognized arguments", completed.stderr)


if __name__ == "__main__":
    unittest.main()
