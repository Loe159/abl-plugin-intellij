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


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "validate_implementation_quality_gate.py"
REPO_ROOT = CHECKS_DIR.parents[1]
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location(
    "validate_implementation_quality_gate",
    MODULE_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


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


def fixture(root: Path, returncode: int = 0) -> dict[str, object]:
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
    (workspace / "app.txt").write_text("base\nchange\n", encoding="utf-8")
    workspace = workspace.resolve()
    identity = {
        "issue": 63,
        "risk": "medium",
        "base_commit": base,
        "workspace": str(workspace),
        "runner_id": "quality-gate-validation-test",
        "preflight_sha256": "2" * 64,
        "start_authorization_receipt_sha256": "3" * 64,
    }
    result_value = {
        "result_version": 1,
        "purpose": "implementation_session_result",
        "mode": "untrusted-runner-output",
        "status": "completed",
        **identity,
        "summary": "Completed quality-gate validation fixture.",
        "workspace_changed": True,
        "patch_generated": False,
        "deterministic_checks_run": False,
        "publication_requested": False,
        "network_requested": False,
        "next_action": "deterministic_patch_generation",
    }
    paths = {
        "workspace": workspace,
        "result": root / "result.json",
        "session": root / "session.json",
        "patch": root / "candidate.patch",
        "patch_receipt": root / "patch-receipt.json",
        "quality_receipt": root / "quality-receipt.json",
        "gradle_home": root / "gradle-home",
    }
    paths["result"].write_bytes(
        validator.validate_implementation_result.canonical_result_bytes(result_value)
    )
    paths["session"].write_text(
        json.dumps(identity, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    patch_result = validator.validate_implementation_patch.validate_patch(
        REPO_ROOT,
        validator.validate_implementation_patch.captured_execution(
            paths["result"].read_bytes(),
            b"",
        ),
        identity,
        paths["patch"],
        paths["patch_receipt"],
        validator.validate_implementation_patch.load_policy(),
    )
    distribution = (
        paths["gradle_home"]
        / "wrapper"
        / "dists"
        / "gradle-8.11.1-bin"
        / "fixture"
        / "gradle-8.11.1"
        / "bin"
    )
    distribution.mkdir(parents=True)
    (distribution / "gradle.bat").write_text("@echo off\r\n", encoding="ascii")
    quality_result = validator.run_implementation_quality_gate.execute(
        REPO_ROOT,
        paths["result"],
        paths["session"],
        paths["patch"],
        paths["patch_receipt"],
        patch_result["receipt_sha256"],
        paths["quality_receipt"],
        paths["gradle_home"],
        validator.run_implementation_quality_gate.load_policy(),
        parent_environment={
            "COMSPEC": os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"),
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
            "WINDIR": os.environ.get("WINDIR", r"C:\Windows"),
        },
        which=lambda _name: r"C:\Windows\System32\taskkill.exe",
        command_runner=mock.Mock(return_value=execution(returncode)),
    )
    return {
        **paths,
        "patch_receipt_sha256": patch_result["receipt_sha256"],
        "quality_receipt_sha256": quality_result["receipt_sha256"],
    }


def validate(item: dict[str, object]) -> dict[str, object]:
    return validator.validate(
        REPO_ROOT,
        item["result"],
        item["session"],
        item["patch"],
        item["patch_receipt"],
        item["patch_receipt_sha256"],
        item["quality_receipt"],
        item["quality_receipt_sha256"],
        item["gradle_home"],
        validator.load_policy(),
    )


class ValidateImplementationQualityGateTest(unittest.TestCase):
    def test_policy_is_exact_validation_only_and_non_authorizing(self) -> None:
        policy = validator.load_policy()

        self.assertEqual(validator.EXPECTED_POLICY, policy)
        self.assertEqual("validation-only", policy["mode"])
        self.assertTrue(policy["require_current_gradle_cache"])

    def test_passed_receipt_is_valid_but_does_not_approve(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = validate(fixture(Path(temp_dir)))

        self.assertTrue(result["valid"])
        self.assertTrue(result["quality_gate_passed"])
        self.assertTrue(result["patch_candidate_ready"])
        for field in validator.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_failed_receipt_is_valid_evidence_of_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = validate(fixture(Path(temp_dir), returncode=1))

        self.assertTrue(result["valid"])
        self.assertFalse(result["quality_gate_passed"])
        self.assertEqual(
            ["failed", "not_run", "not_run"],
            [record["status"] for record in result["commands"]],
        )

    def test_wrong_digest_and_rehashed_command_tampering_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            item = fixture(Path(temp_dir))
            value = json.loads(item["quality_receipt"].read_text(encoding="utf-8"))
            value["commands"][0]["duration_seconds"] = 901.0
            item["quality_receipt"].write_bytes(
                validator.validate_implementation_patch.canonical_bytes(value)
            )
            result = validate(item)
            self.assertFalse(result["valid"])
            self.assertEqual("receipt_sha256", result["failures"][0]["rule"])

            item["quality_receipt_sha256"] = (
                validator.validate_implementation_result.sha256_bytes(
                    item["quality_receipt"].read_bytes()
                )
            )
            result = validate(item)
            self.assertFalse(result["valid"])
            self.assertIn(
                "command_record",
                {failure["rule"] for failure in result["failures"]},
            )

    def test_rehashed_overclaim_and_binding_tampering_are_rejected(self) -> None:
        for mutate, expected_rule in (
            (
                lambda value: value.update(publication_authorized=True),
                "receipt_metadata",
            ),
            (
                lambda value: value["bindings"][0].update(sha256="0" * 64),
                "trusted_binding_mismatch",
            ),
        ):
            with self.subTest(expected_rule=expected_rule):
                with tempfile.TemporaryDirectory() as temp_dir:
                    item = fixture(Path(temp_dir))
                    value = json.loads(
                        item["quality_receipt"].read_text(encoding="utf-8")
                    )
                    mutate(value)
                    item["quality_receipt"].write_bytes(
                        validator.validate_implementation_patch.canonical_bytes(value)
                    )
                    item["quality_receipt_sha256"] = (
                        validator.validate_implementation_result.sha256_bytes(
                            item["quality_receipt"].read_bytes()
                        )
                    )
                    result = validate(item)
                self.assertFalse(result["valid"])
                self.assertIn(
                    expected_rule,
                    {failure["rule"] for failure in result["failures"]},
                )

    def test_patch_workspace_or_cache_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            item = fixture(Path(temp_dir))
            (item["workspace"] / "extra.txt").write_text("drift\n", encoding="utf-8")
            result = validate(item)
            self.assertFalse(result["valid"])
            self.assertIn(
                "patch_receipt",
                {failure["rule"] for failure in result["failures"]},
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            item = fixture(Path(temp_dir))
            for path in item["gradle_home"].rglob("gradle.bat"):
                path.unlink()
            with self.assertRaisesRegex(ValueError, "distribution is not cached"):
                validate(item)

    def test_state_change_during_validation_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            item = fixture(Path(temp_dir))
            snapshot = validator.generate_complete_patch.repository_snapshot(
                item["workspace"]
            )
            changed = {**snapshot, "status": snapshot["status"] + b"drift"}
            calls = 0

            def drifting_snapshot(_workspace: Path) -> dict[str, object]:
                nonlocal calls
                calls += 1
                return changed if calls >= 4 else snapshot

            with mock.patch.object(
                validator.generate_complete_patch,
                "repository_snapshot",
                side_effect=drifting_snapshot,
            ):
                result = validate(item)

        self.assertFalse(result["valid"])
        self.assertEqual("state_changed", result["failures"][-1]["rule"])

    def test_policy_drift_and_cli_override_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "policy.json"
            policy = json.loads(json.dumps(validator.EXPECTED_POLICY))
            policy["require_current_gradle_cache"] = False
            path.write_text(json.dumps(policy), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match"):
                validator.load_policy(path)

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
                "--quality-gate-receipt",
                "quality.json",
                "--quality-gate-receipt-sha256",
                "0" * 64,
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
