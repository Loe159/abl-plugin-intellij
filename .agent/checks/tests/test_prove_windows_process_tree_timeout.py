from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "prove_windows_process_tree_timeout.py"
REPO_ROOT = CHECKS_DIR.parents[1]
SPEC = importlib.util.spec_from_file_location("prove_windows_process_tree_timeout", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
proof = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = proof
SPEC.loader.exec_module(proof)


class FakeRoot:
    def __init__(self) -> None:
        self.pid = 100
        self.stdout = io.BytesIO(b"101 102\n")
        self.waits: list[object] = [subprocess.TimeoutExpired(["python"], 0.5), 1]

    def wait(self, timeout: float) -> int:
        value = self.waits.pop(0)
        if isinstance(value, BaseException):
            raise value
        return int(value)

    def poll(self) -> int:
        return 1


class FakeHandle:
    def __init__(self, pid: int, running: bool = True, terminated: bool = True) -> None:
        self.pid = pid
        self.running = running
        self.terminated = terminated
        self.closed = False

    def is_running(self) -> bool:
        return self.running

    def wait_terminated(self, timeout_seconds: float) -> bool:
        return self.terminated

    def close(self) -> None:
        self.closed = True


class WindowsProcessTreeTimeoutProofTest(unittest.TestCase):
    def test_repository_policy_is_exact_fixture_only_and_non_invoking(self) -> None:
        policy = proof.load_policy()

        self.assertEqual(proof.EXPECTED_POLICY, policy)
        self.assertEqual("fixture-only", policy["mode"])
        self.assertEqual(2, policy["fixture"]["descendant_depth"])
        self.assertEqual(["/PID", "{root_pid}", "/T", "/F"], policy["tree_terminator_arguments"])
        self.assertNotIn("codex", json.dumps(policy).lower())

    def test_observe_fixture_requires_exact_tree_cleanup_evidence(self) -> None:
        root = FakeRoot()
        handles = {101: FakeHandle(101), 102: FakeHandle(102)}
        invocations: list[tuple[list[str], dict[str, object]]] = []

        def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            invocations.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0, stdout=b"not returned", stderr=b"")

        result = proof.observe_fixture(
            REPO_ROOT,
            proof.load_policy(),
            "taskkill.exe",
            lambda *_args, **_kwargs: root,
            run,
            lambda pid: handles[pid],
            iter([1.0, 1.7]).__next__,
        )

        self.assertTrue(result["matched"])
        self.assertEqual("tree_timed_out_and_reaped", result["observation"])
        self.assertTrue(result["child_observed_running_before_kill"])
        self.assertTrue(result["grandchild_observed_running_before_kill"])
        self.assertTrue(result["child_terminated_after_kill"])
        self.assertTrue(result["grandchild_terminated_after_kill"])
        self.assertEqual(["taskkill.exe", "/PID", "100", "/T", "/F"], invocations[0][0])
        self.assertIs(False, invocations[0][1]["shell"])
        self.assertTrue(all(handle.closed for handle in handles.values()))
        self.assertTrue(root.stdout.closed)
        self.assertNotIn("not returned", json.dumps(result))

    def test_nonzero_taskkill_or_missing_descendant_fails_closed(self) -> None:
        for returncode, running, clock_values in [
            (1, True, [1.0, 1.7]),
            (0, False, [1.0, 1.7]),
            (0, True, [1.0, 8.0]),
        ]:
            with self.subTest(returncode=returncode, running=running, clock=clock_values):
                root = FakeRoot()
                handles = {101: FakeHandle(101, running=running), 102: FakeHandle(102)}
                result = proof.observe_fixture(
                    REPO_ROOT,
                    proof.load_policy(),
                    "taskkill.exe",
                    lambda *_args, **_kwargs: root,
                    lambda command, **_kwargs: subprocess.CompletedProcess(
                        command,
                        returncode,
                        stdout=b"",
                        stderr=b"",
                    ),
                    lambda pid: handles[pid],
                    iter(clock_values).__next__,
                )

                self.assertFalse(result["matched"])

    def test_prove_verifies_only_the_exact_fixture(self) -> None:
        matched = proof.base_observation("tree_timed_out_and_reaped")
        matched["matched"] = True
        result = proof.prove(
            REPO_ROOT,
            proof.load_policy(),
            "Windows",
            lambda _name: "taskkill.exe",
            lambda *_args: matched,
        )

        self.assertEqual("verified_fixture", result["control_assessments"][0]["assessment"])
        self.assertTrue(
            all(item["assessment"] == "not_proven" for item in result["control_assessments"][1:])
        )
        for field in proof.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_unsupported_environment_and_unmatched_fixture_do_not_verify(self) -> None:
        called = False

        def fixture_runner(*_args: object) -> dict[str, object]:
            nonlocal called
            called = True
            return proof.base_observation("unexpected")

        unsupported = proof.prove(
            REPO_ROOT,
            proof.load_policy(),
            "Linux",
            lambda _name: "taskkill",
            fixture_runner,
        )
        missing = proof.prove(
            REPO_ROOT,
            proof.load_policy(),
            "Windows",
            lambda _name: None,
            fixture_runner,
        )
        unmatched = proof.prove(
            REPO_ROOT,
            proof.load_policy(),
            "Windows",
            lambda _name: "taskkill.exe",
            fixture_runner,
        )

        self.assertEqual("not_proven", unsupported["control_assessments"][0]["assessment"])
        self.assertEqual("unsupported_environment", unsupported["fixture"]["observation"])
        self.assertEqual("not_proven", missing["control_assessments"][0]["assessment"])
        self.assertEqual("unsupported_environment", missing["fixture"]["observation"])
        self.assertEqual("not_proven", unmatched["control_assessments"][0]["assessment"])
        self.assertTrue(called)

    def test_policy_drift_and_cli_override_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "policy.json"
            policy = json.loads(json.dumps(proof.EXPECTED_POLICY))
            policy["tree_terminator_arguments"].remove("/T")
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
            [sys.executable, str(MODULE_PATH), "--repo", str(REPO_ROOT), "--format", "json"],
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
