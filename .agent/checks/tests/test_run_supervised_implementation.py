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
MODULE_PATH = CHECKS_DIR / "run_supervised_implementation.py"
REPO_ROOT = CHECKS_DIR.parents[1]
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location("run_supervised_implementation", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)
import test_approve_implementation_session as approval_helpers
import test_authorize_implementation_session_start as authorization_helpers


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def authorized(temp: Path) -> tuple[object, ...]:
    return authorization_helpers.write_authorization(temp)


def outputs(temp: Path) -> dict[str, Path]:
    out = temp / "out"
    out.mkdir(parents=True)
    return {
        "expected_session": out / "expected-session.json",
        "result": out / "result.json",
        "patch": out / "patch.diff",
        "patch_receipt": out / "patch-receipt.json",
        "quality_gate": out / "quality-gate.json",
        "final": out / "final-receipt.json",
        "cleanup": out / "cleanup-receipt.json",
        "gradle_home": out / "gradle-home",
    }


def allowed_adapter_command() -> list[str]:
    return [
        sys.executable,
        str(REPO_ROOT / ".agent" / "adapters" / "local_implementation_adapter.py"),
    ]


def result_bytes(session: dict[str, object], changed: bool = True) -> bytes:
    return runner.validate_implementation_result.canonical_result_bytes(
        {
            "result_version": 1,
            "purpose": "implementation_session_result",
            "mode": "untrusted-runner-output",
            "status": "completed",
            **session,
            "summary": "Completed fixture.",
            "workspace_changed": changed,
            "patch_generated": False,
            "deterministic_checks_run": False,
            "publication_requested": False,
            "network_requested": False,
            "next_action": "deterministic_patch_generation",
        }
    )


def execution(stdout: bytes) -> dict[str, object]:
    return {
        "completed": True,
        "timed_out": False,
        "output_limit_exceeded": False,
        "kill_requested": False,
        "direct_child_reaped": True,
        "returncode": 0,
        "stdout": stdout,
        "stderr": b"",
        "capture_complete": True,
        "captured_stdout_bytes": len(stdout),
        "captured_stderr_bytes": 0,
    }


def gate_pass(
    _source: Path,
    _result: Path,
    _session: Path,
    _patch: Path,
    _patch_receipt: Path,
    _patch_receipt_sha256: str,
    quality_gate_receipt: Path,
    _gradle_user_home: Path,
    _policy: dict[str, object],
    **_kwargs: object,
) -> dict[str, object]:
    value = {
        "quality_gate_receipt_version": 1,
        "purpose": "implementation_quality_gate_execution",
        "mode": "controlled-gradle-execution-only",
        **{field: False for field in runner.run_implementation_quality_gate.FALSE_FIELDS},
        "execution_attempted": True,
        "quality_gate_passed": True,
        "network_requested": False,
        "identity": {},
        "patch_receipt_sha256": _patch_receipt_sha256,
        "patch_sha256": runner.validate_implementation_result.sha256_bytes(
            _patch.read_bytes()
        ),
        "gradle_user_home": str(_gradle_user_home),
        "commands": [],
        "bindings": [],
    }
    content = runner.canonical_bytes(value)
    quality_gate_receipt.write_bytes(content)
    return {
        "execution_attempted": True,
        "quality_gate_passed": True,
        "receipt_written": True,
        "receipt_sha256": runner.validate_implementation_result.sha256_bytes(content),
        "commands": [],
        "failures": [],
    }


def qg_valid(*_args: object, **_kwargs: object) -> dict[str, object]:
    return {"valid": True, "quality_gate_passed": True, "failures": []}


def cleanup_valid(*_args: object, **_kwargs: object) -> dict[str, object]:
    return {"valid": True, "failures": []}


