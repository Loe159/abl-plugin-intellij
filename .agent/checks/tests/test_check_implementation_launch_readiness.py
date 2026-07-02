from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "check_implementation_launch_readiness.py"
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location(
    "check_implementation_launch_readiness",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)
import test_approve_implementation_session as approval_helpers
import test_validate_implementation_session_start_consumption as consumption_helpers


class CheckImplementationLaunchReadinessTest(unittest.TestCase):
    def test_policy_is_exact_and_non_invoking(self) -> None:
        policy = checker.load_policy()

        self.assertEqual("post-consumption-readiness-only", policy["mode"])
        self.assertTrue(policy["require_invocation_ready"])
        self.assertTrue(policy["require_valid_consumption_marker"])

    def test_ready_fixture_reaches_launch_boundary_without_launching(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            values = consumption_helpers.consumed(Path(temp_dir))
            result = checker.check_launch(
                *values,
                checker.load_policies(),
                approval_helpers.ready_runner,
            )

        self.assertTrue(result["launch_ready"], result["failures"])
        self.assertTrue(result["invocation_ready"])
        self.assertTrue(result["consumption_marker_valid"])
        self.assertTrue(result["session_start_authorization_consumed"])
        for field in checker.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_unready_runner_and_bad_marker_block_launch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            values = consumption_helpers.consumed(Path(temp_dir))
            unready = checker.check_launch(
                *values,
                checker.load_policies(),
                approval_helpers.unready_runner,
            )
        self.assertFalse(unready["launch_ready"])
        self.assertIn(
            "invocation_readiness",
            [item["rule"] for item in unready["failures"]],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            values = list(consumption_helpers.consumed(Path(temp_dir)))
            values[-1] = "0" * 64
            invalid = checker.check_launch(
                *values,
                checker.load_policies(),
                approval_helpers.ready_runner,
            )
        self.assertFalse(invalid["launch_ready"])
        self.assertIn(
            "consumption_marker_validation",
            [item["rule"] for item in invalid["failures"]],
        )


if __name__ == "__main__":
    unittest.main()
