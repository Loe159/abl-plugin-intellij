from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "validate_implementation_patch_receipt.py"
REPO_ROOT = CHECKS_DIR.parents[1]
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location(
    "validate_implementation_patch_receipt",
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


def fixture(
    root: Path,
    protected: bool = False,
    changed: bool = True,
) -> dict[str, object]:
    workspace = root / "workspace"
    workspace.mkdir()
    git(workspace, "init")
    git(workspace, "config", "user.email", "test@example.invalid")
    git(workspace, "config", "user.name", "Test Fixture")
    (workspace / "app.txt").write_text("base\n", encoding="utf-8")
    git(workspace, "add", "app.txt")
    git(workspace, "commit", "-m", "base")
    base = git(workspace, "rev-parse", "HEAD")
    if protected:
        target = workspace / ".agent" / "blocked.txt"
        target.parent.mkdir()
        target.write_text("blocked\n", encoding="utf-8")
    elif changed:
        (workspace / "app.txt").write_text("base\nchange\n", encoding="utf-8")
    workspace = workspace.resolve()
    identity = {
        "issue": 59,
        "risk": "medium",
        "base_commit": base,
        "workspace": str(workspace),
        "runner_id": "receipt-test-runner",
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
    receipt = root / "receipt.json"
    result_path.write_bytes(
        validator.validate_implementation_result.canonical_result_bytes(result_value)
    )
    session_path.write_text(
        json.dumps(identity, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    produced = validator.validate_implementation_patch.validate_patch(
        REPO_ROOT,
        validator.validate_implementation_patch.captured_execution(
            result_path.read_bytes(),
            b"",
        ),
        identity,
        patch,
        receipt,
        validator.validate_implementation_patch.load_policy(),
    )
    return {
        "workspace": workspace,
        "result": result_path,
        "session": session_path,
        "patch": patch,
        "receipt": receipt,
        "sha256": produced["receipt_sha256"],
    }


def empty_fixture(root: Path) -> dict[str, object]:
    return fixture(root, changed=False)


def validate(item: dict[str, object]) -> dict[str, object]:
    return validator.validate(
        REPO_ROOT,
        item["result"],
        item["session"],
        item["patch"],
        item["receipt"],
        item["sha256"],
        validator.load_policy(),
    )


class ValidateImplementationPatchReceiptTest(unittest.TestCase):
    def test_policy_is_exact_validation_only_and_non_authorizing(self) -> None:
        policy = validator.load_policy()

        self.assertEqual(validator.EXPECTED_POLICY, policy)
        self.assertEqual("validation-only", policy["mode"])
        self.assertTrue(policy["require_retained_patch"])

    def test_allowed_patch_receipt_is_valid_and_candidate_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = validate(fixture(Path(temp_dir)))

        self.assertTrue(result["valid"])
        self.assertTrue(result["patch_candidate_ready"])
        self.assertTrue(result["patch_policy_allowed"])
        self.assertEqual("low", result["risk"])
        self.assertFalse(result["quality_gate"]["completed"])
        for field in validator.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_empty_patch_receipt_is_valid_but_not_candidate_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = validate(empty_fixture(Path(temp_dir)))

        self.assertTrue(result["valid"])
        self.assertFalse(result["patch_candidate_ready"])
        self.assertTrue(result["patch_policy_allowed"])
        self.assertEqual("low", result["risk"])

    def test_policy_blocked_patch_receipt_is_valid_but_not_candidate_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = validate(fixture(Path(temp_dir), protected=True))

        self.assertTrue(result["valid"])
        self.assertFalse(result["patch_candidate_ready"])
        self.assertFalse(result["patch_policy_allowed"])
        self.assertEqual("high", result["risk"])
        self.assertEqual("C", result["route"])

    def test_patch_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            item = fixture(Path(temp_dir))
            item["patch"].write_bytes(item["patch"].read_bytes() + b"\n")
            result = validate(item)

        self.assertFalse(result["valid"])
        self.assertIn("patch_record", {failure["rule"] for failure in result["failures"]})

    def test_receipt_tampering_and_wrong_expected_digest_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            item = fixture(Path(temp_dir))
            value = json.loads(item["receipt"].read_text(encoding="utf-8"))
            value["quality_gate"]["passed"] = True
            item["receipt"].write_bytes(
                validator.validate_implementation_patch.canonical_bytes(value)
            )
            result = validate(item)
            self.assertFalse(result["valid"])
            self.assertEqual("receipt_sha256", result["failures"][0]["rule"])

            item["sha256"] = validator.validate_implementation_result.sha256_bytes(
                item["receipt"].read_bytes()
            )
            result = validate(item)
            self.assertFalse(result["valid"])
            self.assertIn(
                "quality_gate",
                {failure["rule"] for failure in result["failures"]},
            )

    def test_result_or_workspace_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            item = fixture(Path(temp_dir))
            item["result"].write_bytes(item["result"].read_bytes() + b"\n")
            result = validate(item)
            self.assertFalse(result["valid"])
            self.assertIn(
                "implementation_result",
                {failure["rule"] for failure in result["failures"]},
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            item = fixture(Path(temp_dir))
            (item["workspace"] / "extra.txt").write_text("drift\n", encoding="utf-8")
            result = validate(item)
            self.assertFalse(result["valid"])
            self.assertIn("patch_record", {failure["rule"] for failure in result["failures"]})

    def test_input_boundaries_and_policy_drift_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            item = fixture(Path(temp_dir))
            internal = item["workspace"] / "internal.patch"
            internal.write_bytes(item["patch"].read_bytes())
            item["patch"] = internal
            with self.assertRaisesRegex(ValueError, "outside the implementation workspace"):
                validate(item)

            path = Path(temp_dir) / "policy.json"
            policy = json.loads(json.dumps(validator.EXPECTED_POLICY))
            policy["require_retained_patch"] = False
            path.write_text(json.dumps(policy), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match"):
                validator.load_policy(path)

    def test_state_change_during_validation_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            item = fixture(Path(temp_dir))
            snapshot = validator.generate_complete_patch.repository_snapshot(
                item["workspace"]
            )
            changed_snapshot = {**snapshot, "status": snapshot["status"] + b"drift"}
            with mock.patch.object(
                validator.generate_complete_patch,
                "repository_snapshot",
                side_effect=[snapshot, changed_snapshot],
            ):
                result = validate(item)

        self.assertFalse(result["valid"])
        self.assertEqual("state_changed", result["failures"][-1]["rule"])

    def test_cli_refuses_policy_override(self) -> None:
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
                "--receipt",
                "receipt.json",
                "--receipt-sha256",
                "0" * 64,
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
