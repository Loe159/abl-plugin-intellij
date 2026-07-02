from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "prove_bounded_output_capture.py"
REPO_ROOT = CHECKS_DIR.parents[1]
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("prove_bounded_output_capture", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
proof = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = proof
SPEC.loader.exec_module(proof)


class BoundedOutputCaptureProofTest(unittest.TestCase):
    def test_policy_is_exact_and_result_validation_remains_separate(self) -> None:
        policy = proof.load_policy()

        self.assertEqual("enforcement-proof", policy["mode"])
        self.assertEqual("bounded_output_capture", policy["proven_control"])
        self.assertIn(
            "implementation_result_contract_validation",
            policy["unproven_controls"],
        )
        self.assertIn(
            "runner_enforced_output_post_validation",
            policy["unproven_controls"],
        )

    def test_real_launcher_captures_both_streams_and_rejects_excess(self) -> None:
        policy = proof.load_policy()
        result = proof.prove(REPO_ROOT, policy)
        dual, limit = result["fixtures"]

        self.assertEqual(
            "verified_enforcement",
            result["control_assessments"][0]["assessment"],
        )
        self.assertTrue(dual["matched"])
        self.assertEqual(
            policy["fixtures"]["dual_stream"]["stdout_bytes"],
            dual["stdout_bytes"],
        )
        self.assertEqual(
            policy["fixtures"]["dual_stream"]["stderr_bytes"],
            dual["stderr_bytes"],
        )
        self.assertTrue(limit["matched"])
        self.assertTrue(limit["output_limit_exceeded"])
        self.assertTrue(limit["direct_child_reaped"])
        self.assertFalse(limit["partial_output_returned"])
        self.assertLessEqual(
            limit["captured_bytes_before_rejection"],
            limit["configured_capture_limit_bytes"],
        )
        self.assertFalse(result["scope"]["validates_implementation_output"])
        for field in proof.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_incomplete_capture_and_unenforced_limit_fail_closed(self) -> None:
        policy = proof.load_policy()
        dual = {
            "completed": True,
            "timed_out": False,
            "output_limit_exceeded": False,
            "kill_requested": False,
            "direct_child_reaped": True,
            "returncode": 0,
            "stdout": b"",
            "stderr": b"",
            "capture_complete": False,
            "captured_stdout_bytes": 0,
            "captured_stderr_bytes": 0,
            "capture_memory_bound_bytes": 1,
        }
        limit = {
            "completed": True,
            "timed_out": False,
            "output_limit_exceeded": False,
            "kill_requested": False,
            "direct_child_reaped": True,
            "returncode": 0,
            "stdout": b"x",
            "stderr": b"",
            "capture_complete": True,
            "captured_stdout_bytes": 1,
            "captured_stderr_bytes": 0,
            "capture_memory_bound_bytes": 1,
        }
        executions = [dual, limit]

        result = proof.prove(
            REPO_ROOT,
            policy,
            lambda *_args, **_kwargs: executions.pop(0),
        )

        self.assertEqual(
            "not_proven",
            result["control_assessments"][0]["assessment"],
        )
        self.assertFalse(any(fixture["matched"] for fixture in result["fixtures"]))

    def test_policy_drift_and_cli_override_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "policy.json"
            value = json.loads(json.dumps(proof.EXPECTED_POLICY))
            value["unproven_controls"].remove("runner_enforced_output_post_validation")
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
                "untrusted",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, completed.returncode)
        self.assertIn("unrecognized arguments", completed.stderr)

    def test_real_cli_preserves_repository_state(self) -> None:
        status_command = [
            "git",
            "-c",
            f"safe.directory={REPO_ROOT.as_posix()}",
            "-C",
            str(REPO_ROOT),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ]
        before = subprocess.run(
            status_command,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
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
        after = subprocess.run(
            status_command,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        result = json.loads(completed.stdout)

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(before, after)
        self.assertEqual(
            "verified_enforcement",
            result["control_assessments"][0]["assessment"],
        )


if __name__ == "__main__":
    unittest.main()
