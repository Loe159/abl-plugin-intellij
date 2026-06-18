from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "prove_wall_clock_timeout.py"
REPO_ROOT = CHECKS_DIR.parents[1]
SPEC = importlib.util.spec_from_file_location("prove_wall_clock_timeout", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
proof = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = proof
SPEC.loader.exec_module(proof)


class FakeProcess:
    def __init__(self, waits: list[object]) -> None:
        self.waits = waits
        self.killed = False

    def wait(self, timeout: float) -> int:
        value = self.waits.pop(0)
        if isinstance(value, BaseException):
            raise value
        return int(value)

    def kill(self) -> None:
        self.killed = True


class Clock:
    def __init__(self, values: list[float]) -> None:
        self.values = values

    def __call__(self) -> float:
        return self.values.pop(0)


class WallClockTimeoutProofTest(unittest.TestCase):
    def test_repository_policy_is_exact_fixture_only_and_non_invoking(self) -> None:
        policy = proof.load_policy()

        self.assertEqual(proof.EXPECTED_POLICY, policy)
        self.assertEqual("fixture-only", policy["mode"])
        self.assertNotIn("codex", json.dumps(policy).lower())
        self.assertEqual(
            ["post_spawn_direct_child_timeout"],
            [policy["proven_control"]],
        )

    def test_positive_and_negative_fixture_verify_only_direct_child_timeout(self) -> None:
        processes = [
            FakeProcess([0]),
            FakeProcess([subprocess.TimeoutExpired(["python"], 0.5), -9]),
        ]
        invocations: list[tuple[tuple[object, ...], dict[str, object]]] = []

        def popen(*args: object, **kwargs: object) -> FakeProcess:
            invocations.append((args, kwargs))
            return processes.pop(0)

        result = proof.prove(
            REPO_ROOT,
            proof.load_policy(),
            popen,
            Clock([1.0, 1.1, 2.0, 2.6]),
        )

        self.assertEqual("verified_fixture", result["control_assessments"][0]["assessment"])
        self.assertTrue(result["scope"]["direct_child_only"])
        self.assertTrue(result["scope"]["starts_after_process_spawn"])
        self.assertTrue(
            all(item["assessment"] == "not_proven" for item in result["control_assessments"][1:])
        )
        self.assertTrue(all(invocation[1]["shell"] is False for invocation in invocations))
        self.assertTrue(all(invocation[1]["stdout"] == subprocess.DEVNULL for invocation in invocations))
        self.assertTrue(all(invocation[1]["stderr"] == subprocess.DEVNULL for invocation in invocations))
        self.assertTrue(all(invocation[1]["stdin"] == subprocess.DEVNULL for invocation in invocations))
        self.assertTrue(all(invocation[0][0][1:4] == ["-I", "-S", "-B"] for invocation in invocations))
        for field in proof.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_missing_timeout_and_cleanup_failure_do_not_verify(self) -> None:
        scenarios = [
            [
                FakeProcess([0]),
                FakeProcess([0]),
            ],
            [
                FakeProcess([0]),
                FakeProcess(
                    [
                        subprocess.TimeoutExpired(["python"], 0.5),
                        subprocess.TimeoutExpired(["python"], 2.0),
                    ]
                ),
            ],
        ]
        for processes in scenarios:
            with self.subTest():
                result = proof.prove(
                    REPO_ROOT,
                    proof.load_policy(),
                    lambda *_args, **_kwargs: processes.pop(0),
                    Clock([1.0, 1.1, 2.0, 2.6]),
                )

                self.assertEqual("not_proven", result["control_assessments"][0]["assessment"])
                self.assertFalse(result["runner_selected"])

    def test_observed_bound_and_spawn_error_fail_closed(self) -> None:
        processes = [
            FakeProcess([0]),
            FakeProcess([subprocess.TimeoutExpired(["python"], 0.5), -9]),
        ]
        slow = proof.prove(
            REPO_ROOT,
            proof.load_policy(),
            lambda *_args, **_kwargs: processes.pop(0),
            Clock([1.0, 5.0, 6.0, 10.0]),
        )
        spawned = 0

        def failing_popen(*_: object, **__: object) -> FakeProcess:
            nonlocal spawned
            spawned += 1
            raise OSError("not returned")

        failed = proof.prove(REPO_ROOT, proof.load_policy(), failing_popen)

        self.assertEqual("not_proven", slow["control_assessments"][0]["assessment"])
        self.assertEqual("not_proven", failed["control_assessments"][0]["assessment"])
        self.assertEqual(2, spawned)
        self.assertTrue(all(item["observation"] == "spawn_error" for item in failed["fixtures"]))

    def test_policy_drift_and_cli_override_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "policy.json"
            policy = json.loads(json.dumps(proof.EXPECTED_POLICY))
            policy["unproven_controls"].remove("implementation_session_wall_clock_timeout")
            path.write_text(json.dumps(policy), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "fixture-only contract"):
                proof.load_policy(path)

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

    def test_real_cli_verifies_fixture_without_mutating_repo(self) -> None:
        before = subprocess.run(
            ["git", "-c", f"safe.directory={REPO_ROOT.as_posix()}", "-C", str(REPO_ROOT), "status", "--porcelain=v1", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        completed = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--repo", str(REPO_ROOT), "--format", "json"],
            check=False,
            capture_output=True,
            text=True,
        )
        after = subprocess.run(
            ["git", "-c", f"safe.directory={REPO_ROOT.as_posix()}", "-C", str(REPO_ROOT), "status", "--porcelain=v1", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        result = json.loads(completed.stdout)

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(before, after)
        self.assertEqual("verified_fixture", result["control_assessments"][0]["assessment"])
        self.assertEqual(
            "not_proven",
            next(
                item["assessment"]
                for item in result["control_assessments"]
                if item["id"] == "implementation_session_wall_clock_timeout"
            ),
        )


if __name__ == "__main__":
    unittest.main()
