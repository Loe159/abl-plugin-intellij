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
MODULE_PATH = CHECKS_DIR / "build_supervised_runner_invocation.py"
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("build_supervised_runner_invocation", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)

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
    git(repo, "config", "user.email", "runner-invocation@example.invalid")
    git(repo, "config", "user.name", "Runner Invocation")
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


class BuildSupervisedRunnerInvocationTest(unittest.TestCase):
    def test_policy_is_exact_command_construction_only(self) -> None:
        policy = builder.load_policy()

        self.assertEqual(builder.EXPECTED_POLICY, policy)
        self.assertEqual("command-construction-only", policy["mode"])
        self.assertIn(".agent/checks/run_supervised_implementation.py", policy["bindings"])

    def test_builds_exact_runner_command_from_prepared_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            repo, base = init_repo(parent)
            run_dir = parent / "run"
            run_dir.mkdir()
            workspace = parent / "workspace"
            worktree_receipt = run_dir / "worktree.json"
            prepared = prepare_disposable_worktree.prepare(
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

            result = builder.build_invocation(
                repo,
                artifacts["proposal"],
                workspace,
                worktree_receipt,
                artifacts["approval"],
                artifacts["preflight"],
                artifacts["authorization"],
                output_dir,
                gradle_home,
                "json",
                ["python", "adapter.py"],
                builder.load_policy(),
            )

        self.assertTrue(result["runner_invocation_ready"])
        self.assertFalse(result["agent_invocation_authorized"])
        self.assertEqual(prepared["receipt_sha256"], result["input_sha256"]["worktree_receipt"])
        self.assertTrue(result["worktree_validation"]["valid"])
        self.assertIn("--worktree-receipt-sha256", result["command"])
        self.assertIn(str(output_dir / "final-receipt.json"), result["command"])
        self.assertEqual(["python", "adapter.py"], result["adapter_command"])

    def test_rejects_existing_output_and_missing_adapter_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
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
            (output_dir / "final-receipt.json").write_text("exists\n", encoding="utf-8")
            gradle_home = parent / "gradle-home"
            gradle_home.mkdir()

            with self.assertRaisesRegex(ValueError, "final_receipt output already exists"):
                builder.build_invocation(
                    repo,
                    artifacts["proposal"],
                    workspace,
                    worktree_receipt,
                    artifacts["approval"],
                    artifacts["preflight"],
                    artifacts["authorization"],
                    output_dir,
                    gradle_home,
                    "json",
                    ["python", "adapter.py"],
                    builder.load_policy(),
                )
            with self.assertRaisesRegex(ValueError, "Adapter command is required"):
                builder.build_invocation(
                    repo,
                    artifacts["proposal"],
                    workspace,
                    worktree_receipt,
                    artifacts["approval"],
                    artifacts["preflight"],
                    artifacts["authorization"],
                    parent / "fresh-outputs",
                    gradle_home,
                    "json",
                    [],
                    builder.load_policy(),
                )

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
        self.assertIn("unrecognized arguments: --policy", completed.stderr)


if __name__ == "__main__":
    unittest.main()
