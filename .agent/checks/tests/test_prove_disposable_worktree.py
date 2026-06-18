from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "prove_disposable_worktree.py"
REPO_ROOT = CHECKS_DIR.parents[1]
SPEC = importlib.util.spec_from_file_location("prove_disposable_worktree", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
proof = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = proof
SPEC.loader.exec_module(proof)


class DisposableWorktreeProofTest(unittest.TestCase):
    def test_repository_policy_is_exact_fixture_only_and_non_invoking(self) -> None:
        policy = proof.load_policy()

        self.assertEqual(proof.EXPECTED_POLICY, policy)
        self.assertEqual("fixture-only", policy["mode"])
        self.assertNotIn("codex", json.dumps(policy).lower())
        self.assertEqual(
            "disposable_git_worktree_lifecycle_fixture",
            policy["proven_control"],
        )

    def test_real_fixture_verifies_all_lifecycle_invariants(self) -> None:
        observation = proof.observe_fixture(proof.load_policy(), "git")

        self.assertTrue(observation["matched"])
        self.assertEqual("dirty_detached_worktree_removed_cleanly", observation["observation"])
        self.assertTrue(
            all(
                value is True
                for key, value in observation.items()
                if key not in {"id", "observation"}
            )
        )

    def test_missing_git_and_unmatched_fixture_do_not_verify(self) -> None:
        missing = proof.prove(REPO_ROOT, proof.load_policy(), lambda _name: None)
        unmatched = proof.base_observation("lifecycle_invariant_failed")
        result = proof.prove(
            REPO_ROOT,
            proof.load_policy(),
            lambda _name: "git",
            lambda *_args: unmatched,
        )

        self.assertEqual("not_proven", missing["control_assessments"][0]["assessment"])
        self.assertEqual("unsupported_environment", missing["fixture"]["observation"])
        self.assertEqual("not_proven", result["control_assessments"][0]["assessment"])
        for field in proof.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_failed_git_command_fails_closed_without_returning_raw_output(self) -> None:
        sensitive = b"SENSITIVE_GIT_OUTPUT_NOT_RETURNED"

        def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
            return subprocess.CompletedProcess(command, 1, stdout=sensitive, stderr=sensitive)

        observation = proof.observe_fixture(proof.load_policy(), "git", runner=runner)

        self.assertFalse(observation["matched"])
        self.assertEqual("fixture_error", observation["observation"])
        self.assertNotIn(sensitive.decode(), json.dumps(observation))

    def test_git_wrapper_uses_no_shell_and_exact_repo_scope(self) -> None:
        invocation: dict[str, object] = {}

        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            invocation["command"] = command
            invocation.update(kwargs)
            return subprocess.CompletedProcess(command, 0, stdout=b"ok", stderr=b"")

        result = proof.run_git("git.exe", REPO_ROOT, 10, "status", "--short", runner=runner)

        self.assertEqual(b"ok", result)
        self.assertIs(False, invocation["shell"])
        self.assertEqual(
            ["git.exe", "-c", f"safe.directory={REPO_ROOT.as_posix()}", "-C", str(REPO_ROOT)],
            invocation["command"][:5],
        )

    def test_policy_drift_and_cli_override_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "policy.json"
            policy = json.loads(json.dumps(proof.EXPECTED_POLICY))
            policy["unproven_controls"].remove("worktree_cleanup_after_host_crash")
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

    def test_real_cli_verifies_fixture_without_mutating_input_repo(self) -> None:
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
        before = subprocess.run(status_command, check=True, capture_output=True, text=True).stdout
        completed = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--repo", str(REPO_ROOT), "--format", "json"],
            check=False,
            capture_output=True,
            text=True,
        )
        after = subprocess.run(status_command, check=True, capture_output=True, text=True).stdout
        result = json.loads(completed.stdout)

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(before, after)
        self.assertEqual("verified_fixture", result["control_assessments"][0]["assessment"])
        self.assertEqual(
            "not_proven",
            next(
                item["assessment"]
                for item in result["control_assessments"]
                if item["id"] == "implementation_runner_disposable_worktree_lifecycle"
            ),
        )


if __name__ == "__main__":
    unittest.main()
