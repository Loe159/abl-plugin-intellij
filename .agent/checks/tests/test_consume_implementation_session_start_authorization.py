from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "consume_implementation_session_start_authorization.py"
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location(
    "consume_implementation_session_start_authorization",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
consumer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = consumer
SPEC.loader.exec_module(consumer)
import test_approve_implementation_session as approval_helpers
import test_authorize_implementation_session_start as authorization_helpers


def consume_once(temp: Path) -> tuple[dict[str, object], Path, tuple[object, ...]]:
    inputs = authorization_helpers.write_authorization(temp)
    result = consumer.consume(
        *inputs,
        consumer.load_policies(),
        approval_helpers.ready_runner,
    )
    marker = consumer.marker_path(inputs[-2], consumer.load_policy())
    return result, marker, inputs


class ConsumeImplementationSessionStartAuthorizationTest(unittest.TestCase):
    def test_policy_is_exact_and_non_invoking(self) -> None:
        policy = consumer.load_policy()

        self.assertEqual("local-exclusive-consumption-only", policy["mode"])
        self.assertTrue(policy["require_valid_authorization_receipt"])
        self.assertIn(
            ".agent/checks/validate_implementation_session_start_authorization.py",
            policy["bindings"],
        )

    def test_valid_authorization_is_consumed_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result, marker, _inputs = consume_once(Path(temp_dir))
            value = json.loads(marker.read_text(encoding="utf-8"))

        self.assertTrue(result["consumed"], result["failures"])
        self.assertTrue(result["local_exclusive_marker_created"])
        self.assertTrue(value["session_start_authorization_consumed"])
        self.assertFalse(value["agent_invocation_authorized"])
        self.assertFalse(value["cross_host_replay_prevention_enforced"])
        self.assertFalse(value["tamper_resistant"])

    def test_second_consumption_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            first, _marker, inputs = consume_once(Path(temp_dir))
            second = consumer.consume(
                *inputs,
                consumer.load_policies(),
                approval_helpers.ready_runner,
            )

        self.assertTrue(first["consumed"])
        self.assertFalse(second["consumed"])
        self.assertTrue(second["ordinary_local_replay_rejected"])
        self.assertEqual(
            "authorization_already_consumed",
            second["failures"][0]["rule"],
        )

    def test_invalid_authorization_creates_no_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            inputs = list(authorization_helpers.write_authorization(Path(temp_dir)))
            inputs[-1] = "0" * 64
            marker = consumer.marker_path(inputs[-2], consumer.load_policy())
            result = consumer.consume(
                *inputs,
                consumer.load_policies(),
                approval_helpers.ready_runner,
            )

        self.assertFalse(result["consumed"])
        self.assertFalse(marker.exists())
        self.assertEqual(
            "authorization_receipt_validation",
            result["failures"][0]["rule"],
        )

    def test_validation_drift_before_write_creates_no_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            inputs = authorization_helpers.write_authorization(Path(temp_dir))
            marker = consumer.marker_path(inputs[-2], consumer.load_policy())
            original = (
                consumer.validate_implementation_session_start_authorization.validate
            )
            calls = 0

            def drifting_validation(*args: object, **kwargs: object) -> dict[str, object]:
                nonlocal calls
                value = original(*args, **kwargs)
                calls += 1
                if calls == 2:
                    value = dict(value)
                    value["valid"] = False
                return value

            with mock.patch.object(
                consumer.validate_implementation_session_start_authorization,
                "validate",
                side_effect=drifting_validation,
            ):
                result = consumer.consume(
                    *inputs,
                    consumer.load_policies(),
                    approval_helpers.ready_runner,
                )

        self.assertFalse(result["consumed"])
        self.assertFalse(marker.exists())
        self.assertEqual("state_changed", result["failures"][0]["rule"])

    def test_existing_symlink_marker_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            inputs = authorization_helpers.write_authorization(Path(temp_dir))
            marker = inputs[-2].with_name(inputs[-2].name + ".consumed.json")
            target = Path(temp_dir) / "target"
            target.write_text("x", encoding="utf-8")
            try:
                marker.symlink_to(target)
            except OSError:
                self.skipTest("symlink creation unavailable")
            with self.assertRaisesRegex(ValueError, "symlinks"):
                consumer.consume(
                    *inputs,
                    consumer.load_policies(),
                    approval_helpers.ready_runner,
                )


if __name__ == "__main__":
    unittest.main()
