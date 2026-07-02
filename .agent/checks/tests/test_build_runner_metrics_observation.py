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
MODULE_PATH = CHECKS_DIR / "build_runner_metrics_observation.py"
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("build_runner_metrics_observation", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)


def write_bytes(path: Path, content: bytes) -> str:
    path.write_bytes(content)
    return builder.record_run_metrics.sha256_bytes(content)


def write_json(path: Path, value: dict[str, object]) -> str:
    return write_bytes(path, builder.canonical_bytes(value))


def receipt_value(temp: Path, complete: bool, include_patch: bool) -> tuple[dict[str, object], str | None]:
    expected = temp / "expected-session.json"
    expected_sha = write_json(expected, {"fixture": "expected-session"})
    artifacts: dict[str, dict[str, str]] = {
        "expected_session": {"path": str(expected), "sha256": expected_sha}
    }
    patch_sha: str | None = None
    if include_patch:
        patch = temp / "patch.diff"
        patch_sha = write_bytes(
            patch,
            b"diff --git a/example.txt b/example.txt\n--- a/example.txt\n+++ b/example.txt\n@@ -1 +1 @@\n-old\n+new\n",
        )
        artifacts["patch"] = {"path": str(patch), "sha256": patch_sha}
    value = {
        "runner_receipt_version": 1,
        "purpose": "supervised_local_implementation_runner",
        "mode": "bounded-local-orchestration",
        **{field: False for field in builder.validate_supervised_runner_receipt.FALSE_FIELDS},
        "runner_complete": complete,
        "stage": "complete" if complete else "implementation_result",
        "identity": {
            "issue": 17,
            "risk": "medium",
            "base_commit": "a" * 40,
            "workspace": str(temp / "workspace"),
            "runner_id": "fixture-local-runner",
            "preflight_sha256": "b" * 64,
            "start_authorization_receipt_sha256": "c" * 64,
        },
        "authorization_consumed": True,
        "launch_ready": True,
        "adapter_executed": True,
        "implementation_result_valid": complete,
        "implementation_candidate_ready": complete,
        "patch_post_validation_complete": complete,
        "patch_candidate_ready": complete,
        "quality_gate_executed": complete,
        "quality_gate_passed": complete,
        "quality_gate_receipt_valid": complete,
        "network_requested": False,
        "publication_requested": False,
        "cleanup_performed": False,
        "cleanup_receipt_valid": False,
        "cleanup_required": True,
        "authorization_consumption_to_process_start_atomic": False,
        "cross_host_replay_prevention_enforced": False,
        "provider_credential_descendant_noninheritance_proven": False,
        "artifacts": artifacts,
        "failures": []
        if complete
        else [{"rule": "implementation_result", "message": "Captured result is invalid."}],
        "bindings": builder.validate_supervised_runner_receipt.initialize_portable_run.binding_records(
            [
                ".agent/checks/run_supervised_implementation.py",
                ".agent/policies/supervised-implementation-runner.json",
            ]
        ),
    }
    return value, patch_sha


