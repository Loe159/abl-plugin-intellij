from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ADAPTER_PATH = Path(__file__).resolve().parents[2] / "adapters" / "local_implementation_adapter.py"
CHECKS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = CHECKS_DIR.parents[1]
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("local_implementation_adapter", ADAPTER_PATH)
assert SPEC is not None
assert SPEC.loader is not None
adapter = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = adapter
SPEC.loader.exec_module(adapter)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def init_workspace(
    parent: Path,
    runner_id: str = "local-adapter-fixture",
) -> tuple[Path, Path, dict[str, object]]:
    workspace = parent / "workspace"
    workspace.mkdir()
    git(workspace, "init")
    git(workspace, "config", "user.email", "adapter@example.invalid")
    git(workspace, "config", "user.name", "Adapter")
    (workspace / "README.md").write_text("base\n", encoding="utf-8")
    git(workspace, "add", ".")
    git(workspace, "commit", "-m", "base")
    base = git(workspace, "rev-parse", "HEAD")
    session = {
        "issue": 7,
        "risk": "low",
        "base_commit": base,
        "workspace": str(workspace.resolve()),
        "runner_id": runner_id,
        "preflight_sha256": "1" * 64,
        "start_authorization_receipt_sha256": "2" * 64,
    }
    expected = parent / "expected-session.json"
    expected.write_text(json.dumps(session), encoding="utf-8")
    return workspace, expected, session


class LocalImplementationAdapterTest(unittest.TestCase):
    def test_policy_is_exact_command_wrapper(self) -> None:
        policy = adapter.load_policy()

        self.assertEqual(adapter.EXPECTED_POLICY, policy)
        self.assertEqual("agent-command-wrapper", policy["mode"])
        self.assertFalse(any("publish" in item for item in policy["bindings"]))
        self.assertIn("codex", policy["allowed_command_basenames"])
        self.assertIn("codex.exe", policy["allowed_command_basenames"])
        self.assertIn("opencode.exe", policy["allowed_command_basenames"])
        self.assertIn("local-adapter-fixture", policy["fixture_runner_ids"])

    def test_changed_workspace_emits_completed_candidate_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace, expected, session = init_workspace(Path(temp_dir))
            content = adapter.run_adapter(
                expected,
                [
                    sys.executable,
                    "-c",
                    "from pathlib import Path; Path('changed.txt').write_text('changed\\n')",
                ],
                workspace,
                adapter.load_policy(),
            )
            value = json.loads(content.decode("utf-8"))

        self.assertEqual("completed", value["status"])
        self.assertTrue(value["workspace_changed"])
        self.assertEqual("deterministic_patch_generation", value["next_action"])
        self.assertEqual(session["preflight_sha256"], value["preflight_sha256"])
        self.assertFalse(value["patch_generated"])
        self.assertFalse(value["deterministic_checks_run"])
        self.assertFalse(value["publication_requested"])
        self.assertFalse(value["network_requested"])

    def test_adapter_child_environment_filters_provider_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace, expected, _session = init_workspace(Path(temp_dir))
            script = (
                "import os, sys; "
                "sys.exit(7) if 'OPENAI_API_KEY' in os.environ else None; "
                "from pathlib import Path; Path('changed.txt').write_text('changed\\n')"
            )
            with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "fixture-secret"}):
                content = adapter.run_adapter(
                    expected,
                    [sys.executable, "-c", script],
                    workspace,
                    adapter.load_policy(),
                )
            value = json.loads(content.decode("utf-8"))

        self.assertEqual("completed", value["status"])
        self.assertTrue(value["workspace_changed"])

    def test_no_change_and_failed_command_emit_human_review_results(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace, expected, _session = init_workspace(Path(temp_dir))
            no_change = json.loads(
                adapter.run_adapter(
                    expected,
                    [sys.executable, "-c", "print('no change')"],
                    workspace,
                    adapter.load_policy(),
                ).decode("utf-8")
            )
            failed = json.loads(
                adapter.run_adapter(
                    expected,
                    [sys.executable, "-c", "raise SystemExit(3)"],
                    workspace,
                    adapter.load_policy(),
                ).decode("utf-8")
            )

        self.assertEqual("blocked", no_change["status"])
        self.assertFalse(no_change["workspace_changed"])
        self.assertEqual("human_review", no_change["next_action"])
        self.assertEqual("failed", failed["status"])
        self.assertEqual("human_review", failed["next_action"])

    def test_dirty_workspace_blocks_before_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace, expected, _session = init_workspace(Path(temp_dir))
            (workspace / "dirty.txt").write_text("dirty\n", encoding="utf-8")
            value = json.loads(
                adapter.run_adapter(
                    expected,
                    [
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('should-not-run.txt').write_text('x')",
                    ],
                    workspace,
                    adapter.load_policy(),
                ).decode("utf-8")
            )

        self.assertEqual("failed", value["status"])
        self.assertFalse((workspace / "should-not-run.txt").exists())

    def test_non_allowlisted_command_is_rejected_for_real_runner_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace, expected, _session = init_workspace(
                Path(temp_dir),
                runner_id="codex-cli-disposable-worktree",
            )

            with self.assertRaisesRegex(ValueError, "not allowlisted"):
                adapter.run_adapter(
                    expected,
                    [sys.executable, "-c", "print('not allowed for real runner')"],
                    workspace,
                    adapter.load_policy(),
                )

    def test_cli_refuses_policy_override_without_adapter_separator(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace, expected, _session = init_workspace(Path(temp_dir))
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ADAPTER_PATH),
                    "--expected-session",
                    str(expected),
                    "--workspace",
                    str(workspace),
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
