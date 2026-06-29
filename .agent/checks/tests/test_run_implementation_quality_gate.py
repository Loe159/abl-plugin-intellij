from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "run_implementation_quality_gate.py"
REPO_ROOT = CHECKS_DIR.parents[1]
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location(
    "run_implementation_quality_gate",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def candidate(root: Path, changed: bool = True) -> dict[str, object]:
    workspace = root / "workspace"
    workspace.mkdir()
    git(workspace, "init")
    git(workspace, "config", "user.email", "test@example.invalid")
    git(workspace, "config", "user.name", "Test Fixture")
    (workspace / "app.txt").write_text("base\n", encoding="utf-8")
    (workspace / "gradlew.bat").write_text("@echo off\r\nexit /b 0\r\n", encoding="ascii")
    git(workspace, "add", "app.txt", "gradlew.bat")
    git(workspace, "commit", "-m", "base")
    base = git(workspace, "rev-parse", "HEAD")
    if changed:
        (workspace / "app.txt").write_text("base\nchange\n", encoding="utf-8")
    workspace = workspace.resolve()
    identity = {
        "issue": 61,
        "risk": "medium",
        "base_commit": base,
        "workspace": str(workspace),
        "runner_id": "quality-gate-test-runner",
        "preflight_sha256": "2" * 64,
        "start_authorization_receipt_sha256": "3" * 64,
    }
    result_value = {
        "result_version": 1,
        "purpose": "implementation_session_result",
        "mode": "untrusted-runner-output",
        "status": "completed",
        **identity,
        "summary": "Completed fixture.",
        "workspace_changed": True,
        "patch_generated": False,
        "deterministic_checks_run": False,
        "publication_requested": False,
        "network_requested": False,
        "next_action": "deterministic_patch_generation",
    }
    result_path = root / "result.json"
    session_path = root / "session.json"
    patch = root / "candidate.patch"
    patch_receipt = root / "patch-receipt.json"
    result_path.write_bytes(
        gate.validate_implementation_result.canonical_result_bytes(result_value)
    )
    session_path.write_text(
        json.dumps(identity, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    produced = gate.validate_implementation_patch.validate_patch(
        REPO_ROOT,
        gate.validate_implementation_patch.captured_execution(
            result_path.read_bytes(),
            b"",
        ),
        identity,
        patch,
        patch_receipt,
        gate.validate_implementation_patch.load_policy(),
    )
    return {
        "workspace": workspace,
        "result": result_path,
        "session": session_path,
        "patch": patch,
        "patch_receipt": patch_receipt,
        "patch_receipt_sha256": produced["receipt_sha256"],
        "gate_receipt": root / "quality-gate.json",
        "gradle_user_home": root / "gradle-home",
    }


def environment() -> dict[str, str]:
    return {
        "ALLUSERSPROFILE": os.environ.get("ALLUSERSPROFILE", r"C:\ProgramData"),
        "COMSPEC": os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"),
        "PATH": os.environ.get("PATH", ""),
        "PROGRAMDATA": os.environ.get("PROGRAMDATA", r"C:\ProgramData"),
        "SYSTEMDRIVE": os.environ.get("SYSTEMDRIVE", "C:"),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
        "WINDIR": os.environ.get("WINDIR", r"C:\Windows"),
        "SECRET_TOKEN": "must-not-be-inherited",
    }


def fixture_python() -> str:
    candidate = Path(sys.prefix) / "python.exe"
    return str(candidate.resolve() if candidate.is_file() else Path(sys.executable).resolve())


def execution(returncode: int = 0) -> dict[str, object]:
    return {
        "completed": True,
        "timed_out": False,
        "output_limit_exceeded": False,
        "tree_kill_requested": False,
        "tree_kill_returncode": None,
        "direct_kill_requested": False,
        "root_reaped": True,
        "returncode": returncode,
        "capture_complete": True,
        "stdout": b"out",
        "stderr": b"",
        "captured_stdout_bytes": 3,
        "captured_stderr_bytes": 0,
        "duration_seconds": 0.01,
    }


def invoke(
    item: dict[str, object],
    runner: object,
) -> dict[str, object]:
    distribution = (
        item["gradle_user_home"]
        / "wrapper"
        / "dists"
        / "gradle-8.11.1-bin"
        / "fixture"
        / "gradle-8.11.1"
        / "bin"
    )
    distribution.mkdir(parents=True, exist_ok=True)
    (distribution / "gradle.bat").write_text("@echo off\r\n", encoding="ascii")
    return gate.execute(
        REPO_ROOT,
        item["result"],
        item["session"],
        item["patch"],
        item["patch_receipt"],
        item["patch_receipt_sha256"],
        item["gate_receipt"],
        item["gradle_user_home"],
        gate.load_policy(),
        parent_environment=environment(),
        which=lambda _name: r"C:\Windows\System32\taskkill.exe",
        command_runner=runner,
    )


class RunImplementationQualityGateTest(unittest.TestCase):
    def test_policy_is_exact_offline_bounded_and_non_authorizing(self) -> None:
        policy = gate.load_policy()

        self.assertEqual(gate.EXPECTED_POLICY, policy)
        self.assertIn("--offline", policy["fixed_arguments"])
        self.assertEqual("taskkill", policy["tree_terminator"])
        self.assertFalse(policy["network_requested"])

    def test_windows_app_execution_alias_commands_are_rejected(self) -> None:
        policy = gate.load_policy()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / "gradlew.bat").write_text("@echo off\r\n", encoding="ascii")
            alias = (
                root
                / "AppData"
                / "Local"
                / "Microsoft"
                / "WindowsApps"
                / "python.exe"
            )
            alias.parent.mkdir(parents=True)
            alias.write_text("", encoding="ascii")

            with self.assertRaisesRegex(ValueError, "Windows App Execution Alias"):
                gate.exact_gradle_command(
                    workspace,
                    ["test"],
                    {"COMSPEC": str(alias)},
                    policy,
                )
            with self.assertRaisesRegex(ValueError, "Windows App Execution Alias"):
                gate.run_bounded(
                    [str(alias), "-V"],
                    REPO_ROOT,
                    environment(),
                    policy,
                    1.0,
                    r"C:\Windows\System32\taskkill.exe",
                    popen=mock.Mock(side_effect=AssertionError("must not spawn")),
                )

    def test_exact_candidate_runs_all_commands_and_writes_pass_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            item = candidate(Path(temp_dir))
            runner = mock.Mock(return_value=execution())

            result = invoke(item, runner)
            receipt = json.loads(item["gate_receipt"].read_text(encoding="utf-8"))

        self.assertTrue(result["execution_attempted"])
        self.assertTrue(result["quality_gate_passed"])
        self.assertTrue(result["receipt_written"])
        self.assertEqual(3, runner.call_count)
        self.assertTrue(all(record["status"] == "passed" for record in result["commands"]))
        self.assertFalse(receipt["network_requested"])
        self.assertFalse(receipt["publication_authorized"])
        first_command = runner.call_args_list[0].args[0]
        self.assertEqual("call", first_command[4])
        self.assertEqual("gradlew.bat", first_command[5])
        self.assertEqual(["ktlintCheck", "detekt"], first_command[6:8])
        self.assertNotIn("SECRET_TOKEN", runner.call_args_list[0].args[2])

    def test_failed_first_command_writes_failed_receipt_and_stops(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            item = candidate(Path(temp_dir))
            runner = mock.Mock(return_value=execution(1))

            result = invoke(item, runner)

        self.assertFalse(result["quality_gate_passed"])
        self.assertTrue(result["receipt_written"])
        self.assertEqual(1, runner.call_count)
        self.assertEqual(
            ["failed", "not_run", "not_run"],
            [record["status"] for record in result["commands"]],
        )

    def test_empty_patch_blocks_before_process_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            item = candidate(Path(temp_dir), changed=False)
            runner = mock.Mock()

            result = invoke(item, runner)

        self.assertFalse(result["execution_attempted"])
        self.assertFalse(result["receipt_written"])
        self.assertEqual("patch_candidate", result["failures"][0]["rule"])
        runner.assert_not_called()

    def test_workspace_git_drift_fails_without_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            item = candidate(Path(temp_dir))

            def drifting_runner(*_args: object) -> dict[str, object]:
                (item["workspace"] / "drift.txt").write_text("drift\n", encoding="utf-8")
                return execution()

            with self.assertRaisesRegex(ValueError, "Git state changed"):
                invoke(item, drifting_runner)
            self.assertFalse(item["gate_receipt"].exists())

    def test_input_drift_and_receipt_write_failure_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            item = candidate(Path(temp_dir))
            original = item["result"].read_bytes()
            changed = False

            def drifting_runner(*_args: object) -> dict[str, object]:
                nonlocal changed
                if not changed:
                    item["result"].write_bytes(original + b"\n")
                    changed = True
                return execution()

            with self.assertRaisesRegex(ValueError, "inputs or trusted bindings changed"):
                invoke(item, drifting_runner)
            self.assertFalse(item["gate_receipt"].exists())

        with tempfile.TemporaryDirectory() as temp_dir:
            item = candidate(Path(temp_dir))

            def partial_write(path: Path, _content: bytes) -> None:
                path.write_bytes(b"partial")
                raise OSError("synthetic receipt failure")

            with mock.patch.object(
                gate.validate_implementation_patch,
                "write_exclusive",
                side_effect=partial_write,
            ):
                with self.assertRaisesRegex(OSError, "synthetic receipt failure"):
                    invoke(item, mock.Mock(return_value=execution()))
            self.assertFalse(item["gate_receipt"].exists())

    def test_receipt_boundaries_policy_drift_and_cli_override_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            item = candidate(Path(temp_dir))
            item["gate_receipt"] = item["workspace"] / "quality-gate.json"
            with self.assertRaisesRegex(ValueError, "outside the workspace"):
                invoke(item, mock.Mock(return_value=execution()))

            empty_gradle_home = Path(temp_dir) / "empty-gradle-home"
            empty_gradle_home.mkdir()
            runner = mock.Mock()
            with self.assertRaisesRegex(ValueError, "distribution is not cached"):
                gate.execute(
                    REPO_ROOT,
                    item["result"],
                    item["session"],
                    item["patch"],
                    item["patch_receipt"],
                    item["patch_receipt_sha256"],
                    Path(temp_dir) / "external-receipt.json",
                    empty_gradle_home,
                    gate.load_policy(),
                    parent_environment=environment(),
                    which=lambda _name: r"C:\Windows\System32\taskkill.exe",
                    command_runner=runner,
                )
            runner.assert_not_called()

            path = Path(temp_dir) / "policy.json"
            policy = json.loads(json.dumps(gate.EXPECTED_POLICY))
            policy["network_requested"] = True
            path.write_text(json.dumps(policy), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match"):
                gate.load_policy(path)

        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--repo",
                str(REPO_ROOT),
                "--result",
                "result.json",
                "--expected-session",
                "session.json",
                "--patch",
                "patch.diff",
                "--patch-receipt",
                "patch-receipt.json",
                "--patch-receipt-sha256",
                "0" * 64,
                "--receipt-output",
                "quality-gate.json",
                "--gradle-user-home",
                "gradle-home",
                "--policy",
                "untrusted.json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, completed.returncode)
        self.assertIn("unrecognized arguments", completed.stderr)

    @unittest.skipUnless(os.name == "nt", "Windows process-tree fixture")
    def test_bounded_runner_captures_output_and_kills_timeout_tree(self) -> None:
        taskkill = shutil.which("taskkill")
        self.assertIsNotNone(taskkill)
        policy = json.loads(json.dumps(gate.load_policy()))
        policy["max_captured_output_bytes"] = 65536
        policy["capture_chunk_bytes"] = 4096
        policy["cleanup_timeout_seconds"] = 3.0
        command = [
            fixture_python(),
            "-I",
            "-S",
            "-B",
            "-c",
            "import sys;sys.stdout.write('ok');sys.stderr.write('err')",
        ]
        success = gate.run_bounded(
            command,
            REPO_ROOT,
            environment(),
            policy,
            3.0,
            taskkill,
        )
        timeout = gate.run_bounded(
            [
                fixture_python(),
                "-I",
                "-S",
                "-B",
                "-c",
                "import time;time.sleep(10)",
            ],
            REPO_ROOT,
            environment(),
            policy,
            0.2,
            taskkill,
        )

        self.assertTrue(success["completed"])
        self.assertEqual(b"ok", success["stdout"])
        self.assertEqual(b"err", success["stderr"])
        self.assertTrue(timeout["timed_out"])
        self.assertTrue(timeout["tree_kill_requested"])
        self.assertTrue(timeout["root_reaped"])
        self.assertTrue(
            timeout["tree_kill_returncode"] == 0
            or timeout["direct_kill_requested"]
        )

        policy["cleanup_timeout_seconds"] = 0.2
        taskkill_error = gate.run_bounded(
            [
                fixture_python(),
                "-I",
                "-S",
                "-B",
                "-c",
                "import time;time.sleep(10)",
            ],
            REPO_ROOT,
            environment(),
            policy,
            0.1,
            taskkill,
            run=mock.Mock(side_effect=OSError("synthetic taskkill failure")),
        )
        self.assertTrue(taskkill_error["tree_kill_requested"])
        self.assertIsNone(taskkill_error["tree_kill_returncode"])
        self.assertTrue(taskkill_error["direct_kill_requested"])
        self.assertTrue(taskkill_error["root_reaped"])


if __name__ == "__main__":
    unittest.main()
