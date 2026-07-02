from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "validate_implementation_result.py"
REPO_ROOT = CHECKS_DIR.parents[1]
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("validate_implementation_result", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


def session() -> dict[str, object]:
    return {
        "issue": 57,
        "risk": "medium",
        "base_commit": "1" * 40,
        "workspace": str(REPO_ROOT.resolve()),
        "runner_id": "test-runner",
        "preflight_sha256": "2" * 64,
        "start_authorization_receipt_sha256": "3" * 64,
    }


def result_value() -> dict[str, object]:
    return {
        "result_version": 1,
        "purpose": "implementation_session_result",
        "mode": "untrusted-runner-output",
        "status": "completed",
        **session(),
        "summary": "Completed the bounded fixture.",
        "workspace_changed": True,
        "patch_generated": False,
        "deterministic_checks_run": False,
        "publication_requested": False,
        "network_requested": False,
        "next_action": "deterministic_patch_generation",
    }


def execution(stdout: bytes, **changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "completed": True,
        "stdout": stdout,
        "stderr": b"",
        "capture_complete": True,
        "timed_out": False,
        "output_limit_exceeded": False,
        "kill_requested": False,
        "direct_child_reaped": True,
        "returncode": 0,
        "captured_stdout_bytes": len(stdout),
        "captured_stderr_bytes": 0,
    }
    value.update(changes)
    if "stderr" in changes and "captured_stderr_bytes" not in changes:
        value["captured_stderr_bytes"] = len(changes["stderr"])
    return value


class ValidateImplementationResultTest(unittest.TestCase):
    def validate(self, value: dict[str, object], **changes: object) -> dict[str, object]:
        return validator.validate_execution(
            execution(validator.canonical_result_bytes(value), **changes),
            session(),
            validator.load_policy(),
            validator.diff_policy.load_policy(validator.DIFF_POLICY_PATH),
        )

    def test_policy_and_schema_are_exact(self) -> None:
        self.assertEqual(validator.EXPECTED_POLICY, validator.load_policy())
        self.assertEqual(validator.EXPECTED_SCHEMA, validator.load_schema())
        self.assertEqual(
            set(validator.EXPECTED_SCHEMA["required"]),
            validator.RESULT_FIELDS,
        )

    def test_canonical_completed_result_is_candidate_ready_but_not_authorized(self) -> None:
        result = self.validate(result_value())

        self.assertTrue(result["valid"])
        self.assertTrue(result["implementation_candidate_ready"])
        self.assertEqual("completed", result["status"])
        for field in validator.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_blocked_result_is_valid_but_not_candidate_ready(self) -> None:
        value = result_value()
        value.update(
            status="blocked",
            workspace_changed=False,
            next_action="human_review",
        )

        result = self.validate(value)

        self.assertTrue(result["valid"])
        self.assertFalse(result["implementation_candidate_ready"])

    def test_identity_schema_secret_and_overclaims_fail_closed(self) -> None:
        cases: list[tuple[str, dict[str, object], str]] = []
        wrong_identity = copy.deepcopy(result_value())
        wrong_identity["preflight_sha256"] = "4" * 64
        cases.append(("identity", wrong_identity, "session_identity"))
        wrong_type = copy.deepcopy(result_value())
        wrong_type["issue"] = 57.0
        cases.append(("identity_type", wrong_type, "session_identity"))
        extra = copy.deepcopy(result_value())
        extra["unexpected"] = True
        cases.append(("extra", extra, "result_schema"))
        secret = copy.deepcopy(result_value())
        secret["summary"] = "ghp_" + ("A" * 36)
        cases.append(("secret", secret, "high_confidence_secret"))
        overclaim = copy.deepcopy(result_value())
        overclaim["publication_requested"] = True
        cases.append(("overclaim", overclaim, "forbidden_claim"))
        no_change = copy.deepcopy(result_value())
        no_change["workspace_changed"] = False
        cases.append(("no_change", no_change, "workspace_change_required"))

        for name, value, expected_rule in cases:
            with self.subTest(name=name):
                result = self.validate(value)
                self.assertFalse(result["valid"])
                self.assertIn(expected_rule, {item["rule"] for item in result["failures"]})

    def test_capture_protocol_and_canonical_encoding_fail_closed(self) -> None:
        canonical = validator.canonical_result_bytes(result_value())
        noncanonical = json.dumps(result_value(), indent=2).encode("utf-8")
        cases = [
            ("incomplete", execution(canonical, capture_complete=False), "capture_complete"),
            ("not_completed", execution(canonical, completed=False), "execution_completed"),
            ("timeout", execution(canonical, timed_out=True), "timed_out"),
            ("limit", execution(canonical, output_limit_exceeded=True), "output_limit"),
            ("kill", execution(canonical, kill_requested=True), "kill_requested"),
            ("unreaped", execution(canonical, direct_child_reaped=False), "direct_child_reaped"),
            ("exit", execution(canonical, returncode=1), "protocol_exit"),
            ("stderr", execution(canonical, stderr=b"diagnostic"), "stderr"),
            (
                "wrong_count",
                execution(canonical, captured_stdout_bytes=len(canonical) - 1),
                "capture_byte_counts",
            ),
            ("noncanonical", execution(noncanonical), "canonical_json"),
        ]
        for name, captured, expected_rule in cases:
            with self.subTest(name=name):
                result = validator.validate_execution(
                    captured,
                    session(),
                    validator.load_policy(),
                    validator.diff_policy.load_policy(validator.DIFF_POLICY_PATH),
                )
                self.assertFalse(result["valid"])
                self.assertIn(expected_rule, {item["rule"] for item in result["failures"]})

    def test_policy_drift_invalid_session_and_cli_override_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            policy_path = root / "policy.json"
            policy = json.loads(json.dumps(validator.EXPECTED_POLICY))
            policy["required_false_fields"].remove("network_requested")
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match"):
                validator.load_policy(policy_path)
        invalid_session = session()
        invalid_session["workspace"] = "relative"
        with self.assertRaisesRegex(ValueError, "identity is invalid"):
            validator.validate_expected_session(invalid_session)

        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--result",
                "result.json",
                "--expected-session",
                "session.json",
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
