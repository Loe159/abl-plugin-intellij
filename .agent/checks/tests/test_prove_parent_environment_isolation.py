from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "prove_parent_environment_isolation.py"
REPO_ROOT = CHECKS_DIR.parents[1]
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location(
    "prove_parent_environment_isolation",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
proof = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = proof
SPEC.loader.exec_module(proof)


class ParentEnvironmentIsolationProofTest(unittest.TestCase):
    def test_policy_is_exact_and_scope_excludes_provider_descendants(self) -> None:
        policy = proof.load_policy()

        self.assertEqual("enforcement-proof", policy["mode"])
        self.assertEqual(
            "parent_environment_credential_isolation",
            policy["proven_control"],
        )
        self.assertIn(
            "provider_credential_descendant_noninheritance",
            policy["unproven_controls"],
        )

    def test_real_launcher_excludes_every_sensitive_name_without_returning_values(self) -> None:
        policy = proof.load_policy()
        result = proof.prove(
            REPO_ROOT,
            policy,
            {"PATH": "allowed-path"},
        )

        self.assertEqual(
            "verified_enforcement",
            result["control_assessments"][0]["assessment"],
        )
        self.assertEqual([], result["observation"]["sensitive_names_present"])
        self.assertEqual(
            policy["required_child_variables"],
            result["observation"]["required_names_present"],
        )
        self.assertEqual(
            len(policy["sensitive_variable_names"]),
            result["observation"]["sensitive_names_tested"],
        )
        self.assertFalse(result["scope"]["provider_descendant_boundary_tested"])
        self.assertNotIn("synthetic-isolation-marker", json.dumps(result))
        for field in proof.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_malformed_output_sensitive_leak_and_timeout_fail_closed(self) -> None:
        policy = proof.load_policy()
        scenarios = [
            {
                "completed": True,
                "timed_out": False,
                "returncode": 0,
                "stdout": b"not-json",
                "stderr": b"",
                "capture_complete": True,
                "output_limit_exceeded": False,
                "kill_requested": False,
                "direct_child_reaped": True,
            },
            {
                "completed": True,
                "timed_out": False,
                "returncode": 0,
                "stdout": json.dumps(
                    {
                        "sensitive_present": ["GITHUB_TOKEN"],
                        "required_present": policy["required_child_variables"],
                        "mode": policy["expected_child_environment_mode"],
                    }
                ).encode(),
                "stderr": b"",
                "capture_complete": True,
                "output_limit_exceeded": False,
                "kill_requested": False,
                "direct_child_reaped": True,
            },
            {
                "completed": False,
                "timed_out": True,
                "returncode": None,
                "stdout": b"",
                "stderr": b"",
                "capture_complete": False,
                "output_limit_exceeded": False,
                "kill_requested": True,
                "direct_child_reaped": True,
            },
        ]
        for execution in scenarios:
            with self.subTest():
                result = proof.prove(
                    REPO_ROOT,
                    policy,
                    {},
                    lambda *_args, **_kwargs: execution,
                )
                self.assertEqual(
                    "not_proven",
                    result["control_assessments"][0]["assessment"],
                )

    def test_policy_drift_and_cli_override_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "policy.json"
            value = json.loads(json.dumps(proof.EXPECTED_POLICY))
            value["unproven_controls"].remove(
                "provider_credential_descendant_noninheritance"
            )
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
        before = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={REPO_ROOT.as_posix()}",
                "-C",
                str(REPO_ROOT),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ],
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
            [
                "git",
                "-c",
                f"safe.directory={REPO_ROOT.as_posix()}",
                "-C",
                str(REPO_ROOT),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ],
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
