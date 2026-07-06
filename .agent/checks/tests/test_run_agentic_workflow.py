from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


CHECKS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = CHECKS_DIR.parents[1]
MODULE_PATH = CHECKS_DIR / "run_agentic_workflow.py"
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("run_agentic_workflow", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
trigger = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = trigger
SPEC.loader.exec_module(trigger)

import prepare_disposable_worktree


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def init_repo(parent: Path) -> tuple[Path, str]:
    repo = parent / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "workflow-trigger@example.invalid")
    git(repo, "config", "user.name", "Workflow Trigger")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")
    return repo, git(repo, "rev-parse", "HEAD")


def write_artifacts(directory: Path) -> dict[str, Path]:
    paths = {
        "proposal": directory / "proposal.json",
        "approval": directory / "approval.json",
        "preflight": directory / "preflight.json",
        "authorization": directory / "authorization.json",
    }
    for name, path in paths.items():
        path.write_text(json.dumps({"artifact": name}) + "\n", encoding="utf-8")
    return paths


def workflow_fixture(parent: Path) -> dict[str, Any]:
    repo, base = init_repo(parent)
    run_dir = parent / "run"
    run_dir.mkdir()
    workspace = parent / "workspace"
    worktree_receipt = run_dir / "worktree.json"
    prepare_disposable_worktree.prepare(
        repo,
        base,
        workspace,
        worktree_receipt,
        prepare_disposable_worktree.load_policy(),
    )
    artifacts = write_artifacts(run_dir)
    output_dir = parent / "outputs"
    output_dir.mkdir()
    gradle_home = parent / "gradle-home"
    gradle_home.mkdir()
    return {
        "repo": repo,
        "workspace": workspace,
        "worktree_receipt": worktree_receipt,
        "proposal": artifacts["proposal"],
        "approval": artifacts["approval"],
        "preflight": artifacts["preflight"],
        "authorization": artifacts["authorization"],
        "output_dir": output_dir,
        "gradle_home": gradle_home,
    }


class RunAgenticWorkflowTest(unittest.TestCase):
    def test_policy_is_exact_dry_run_or_explicit_execute(self) -> None:
        policy = trigger.load_policy()

        self.assertEqual(trigger.EXPECTED_POLICY, policy)
        self.assertTrue(policy["default_dry_run"])
        self.assertTrue(policy["require_execute_flag_for_runner_process"])
        self.assertIn(".agent/checks/run_supervised_implementation.py", policy["bindings"])

    def test_dry_run_builds_command_without_starting_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = workflow_fixture(Path(temp_dir))
            calls: list[Any] = []

            def fake_runner(*args: Any, **kwargs: Any) -> dict[str, Any]:
                calls.append(args)
                return {"returncode": 0}

            result = trigger.trigger_workflow(
                fixture["repo"],
                fixture["proposal"],
                fixture["workspace"],
                fixture["worktree_receipt"],
                fixture["approval"],
                fixture["preflight"],
                fixture["authorization"],
                fixture["output_dir"],
                fixture["gradle_home"],
                "json",
                ["python", "adapter.py"],
                False,
                trigger.load_policy(),
                command_runner=fake_runner,
            )

        self.assertTrue(result["workflow_trigger_ready"])
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["execute_requested"])
        self.assertFalse(result["runner_process_started"])
        self.assertEqual([], calls)
        self.assertEqual(
            "run_supervised_implementation.py",
            Path(result["invocation"]["command"][1]).name,
        )
        for field in trigger.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_execute_runs_constructed_runner_command_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = workflow_fixture(Path(temp_dir))
            calls: list[list[str]] = []

            def fake_runner(
                argv: list[str],
                cwd: Path,
                timeout_seconds: float,
                max_output_bytes: int,
            ) -> dict[str, Any]:
                calls.append(list(argv))
                final_index = argv.index("--final-receipt-output") + 1
                final_receipt = Path(argv[final_index])
                final_receipt.write_bytes(b"{}\n")
                return {
                    "argv": list(argv),
                    "returncode": 0,
                    "stdout_bytes": 0,
                    "stderr_bytes": 0,
                    "stdout_sha256": "0" * 64,
                    "stderr_sha256": "0" * 64,
                    "stdout_truncated": False,
                    "stderr_truncated": False,
                    "cwd": str(cwd),
                    "timeout_seconds": timeout_seconds,
                    "max_output_bytes": max_output_bytes,
                }

            result = trigger.trigger_workflow(
                fixture["repo"],
                fixture["proposal"],
                fixture["workspace"],
                fixture["worktree_receipt"],
                fixture["approval"],
                fixture["preflight"],
                fixture["authorization"],
                fixture["output_dir"],
                fixture["gradle_home"],
                "json",
                ["python", "adapter.py"],
                True,
                trigger.load_policy(),
                command_runner=fake_runner,
            )

        self.assertFalse(result["dry_run"])
        self.assertTrue(result["execute_requested"])
        self.assertTrue(result["runner_process_started"])
        self.assertTrue(result["runner_completed"])
        self.assertFalse(result["runner_blocked"])
        self.assertEqual(0, result["runner_exit_code"])
        self.assertEqual(1, len(calls))
        self.assertIn("--", calls[0])
        self.assertTrue(result["final_receipt_present"])
        self.assertEqual(trigger.sha256_bytes(b"{}\n"), result["final_receipt_sha256"])
        for field in trigger.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_cli_refuses_policy_override(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--repo",
                str(REPO_ROOT),
                "--proposal",
                "proposal.json",
                "--workspace",
                "workspace",
                "--worktree-receipt",
                "worktree.json",
                "--approval-receipt",
                "approval.json",
                "--preflight",
                "preflight.json",
                "--authorization-receipt",
                "authorization.json",
                "--output-dir",
                "outputs",
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


if __name__ == "__main__":
    unittest.main()