class BuildRunnerMetricsObservationTest(unittest.TestCase):
    def test_policy_is_exact_receipt_derived_only(self) -> None:
        policy = builder.load_policy()

        self.assertEqual(builder.EXPECTED_POLICY, policy)
        self.assertEqual("receipt-derived-observation-only", policy["mode"])

    def test_complete_runner_receipt_derives_measured_patch_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            receipt = temp / "final-receipt.json"
            value, patch_sha = receipt_value(temp, complete=True, include_patch=True)
            receipt_sha = write_json(receipt, value)
            output = temp / "observation.json"

            observation, content = builder.build_observation(
                REPO_ROOT,
                receipt,
                receipt_sha,
                output,
                "issue-17-run-1",
                "2026-06-17T10:00:00Z",
                "2026-06-17T10:02:00Z",
                "openai",
                "unknown",
                builder.load_policy(),
            )

        self.assertEqual("implement", observation["stage"])
        self.assertEqual("succeeded", observation["outcome"]["status"])
        self.assertEqual("measured", observation["diff_status"])
        self.assertEqual(patch_sha, observation["patch_sha256"])
        self.assertEqual("unavailable", observation["tokens"]["status"])
        self.assertEqual("unavailable", observation["cost"]["status"])
        self.assertLess(len(content), builder.record_run_metrics.load_policy()["max_observation_bytes"])

    def test_blocked_runner_receipt_derives_no_diff_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            receipt = temp / "final-receipt.json"
            value, _patch_sha = receipt_value(temp, complete=False, include_patch=False)
            receipt_sha = write_json(receipt, value)
            output = temp / "observation.json"

            observation, _content = builder.build_observation(
                REPO_ROOT,
                receipt,
                receipt_sha,
                output,
                "issue-17-run-2",
                "2026-06-17T10:00:00Z",
                "2026-06-17T10:01:00Z",
                "openai",
                "unknown",
                builder.load_policy(),
            )

        self.assertEqual("blocked", observation["outcome"]["status"])
        self.assertEqual("not_applicable", observation["diff_status"])
        self.assertIsNone(observation["patch_sha256"])

    def test_builder_enforces_its_own_receipt_size_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            receipt = temp / "final-receipt.json"
            value, _patch_sha = receipt_value(temp, complete=False, include_patch=False)
            value["failures"] = [
                {
                    "rule": "implementation_result",
                    "message": "x" * builder.load_policy()["max_receipt_bytes"],
                }
            ]
            receipt_sha = write_json(receipt, value)

            with self.assertRaisesRegex(ValueError, "max_receipt_bytes"):
                builder.build_observation(
                    REPO_ROOT,
                    receipt,
                    receipt_sha,
                    temp / "observation.json",
                    "issue-17-run-large",
                    "2026-06-17T10:00:00Z",
                    "2026-06-17T10:01:00Z",
                    "openai",
                    "unknown",
                    builder.load_policy(),
                )

    def test_cli_writes_once_and_refuses_policy_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            receipt = temp / "final-receipt.json"
            value, _patch_sha = receipt_value(temp, complete=False, include_patch=False)
            receipt_sha = write_json(receipt, value)
            output = temp / "observation.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--repo",
                    str(REPO_ROOT),
                    "--final-receipt",
                    str(receipt),
                    "--final-receipt-sha256",
                    receipt_sha,
                    "--run-id",
                    "issue-17-run-3",
                    "--started-at",
                    "2026-06-17T10:00:00Z",
                    "--completed-at",
                    "2026-06-17T10:01:00Z",
                    "--model-provider",
                    "openai",
                    "--model-id",
                    "unknown",
                    "--output",
                    str(output),
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            second = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--repo",
                    str(REPO_ROOT),
                    "--final-receipt",
                    str(receipt),
                    "--final-receipt-sha256",
                    receipt_sha,
                    "--run-id",
                    "issue-17-run-3",
                    "--started-at",
                    "2026-06-17T10:00:00Z",
                    "--completed-at",
                    "2026-06-17T10:01:00Z",
                    "--model-provider",
                    "openai",
                    "--model-id",
                    "unknown",
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            override = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--repo",
                    str(REPO_ROOT),
                    "--final-receipt",
                    str(receipt),
                    "--final-receipt-sha256",
                    receipt_sha,
                    "--run-id",
                    "issue-17-run-4",
                    "--started-at",
                    "2026-06-17T10:00:00Z",
                    "--completed-at",
                    "2026-06-17T10:01:00Z",
                    "--model-provider",
                    "openai",
                    "--model-id",
                    "unknown",
                    "--output",
                    str(temp / "other.json"),
                    "--policy",
                    "untrusted.json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            output_exists = output.is_file()

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["produced"])
        self.assertTrue(output_exists)
        self.assertEqual(1, second.returncode)
        self.assertIn("already exists", second.stderr)
        self.assertEqual(2, override.returncode)
        self.assertIn("unrecognized arguments", override.stderr)


if __name__ == "__main__":
    unittest.main()