class RunSupervisedImplementationTest(unittest.TestCase):
    def test_policy_is_exact_bounded_and_non_publishing(self) -> None:
        policy = runner.load_policy()

        self.assertEqual(runner.EXPECTED_POLICY, policy)
        self.assertFalse(policy["network_requested"])
        self.assertFalse(policy["publication_requested"])
        self.assertTrue(policy["require_consumed_authorization"])

    def test_adapter_entrypoint_resolves_interpreter_to_absolute_path(self) -> None:
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("bash is not installed")
        label, command = runner.adapter_entrypoint(
            REPO_ROOT,
            ["bash", ".agent/adapters/codex.sh", "--version"],
            runner.load_policy(),
        )

        self.assertEqual(".agent/adapters/codex.sh", label)
        self.assertEqual(str(Path(bash).resolve()), command[0])
        self.assertTrue(Path(command[1]).is_absolute())

    def test_end_to_end_runner_consumes_authorization_and_writes_final_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            values = authorized(temp)
            out = outputs(temp)
            captured_session: dict[str, object] = {}

            def adapter(
                _command: object,
                workspace: Path,
                *_args: object,
            ) -> dict[str, object]:
                session = json.loads(out["expected_session"].read_text(encoding="utf-8"))
                captured_session.update(session)
                (workspace / "runner-fixture.txt").write_text("changed\n", encoding="utf-8")
                return execution(result_bytes(session))

            with mock.patch.object(
                runner.validate_implementation_quality_gate,
                "validate",
                side_effect=qg_valid,
            ):
                result = runner.run_supervised(
                    *values,
                    allowed_adapter_command(),
                    out["expected_session"],
                    out["result"],
                    out["patch"],
                    out["patch_receipt"],
                    out["quality_gate"],
                    out["final"],
                    out["gradle_home"],
                    runner.load_policy(),
                    cleanup_receipt_output=out["cleanup"],
                    parent_environment=environment(),
                    adapter_runner=adapter,
                    quality_gate_executor=gate_pass,
                    cleanup_validator=cleanup_valid,
                    readiness_runner=approval_helpers.ready_runner,
                )
            receipt = json.loads(out["final"].read_text(encoding="utf-8"))
            result_written = out["result"].is_file()
            patch_written = out["patch"].is_file()
            cleanup_written = out["cleanup"].is_file()
            workspace_removed = not values[3].exists()
            consumption_marker_written = Path(str(values[10]) + ".consumed.json").is_file()

        self.assertTrue(result["runner_complete"], result["failures"])
        self.assertTrue(result["final_receipt_written"])
        self.assertTrue(result["final_receipt_valid"], result["final_receipt_validation"])
        self.assertTrue(result["authorization_consumed"])
        self.assertTrue(result["adapter_executed"])
        self.assertTrue(result["implementation_result_valid"])
        self.assertTrue(result["patch_candidate_ready"])
        self.assertTrue(result["quality_gate_passed"])
        self.assertTrue(result["quality_gate_receipt_valid"])
        self.assertTrue(result["cleanup_performed"])
        self.assertTrue(result["cleanup_receipt_valid"])
        self.assertFalse(result["cleanup_required"])
        self.assertTrue(result_written)
        self.assertTrue(patch_written)
        self.assertTrue(cleanup_written)
        self.assertTrue(workspace_removed)
        self.assertEqual("codex-cli-disposable-worktree", captured_session["runner_id"])
        self.assertFalse(receipt["publication_authorized"])
        self.assertFalse(receipt["authorization_consumption_to_process_start_atomic"])
        self.assertTrue(receipt["cleanup_performed"])
        self.assertTrue(receipt["cleanup_receipt_valid"])
        self.assertIn("cleanup_receipt", receipt["artifacts"])
        self.assertTrue(consumption_marker_written)

    def test_invalid_result_blocks_before_patch_and_does_not_retain_result_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            values = authorized(temp)
            out = outputs(temp)

            result = runner.run_supervised(
                *values,
                allowed_adapter_command(),
                out["expected_session"],
                out["result"],
                out["patch"],
                out["patch_receipt"],
                out["quality_gate"],
                out["final"],
                out["gradle_home"],
                runner.load_policy(),
                cleanup_receipt_output=out["cleanup"],
                parent_environment=environment(),
                adapter_runner=mock.Mock(return_value=execution(b"not json\n")),
                quality_gate_executor=mock.Mock(),
                cleanup_validator=cleanup_valid,
                readiness_runner=approval_helpers.ready_runner,
            )
            receipt = json.loads(out["final"].read_text(encoding="utf-8"))
            cleanup_written = out["cleanup"].is_file()
            workspace_removed = not values[3].exists()

        self.assertFalse(result["runner_complete"])
        self.assertTrue(result["final_receipt_written"])
        self.assertTrue(result["final_receipt_valid"], result["final_receipt_validation"])
        self.assertEqual("implementation_result", result["stage"])
        self.assertFalse(out["result"].exists())
        self.assertFalse(out["patch"].exists())
        self.assertTrue(result["cleanup_performed"])
        self.assertTrue(result["cleanup_receipt_valid"])
        self.assertFalse(result["cleanup_required"])
        self.assertTrue(cleanup_written)
        self.assertTrue(workspace_removed)
        self.assertTrue(receipt["cleanup_performed"])
        self.assertTrue(receipt["cleanup_receipt_valid"])
        self.assertIn("cleanup_receipt", receipt["artifacts"])
        self.assertEqual("implementation_result", receipt["failures"][0]["rule"])

    def test_patch_block_prevents_quality_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            values = authorized(temp)
            out = outputs(temp)
            quality_gate = mock.Mock()

            def adapter(_command: object, workspace: Path, *_args: object) -> dict[str, object]:
                session = json.loads(out["expected_session"].read_text(encoding="utf-8"))
                blocked = workspace / ".agent" / "blocked.txt"
                blocked.parent.mkdir(exist_ok=True)
                blocked.write_text("blocked\n", encoding="utf-8")
                return execution(result_bytes(session))

            result = runner.run_supervised(
                *values,
                allowed_adapter_command(),
                out["expected_session"],
                out["result"],
                out["patch"],
                out["patch_receipt"],
                out["quality_gate"],
                out["final"],
                out["gradle_home"],
                runner.load_policy(),
                parent_environment=environment(),
                adapter_runner=adapter,
                quality_gate_executor=quality_gate,
                readiness_runner=approval_helpers.ready_runner,
            )
            patch_receipt_written = out["patch_receipt"].is_file()

        self.assertFalse(result["runner_complete"])
        self.assertTrue(result["final_receipt_valid"], result["final_receipt_validation"])
        self.assertEqual("implementation_patch", result["stage"])
        self.assertFalse(result["patch_candidate_ready"])
        self.assertTrue(patch_receipt_written)
        quality_gate.assert_not_called()

    def test_unready_runner_blocks_before_adapter_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            values = authorized(temp)
            out = outputs(temp)
            adapter = mock.Mock()

            result = runner.run_supervised(
                *values,
                allowed_adapter_command(),
                out["expected_session"],
                out["result"],
                out["patch"],
                out["patch_receipt"],
                out["quality_gate"],
                out["final"],
                out["gradle_home"],
                runner.load_policy(),
                parent_environment=environment(),
                adapter_runner=adapter,
                quality_gate_executor=mock.Mock(),
                readiness_runner=approval_helpers.unready_runner,
            )

        self.assertFalse(result["runner_complete"])
        self.assertTrue(result["final_receipt_valid"], result["final_receipt_validation"])
        self.assertEqual("authorization_consumption", result["stage"])
        adapter.assert_not_called()

    def test_relative_adapter_entrypoint_is_resolved_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            workspace = temp / "workspace"
            workspace.mkdir()
            poisoned = workspace / ".agent" / "adapters" / "local_implementation_adapter.py"
            out = outputs(temp)
            captured: dict[str, object] = {}
            marker = temp / "authorization.json.consumed.json"
            marker.write_text("marker\n", encoding="utf-8")

            def adapter(command: object, *_args: object) -> dict[str, object]:
                captured["command"] = command
                return execution(b"not json\n")

            result = runner.run_supervised(
                REPO_ROOT,
                temp / "proposal.json",
                "0" * 64,
                workspace,
                temp / "worktree.json",
                "1" * 64,
                temp / "approval.json",
                "2" * 64,
                temp / "preflight.json",
                "3" * 64,
                temp / "authorization.json",
                "4" * 64,
                [sys.executable, ".agent/adapters/local_implementation_adapter.py"],
                out["expected_session"],
                out["result"],
                out["patch"],
                out["patch_receipt"],
                out["quality_gate"],
                out["final"],
                out["gradle_home"],
                runner.load_policy(),
                parent_environment=environment(),
                consumption_runner=mock.Mock(
                    return_value={
                        "consumed": True,
                        "consumption_marker": str(marker),
                        "consumption_marker_sha256": "5" * 64,
                    }
                ),
                launch_readiness_runner=mock.Mock(
                    return_value={
                        "launch_ready": True,
                        "issue": 1,
                        "risk": "low",
                        "base_commit": "6" * 40,
                        "workspace": str(workspace.resolve()),
                        "candidate_runner": {"id": "codex-cli-disposable-worktree"},
                    }
                ),
                adapter_runner=adapter,
                quality_gate_executor=mock.Mock(),
            )

        command = captured["command"]
        self.assertIsInstance(command, list)
        self.assertEqual(
            str((REPO_ROOT / ".agent" / "adapters" / "local_implementation_adapter.py").resolve()),
            command[1],
        )
        self.assertNotEqual(str(poisoned), command[1])
        self.assertEqual("implementation_result", result["stage"])

    def test_output_boundaries_policy_drift_and_cli_override_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            values = authorized(temp)
            out = outputs(temp)
            with self.assertRaisesRegex(ValueError, "outside the implementation workspace"):
                runner.run_supervised(
                    *values,
                    allowed_adapter_command(),
                    values[3] / "expected-session.json",
                    out["result"],
                    out["patch"],
                    out["patch_receipt"],
                    out["quality_gate"],
                    out["final"],
                    out["gradle_home"],
                    runner.load_policy(),
                    readiness_runner=approval_helpers.ready_runner,
                )

            path = temp / "policy.json"
            policy = json.loads(json.dumps(runner.EXPECTED_POLICY))
            policy["network_requested"] = True
            path.write_text(json.dumps(policy), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match"):
                runner.load_policy(path)

            blocked = outputs(temp / "blocked")
            adapter = mock.Mock()
            result = runner.run_supervised(
                *values,
                ["untrusted-adapter"],
                blocked["expected_session"],
                blocked["result"],
                blocked["patch"],
                blocked["patch_receipt"],
                blocked["quality_gate"],
                blocked["final"],
                blocked["gradle_home"],
                runner.load_policy(),
                parent_environment=environment(),
                adapter_runner=adapter,
                quality_gate_executor=mock.Mock(),
                readiness_runner=approval_helpers.ready_runner,
            )
            self.assertEqual("adapter_command", result["stage"])
            self.assertTrue(result["final_receipt_valid"], result["final_receipt_validation"])
            self.assertFalse(result["authorization_consumed"])
            self.assertFalse(result["adapter_executed"])
            adapter.assert_not_called()

        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--repo",
                ".",
                "--proposal",
                "proposal.json",
                "--proposal-sha256",
                "0" * 64,
                "--workspace",
                ".",
                "--worktree-receipt",
                "worktree.json",
                "--worktree-receipt-sha256",
                "0" * 64,
                "--approval-receipt",
                "approval.json",
                "--approval-receipt-sha256",
                "0" * 64,
                "--preflight",
                "preflight.json",
                "--preflight-sha256",
                "0" * 64,
                "--authorization-receipt",
                "authorization.json",
                "--authorization-receipt-sha256",
                "0" * 64,
                "--expected-session-output",
                "session.json",
                "--result-output",
                "result.json",
                "--patch-output",
                "patch.diff",
                "--patch-receipt-output",
                "patch-receipt.json",
                "--quality-gate-receipt-output",
                "quality-gate.json",
                "--final-receipt-output",
                "final.json",
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


if __name__ == "__main__":
    unittest.main()
