from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "validate_supervised_runner_receipt.py"
REPO_ROOT = CHECKS_DIR.parents[1]
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("validate_supervised_runner_receipt", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


def write_json(path: Path, value: dict[str, object]) -> str:
    content = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(content)
    return validator.validate_implementation_result.sha256_bytes(content)


def receipt_value(artifact: Path, artifact_sha256: str) -> dict[str, object]:
    return {
        "runner_receipt_version": 1,
        "purpose": "supervised_local_implementation_runner",
        "mode": "bounded-local-orchestration",
        **{field: False for field in validator.FALSE_FIELDS},
        "runner_complete": True,
        "stage": "complete",
        "identity": {
            "issue": 1,
            "risk": "low",
            "base_commit": "0" * 40,
            "workspace": str(artifact.parent),
            "runner_id": "receipt-validation-test",
            "preflight_sha256": "1" * 64,
            "start_authorization_receipt_sha256": "2" * 64,
        },
        "authorization_consumed": True,
        "launch_ready": True,
        "adapter_executed": True,
        "implementation_result_valid": True,
        "implementation_candidate_ready": True,
        "patch_post_validation_complete": True,
        "patch_candidate_ready": True,
        "quality_gate_executed": True,
        "quality_gate_passed": True,
        "quality_gate_receipt_valid": True,
        "network_requested": False,
        "publication_requested": False,
        "cleanup_performed": False,
        "cleanup_receipt_valid": False,
        "cleanup_required": True,
        "authorization_consumption_to_process_start_atomic": False,
        "cross_host_replay_prevention_enforced": False,
        "provider_credential_descendant_noninheritance_proven": False,
        "artifacts": {
            "expected_session": {
                "path": str(artifact),
                "sha256": artifact_sha256,
            }
        },
        "failures": [],
        "bindings": validator.initialize_portable_run.binding_records(
            [
                ".agent/checks/run_supervised_implementation.py",
                ".agent/policies/supervised-implementation-runner.json",
            ]
        ),
    }


class ValidateSupervisedRunnerReceiptTest(unittest.TestCase):
    def test_valid_receipt_checks_current_artifacts_and_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            artifact = temp / "expected-session.json"
            artifact_sha = write_json(artifact, {"fixture": "artifact"})
            receipt = temp / "final-receipt.json"
            receipt_sha = write_json(receipt, receipt_value(artifact, artifact_sha))

            result = validator.validate(receipt, receipt_sha, validator.load_policy())

        self.assertTrue(result["valid"], result["failures"])
        self.assertTrue(result["runner_complete"])
        self.assertEqual("complete", result["stage"])
        for field in validator.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_text_output_lists_only_validated_false_fields(self) -> None:
        text = validator.format_text(
            {
                "valid": True,
                "failures": [],
            }
        )

        for field in validator.FALSE_FIELDS:
            self.assertIn(f"{field}=false", text)
        self.assertNotIn("agent_invocation_authorized=false", text)

    def test_tampered_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            artifact = temp / "expected-session.json"
            artifact_sha = write_json(artifact, {"fixture": "artifact"})
            receipt = temp / "final-receipt.json"
            receipt_sha = write_json(receipt, receipt_value(artifact, artifact_sha))
            artifact.write_text("changed\n", encoding="utf-8")

            result = validator.validate(receipt, receipt_sha, validator.load_policy())

        self.assertFalse(result["valid"])
        self.assertIn("artifact_sha256", {item["rule"] for item in result["failures"]})

    def test_cli_refuses_policy_override(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--receipt",
                "final-receipt.json",
                "--receipt-sha256",
                "0" * 64,
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
