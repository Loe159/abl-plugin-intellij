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
MODULE_PATH = CHECKS_DIR / "isolated_process.py"
SPEC = importlib.util.spec_from_file_location("isolated_process", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
isolated = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = isolated
SPEC.loader.exec_module(isolated)


def fixture_python() -> str:
    candidate = Path(sys.prefix) / "python.exe"
    return str(candidate.resolve() if candidate.is_file() else Path(sys.executable).resolve())


class IsolatedProcessTest(unittest.TestCase):
    def test_policy_is_exact_and_environment_is_reconstructed(self) -> None:
        policy = isolated.load_policy()
        self.assertGreaterEqual(policy["max_timeout_seconds"], 600.0)
        class GuardedEnvironment(dict[str, str]):
            def __getitem__(self, name: str) -> str:
                if name in {"GITHUB_TOKEN", "OPENAI_API_KEY"}:
                    raise AssertionError("Rejected environment value was read")
                return super().__getitem__(name)

        parent = GuardedEnvironment(
            {
                "PATH": "allowed-path",
                "GITHUB_TOKEN": "synthetic-marker",
                "OPENAI_API_KEY": "synthetic-marker",
            }
        )

        child = isolated.build_child_environment(parent, policy)

        self.assertEqual("allowed-path", child["PATH"])
        self.assertEqual("isolated", child["AGENT_RUNNER_ENVIRONMENT_MODE"])
        self.assertNotIn("GITHUB_TOKEN", child)
        self.assertNotIn("OPENAI_API_KEY", child)
        self.assertEqual(
            set(child),
            {"PATH", *policy["fixed_child_environment"]},
        )

    def test_duplicate_case_insensitive_names_and_relative_executable_are_rejected(self) -> None:
        policy = isolated.load_policy()
        with self.assertRaisesRegex(ValueError, "duplicate case-insensitive"):
            isolated.build_child_environment({"Path": "one", "PATH": "two"}, policy)
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "absolute path"):
                isolated.validate_command(["python", "-V"], Path(temp_dir), policy)

    def test_windows_app_execution_alias_executable_is_rejected(self) -> None:
        policy = isolated.load_policy()
        with tempfile.TemporaryDirectory() as temp_dir:
            alias = (
                Path(temp_dir)
                / "AppData"
                / "Local"
                / "Microsoft"
                / "WindowsApps"
                / "python.exe"
            )
            alias.parent.mkdir(parents=True)
            alias.write_text("", encoding="ascii")

            with self.assertRaisesRegex(ValueError, "Windows App Execution Alias"):
                isolated.validate_command([str(alias), "-V"], Path(temp_dir), policy)

    def test_run_uses_exact_non_shell_bounded_process_contract(self) -> None:
        policy = isolated.load_policy()
        observed: dict[str, object] = {}

        class Process:
            def __init__(self) -> None:
                self.stdout = io.BytesIO(b"ok")
                self.stderr = io.BytesIO(b"")

            def wait(self, timeout: float) -> int:
                return 0

            def kill(self) -> None:
                raise AssertionError("Successful process must not be killed")

        def popen(command: list[str], **kwargs: object) -> Process:
            observed.update(command=command, **kwargs)
            return Process()

        result = isolated.run(
            [fixture_python(), "-V"],
            CHECKS_DIR,
            {"PATH": "allowed", "GH_TOKEN": "synthetic-marker"},
            policy,
            1.0,
            popen,
        )

        self.assertTrue(result["completed"])
        self.assertEqual(b"ok", result["stdout"])
        self.assertIs(observed["stdin"], subprocess.DEVNULL)
        self.assertIs(observed["stdout"], subprocess.PIPE)
        self.assertIs(observed["stderr"], subprocess.PIPE)
        self.assertFalse(observed["shell"])
        self.assertNotIn("GH_TOKEN", observed["env"])
        self.assertTrue(result["capture_complete"])

    def test_timeout_and_output_limit_fail_closed(self) -> None:
        policy = isolated.load_policy()
        timed_out = isolated.run(
            [
                fixture_python(),
                "-I",
                "-S",
                "-B",
                "-c",
                "import time; time.sleep(10)",
            ],
            CHECKS_DIR,
            {},
            policy,
            0.1,
        )
        oversized = isolated.run(
            [
                fixture_python(),
                "-I",
                "-S",
                "-B",
                "-c",
                f"import sys; sys.stdout.write('x'*{policy['max_captured_output_bytes'] + 1})",
            ],
            CHECKS_DIR,
            {},
            policy,
            1.0,
        )

        self.assertTrue(timed_out["timed_out"])
        self.assertFalse(timed_out["completed"])
        self.assertTrue(timed_out["kill_requested"])
        self.assertTrue(timed_out["direct_child_reaped"])
        self.assertTrue(oversized["output_limit_exceeded"])
        self.assertTrue(oversized["kill_requested"])
        self.assertFalse(oversized["capture_complete"])
        self.assertEqual(b"", oversized["stdout"])

    def test_timeout_still_applies_after_child_closes_both_streams(self) -> None:
        policy = isolated.load_policy()
        result = isolated.run(
            [
                fixture_python(),
                "-I",
                "-S",
                "-B",
                "-c",
                (
                    "import os,time;"
                    "os.close(1);"
                    "os.close(2);"
                    "time.sleep(10)"
                ),
            ],
            CHECKS_DIR,
            {},
            policy,
            0.1,
        )

        self.assertTrue(result["timed_out"])
        self.assertTrue(result["kill_requested"])
        self.assertTrue(result["direct_child_reaped"])
        self.assertFalse(result["capture_complete"])

    def test_policy_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "policy.json"
            value = json.loads(json.dumps(isolated.EXPECTED_POLICY))
            value["allowed_parent_variables"].append("GITHUB_TOKEN")
            path.write_text(json.dumps(value), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "does not match"):
                isolated.load_policy(path)


if __name__ == "__main__":
    unittest.main()
