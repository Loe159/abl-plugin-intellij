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
MODULE_PATH = CHECKS_DIR / "publish_draft_pr.py"
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("publish_draft_pr", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
publisher = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = publisher
SPEC.loader.exec_module(publisher)


def publication_fixture(temp: Path) -> tuple[Path, dict[str, Path], Path, str, str]:
    repo = temp / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Agent Test",
            "-c",
            "user.email=agent@example.invalid",
            "commit",
            "-m",
            "base",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    workspace = temp / "workspace"
    workspace.mkdir()
    external = temp / "external"
    external.mkdir()
    gradle_home = temp / "gradle-home"
    gradle_home.mkdir()
    expected_session = {
        "issue": 123,
        "risk": "low",
        "base_commit": base,
        "workspace": str(workspace.resolve()),
        "runner_id": "local",
        "preflight_sha256": "a" * 64,
        "start_authorization_receipt_sha256": "b" * 64,
    }
    paths = {
        "result": external / "result.json",
        "expected": external / "expected-session.json",
        "patch": external / "patch.diff",
        "patch_receipt": external / "patch-receipt.json",
        "quality": external / "quality.json",
        "body": external / "body.md",
        "receipt": external / "publication.json",
    }
    paths["result"].write_text("{}\n", encoding="utf-8")
    paths["expected"].write_text(json.dumps(expected_session), encoding="utf-8")
    paths["patch"].write_text("diff --git a/README.md b/README.md\n", encoding="utf-8")
    paths["patch_receipt"].write_text("{}\n", encoding="utf-8")
    paths["quality"].write_text("{}\n", encoding="utf-8")
    return repo, paths, gradle_home, "c" * 64, "d" * 64


class PublishDraftPrTest(unittest.TestCase):
    def test_policy_is_exact_and_dry_run_by_default(self) -> None:
        policy = publisher.load_policy()

        self.assertEqual(publisher.EXPECTED_POLICY, policy)
        self.assertTrue(policy["default_dry_run"])
        self.assertTrue(policy["require_execute_flag_for_external_writes"])
        self.assertEqual(["codex/"], policy["allowed_branch_prefixes"])

    def test_branch_validation_rejects_unsafe_names(self) -> None:
        policy = publisher.load_policy()

        self.assertEqual("codex/agent-123", publisher.validate_branch("codex/agent-123", policy))
        for name in ["main", "codex/../main", "codex//x", "codex/topic.lock", " codex/x"]:
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "branch name"):
                    publisher.validate_branch(name, policy)

    def test_dry_run_writes_plan_without_running_external_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            (repo / "README.md").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Agent Test",
                    "-c",
                    "user.email=agent@example.invalid",
                    "commit",
                    "-m",
                    "base",
                ],
                cwd=repo,
                check=True,
                capture_output=True,
            )
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()

            workspace = temp / "workspace"
            workspace.mkdir()
            external = temp / "external"
            external.mkdir()
            gradle_home = temp / "gradle-home"
            gradle_home.mkdir()
            expected_session = {
                "issue": 123,
                "risk": "low",
                "base_commit": base,
                "workspace": str(workspace.resolve()),
                "runner_id": "local",
                "preflight_sha256": "a" * 64,
                "start_authorization_receipt_sha256": "b" * 64,
            }
            paths = {
                "result": external / "result.json",
                "expected": external / "expected-session.json",
                "patch": external / "patch.diff",
                "patch_receipt": external / "patch-receipt.json",
                "quality": external / "quality.json",
                "body": external / "body.md",
                "receipt": external / "publication.json",
            }
            paths["result"].write_text("{}\n", encoding="utf-8")
            paths["expected"].write_text(json.dumps(expected_session), encoding="utf-8")
            paths["patch"].write_text("diff --git a/README.md b/README.md\n", encoding="utf-8")
            paths["patch_receipt"].write_text("{}\n", encoding="utf-8")
            paths["quality"].write_text("{}\n", encoding="utf-8")
            patch_receipt_sha = "c" * 64
            quality_sha = "d" * 64
            calls: list[Any] = []

            def fake_quality_validator(*args: Any, **kwargs: Any) -> dict[str, Any]:
                return {"valid": True, "quality_gate_passed": True}

            def fake_runner(*args: Any, **kwargs: Any) -> dict[str, Any]:
                calls.append(args)
                return {"status": "passed"}

            result = publisher.publish(
                repo,
                paths["result"],
                paths["expected"],
                paths["patch"],
                paths["patch_receipt"],
                patch_receipt_sha,
                paths["quality"],
                quality_sha,
                gradle_home,
                "codex/agent-123",
                "Draft fix",
                "Small deterministic patch.",
                paths["body"],
                paths["receipt"],
                "main",
                "origin",
                False,
                publisher.load_policy(),
                quality_gate_validator=fake_quality_validator,
                command_runner=fake_runner,
            )

            self.assertTrue(result["publisher_complete"])
            self.assertTrue(result["dry_run"])
            self.assertFalse(result["draft_pr_created"])
            self.assertFalse(result["branch_pushed"])
            self.assertEqual([], calls)
            self.assertTrue(paths["body"].is_file())
            self.assertTrue(paths["receipt"].is_file())
            self.assertTrue(all(command["status"] == "planned" for command in result["commands"]))

    def test_execute_blocked_by_quality_gate_does_not_claim_external_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, paths, gradle_home, patch_receipt_sha, quality_sha = publication_fixture(
                Path(temp_dir)
            )
            calls: list[Any] = []

            def fake_quality_validator(*args: Any, **kwargs: Any) -> dict[str, Any]:
                return {"valid": False, "quality_gate_passed": False}

            def fake_runner(*args: Any, **kwargs: Any) -> dict[str, Any]:
                calls.append(args)
                return {"status": "passed"}

            result = publisher.publish(
                repo,
                paths["result"],
                paths["expected"],
                paths["patch"],
                paths["patch_receipt"],
                patch_receipt_sha,
                paths["quality"],
                quality_sha,
                gradle_home,
                "codex/agent-123",
                "Draft fix",
                "Small deterministic patch.",
                paths["body"],
                paths["receipt"],
                "main",
                "origin",
                True,
                publisher.load_policy(),
                quality_gate_validator=fake_quality_validator,
                command_runner=fake_runner,
            )

        self.assertFalse(result["publisher_complete"])
        self.assertFalse(result["dry_run"])
        self.assertTrue(result["publication_requested"])
        self.assertTrue(result["publication_authorized"])
        self.assertFalse(result["branch_pushed"])
        self.assertFalse(result["draft_pr_created"])
        self.assertFalse(result["external_service_written"])
        self.assertEqual([], calls)
        self.assertTrue(all(command["status"] == "blocked" for command in result["commands"]))

    def test_execute_runs_only_draft_pr_publication_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, paths, gradle_home, patch_receipt_sha, quality_sha = publication_fixture(
                Path(temp_dir)
            )
            commands: list[list[str]] = []

            def fake_quality_validator(*args: Any, **kwargs: Any) -> dict[str, Any]:
                return {"valid": True, "quality_gate_passed": True}

            def fake_runner(
                argv: list[str],
                *_args: Any,
                **_kwargs: Any,
            ) -> dict[str, Any]:
                commands.append(list(argv))
                return {
                    "argv": list(argv),
                    "status": "passed",
                    "returncode": 0,
                    "stdout_bytes": 0,
                    "stderr_bytes": 0,
                    "stdout_sha256": "0" * 64,
                    "stderr_sha256": "0" * 64,
                }

            result = publisher.publish(
                repo,
                paths["result"],
                paths["expected"],
                paths["patch"],
                paths["patch_receipt"],
                patch_receipt_sha,
                paths["quality"],
                quality_sha,
                gradle_home,
                "codex/agent-123",
                "Draft fix",
                "Small deterministic patch.",
                paths["body"],
                paths["receipt"],
                "main",
                "origin",
                True,
                publisher.load_policy(),
                quality_gate_validator=fake_quality_validator,
                command_runner=fake_runner,
            )

        self.assertTrue(result["publisher_complete"])
        self.assertTrue(result["branch_pushed"])
        self.assertTrue(result["draft_pr_created"])
        self.assertTrue(result["external_service_written"])
        self.assertEqual("gh", commands[-1][0])
        self.assertEqual("pr", commands[-1][1])
        self.assertEqual("create", commands[-1][2])
        self.assertIn("--draft", commands[-1])
        flattened = [part for command in commands for part in command]
        self.assertNotIn("merge", flattened)
        self.assertNotIn("release", flattened)


if __name__ == "__main__":
    unittest.main()
