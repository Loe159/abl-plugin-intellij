from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "validate_implementation_session_start_consumption.py"
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location(
    "validate_implementation_session_start_consumption",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)
import test_approve_implementation_session as approval_helpers
import test_authorize_implementation_session_start as authorization_helpers


def consumed(temp: Path) -> tuple[object, ...]:
    inputs = authorization_helpers.write_authorization(temp)
    result = validator.consume_implementation_session_start_authorization.consume(
        *inputs,
        validator.load_policies(),
        approval_helpers.ready_runner,
    )
    assert result["consumed"], result
    marker = Path(result["consumption_marker"])
    return (*inputs, marker, result["consumption_marker_sha256"])


def validate(values: tuple[object, ...]) -> dict[str, object]:
    return validator.validate(
        *values,
        validator.load_policies(),
        approval_helpers.ready_runner,
    )


class ValidateImplementationSessionStartConsumptionTest(unittest.TestCase):
    def test_policy_is_exact_validation_only_and_non_invoking(self) -> None:
        policy = validator.load_policy()

        self.assertEqual(validator.EXPECTED_POLICY, policy)
        self.assertEqual("validation-only", policy["mode"])
        self.assertTrue(policy["require_canonical_marker"])

    def test_real_marker_is_validated_without_invocation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            values = consumed(Path(temp_dir))
            result = validate(values)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--repo",
                    str(values[0]),
                    "--proposal",
                    str(values[1]),
                    "--proposal-sha256",
                    str(values[2]),
                    "--workspace",
                    str(values[3]),
                    "--worktree-receipt",
                    str(values[4]),
                    "--worktree-receipt-sha256",
                    str(values[5]),
                    "--approval-receipt",
                    str(values[6]),
                    "--approval-receipt-sha256",
                    str(values[7]),
                    "--preflight",
                    str(values[8]),
                    "--preflight-sha256",
                    str(values[9]),
                    "--authorization-receipt",
                    str(values[10]),
                    "--authorization-receipt-sha256",
                    str(values[11]),
                    "--consumption-marker",
                    str(values[12]),
                    "--consumption-marker-sha256",
                    str(values[13]),
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertTrue(result["valid"], result["failures"])
        self.assertEqual(1, completed.returncode)
        self.assertEqual("", completed.stdout)
        self.assertIn(
            "implementation-session-start-consumption-validation: ERROR",
            completed.stderr,
        )
        self.assertTrue(result["session_start_authorization_consumed"])
        self.assertTrue(result["ordinary_local_replay_rejected"])
        self.assertFalse(result["cross_host_replay_prevention_enforced"])
        self.assertFalse(result["tamper_resistant"])
        for field in validator.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_wrong_digest_rejects_before_marker_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            values = list(consumed(Path(temp_dir)))
            values[-2].write_text("not json", encoding="utf-8")
            values[-1] = "0" * 64
            result = validate(tuple(values))

        self.assertEqual("marker_sha256", result["failures"][0]["rule"])

    def test_rehashed_overclaim_and_identity_change_are_rejected(self) -> None:
        mutations = [
            (
                "marker_metadata",
                lambda value: value.update(agent_invocation_authorized=True),
            ),
            ("marker_identity", lambda value: value.update(issue=True)),
            (
                "trusted_binding_mismatch",
                lambda value: value["bindings"][0].update(sha256="0" * 64),
            ),
        ]
        for expected, mutate in mutations:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp_dir:
                values = list(consumed(Path(temp_dir)))
                marker = values[-2]
                value = json.loads(marker.read_text(encoding="utf-8"))
                mutate(value)
                marker.write_bytes(
                    validator.consume_implementation_session_start_authorization.canonical_marker_bytes(
                        value
                    )
                )
                values[-1] = validator.authorize_implementation_session_start.sha256_bytes(
                    marker.read_bytes()
                )
                result = validate(tuple(values))
                self.assertIn(expected, [item["rule"] for item in result["failures"]])

    def test_copied_marker_and_unready_current_state_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            values = list(consumed(Path(temp_dir)))
            copied = Path(temp_dir) / "copied-consumption.json"
            copied.write_bytes(values[-2].read_bytes())
            values[-2] = copied
            copied_result = validate(tuple(values))
            self.assertIn(
                "marker_path",
                [item["rule"] for item in copied_result["failures"]],
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            values = consumed(Path(temp_dir))
            result = validator.validate(
                *values,
                validator.load_policies(),
                approval_helpers.unready_runner,
            )
            self.assertIn(
                "authorization_receipt_validation",
                [item["rule"] for item in result["failures"]],
            )


if __name__ == "__main__":
    unittest.main()
