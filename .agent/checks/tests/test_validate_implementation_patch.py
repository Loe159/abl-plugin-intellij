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
MODULE_PATH = CHECKS_DIR / "validate_implementation_patch.py"
REPO_ROOT = CHECKS_DIR.parents[1]
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("validate_implementation_patch", MODULE_PATH)
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


def prepare_repo(root: Path, path: str = "app.txt") -> tuple[Path, str]:
    repo = root / "workspace"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "Test Fixture")
    (repo / "app.txt").write_text("base\n", encoding="utf-8")
    git(repo, "add", "app.txt")
    git(repo, "commit", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("change\n", encoding="utf-8")
    return repo.resolve(), base


def prepare_clean_repo(root: Path) -> tuple[Path, str]:
    repo = root / "workspace"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "Test Fixture")
    (repo / "app.txt").write_text("base\n", encoding="utf-8")
    git(repo, "add", "app.txt")
    git(repo, "commit", "-m", "base")
    return repo.resolve(), git(repo, "rev-parse", "HEAD")


def identity(repo: Path, base: str) -> dict[str, object]:
    return {
        "issue": 58,
        "risk": "medium",
        "base_commit": base,
        "workspace": str(repo),
        "runner_id": "test-runner",
        "preflight_sha256": "2" * 64,
        "start_authorization_receipt_sha256": "3" * 64,
    }


def result_bytes(session: dict[str, object]) -> bytes:
    return validator.validate_implementation_result.canonical_result_bytes(
        {
            "result_version": 1,
            "purpose": "implementation_session_result",
            "mode": "untrusted-runner-output",
            "status": "completed",
            **session,
            "summary": "Completed fixture.",
            "workspace_changed": True,
            "patch_generated": False,
            "deterministic_checks_run": False,
            "publication_requested": False,
            "network_requested": False,
            "next_action": "deterministic_patch_generation",
        }
    )


class ValidateImplementationPatchTest(unittest.TestCase):
    def test_policy_is_exact_non_authorizing_and_requires_quality_gate_later(self) -> None:
        policy = validator.load_policy()

        self.assertEqual(validator.EXPECTED_POLICY, policy)
        self.assertTrue(policy["quality_gate_execution_required"])
        self.assertTrue(policy["require_nonempty_patch_for_candidate"])
        self.assertTrue(policy["require_policy_allowed_for_candidate"])

    def test_allowed_patch_writes_receipt_and_is_candidate_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo, base = prepare_repo(root)
            session = identity(repo, base)
            patch = root / "candidate.patch"
            receipt = root / "receipt.json"

            result = validator.validate_patch(
                REPO_ROOT,
                validator.captured_execution(result_bytes(session), b""),
                session,
                patch,
                receipt,
                validator.load_policy(),
            )

            self.assertTrue(result["post_validation_complete"])
            self.assertTrue(result["patch_candidate_ready"])
            self.assertTrue(result["patch"]["policy_allowed"])
            self.assertEqual("low", result["risk"]["risk"])
            self.assertTrue(patch.is_file())
            self.assertTrue(receipt.is_file())
            self.assertFalse(result["quality_gate"]["completed"])
            for field in validator.FALSE_FIELDS:
                self.assertFalse(result[field])

    def test_empty_patch_is_complete_but_not_candidate_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo, base = prepare_clean_repo(root)
            session = identity(repo, base)

            result = validator.validate_patch(
                REPO_ROOT,
                validator.captured_execution(result_bytes(session), b""),
                session,
                root / "candidate.patch",
                root / "receipt.json",
                validator.load_policy(),
            )

            self.assertTrue(result["post_validation_complete"])
            self.assertFalse(result["patch_candidate_ready"])
            self.assertTrue(result["patch"]["policy_allowed"])
            self.assertFalse(result["patch"]["nonempty"])
            self.assertEqual(0, result["patch"]["facts"]["file_count"])

    def test_protected_patch_is_complete_but_not_candidate_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo, base = prepare_repo(root, ".agent/blocked.txt")
            session = identity(repo, base)

            result = validator.validate_patch(
                REPO_ROOT,
                validator.captured_execution(result_bytes(session), b""),
                session,
                root / "candidate.patch",
                root / "receipt.json",
                validator.load_policy(),
            )

            self.assertTrue(result["post_validation_complete"])
            self.assertFalse(result["patch_candidate_ready"])
            self.assertFalse(result["patch"]["policy_allowed"])
            self.assertEqual("high", result["risk"]["risk"])
            self.assertEqual("C", result["risk"]["route"])

    def test_invalid_result_does_not_call_generator_or_write_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo, base = prepare_repo(root)
            session = identity(repo, base)
            wrong = dict(session)
            wrong["preflight_sha256"] = "4" * 64
            generator = mock.Mock()
            patch = root / "candidate.patch"
            receipt = root / "receipt.json"

            result = validator.validate_patch(
                REPO_ROOT,
                validator.captured_execution(result_bytes(wrong), b""),
                session,
                patch,
                receipt,
                validator.load_policy(),
                generator=generator,
            )

            self.assertFalse(result["post_validation_complete"])
            self.assertFalse(result["patch_candidate_ready"])
            generator.assert_not_called()
            self.assertFalse(patch.exists())
            self.assertFalse(receipt.exists())

    def test_output_boundaries_and_policy_drift_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo, base = prepare_repo(root)
            session = identity(repo, base)
            with self.assertRaisesRegex(ValueError, "outside the implementation workspace"):
                validator.validate_patch(
                    REPO_ROOT,
                    validator.captured_execution(result_bytes(session), b""),
                    session,
                    repo / "candidate.patch",
                    root / "receipt.json",
                    validator.load_policy(),
                )
            with self.assertRaisesRegex(ValueError, "must be distinct"):
                validator.validate_output_targets(
                    REPO_ROOT,
                    repo,
                    root / "same",
                    root / "same",
                    validator.load_policy(),
                )

            path = root / "policy.json"
            policy = json.loads(json.dumps(validator.EXPECTED_POLICY))
            policy["require_policy_allowed_for_candidate"] = False
            path.write_text(json.dumps(policy), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match"):
                validator.load_policy(path)

    def test_receipt_failure_removes_generated_patch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo, base = prepare_repo(root)
            session = identity(repo, base)
            patch = root / "candidate.patch"
            receipt = root / "receipt.json"
            with mock.patch.object(
                validator,
                "write_exclusive",
                side_effect=OSError("synthetic write failure"),
            ):
                with self.assertRaisesRegex(OSError, "synthetic write failure"):
                    validator.validate_patch(
                        REPO_ROOT,
                        validator.captured_execution(result_bytes(session), b""),
                        session,
                        patch,
                        receipt,
                        validator.load_policy(),
                    )

            self.assertFalse(patch.exists())
            self.assertFalse(receipt.exists())

    def test_generator_failure_after_write_removes_partial_patch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo, base = prepare_repo(root)
            session = identity(repo, base)
            patch = root / "candidate.patch"
            receipt = root / "receipt.json"

            def failing_generator(
                _repo: Path,
                _base: str,
                output: Path,
                _policy: Path,
                _force: bool,
            ) -> dict[str, object]:
                output.write_bytes(b"partial")
                raise ValueError("synthetic generator failure")

            with self.assertRaisesRegex(ValueError, "synthetic generator failure"):
                validator.validate_patch(
                    REPO_ROOT,
                    validator.captured_execution(result_bytes(session), b""),
                    session,
                    patch,
                    receipt,
                    validator.load_policy(),
                    generator=failing_generator,
                )

            self.assertFalse(patch.exists())
            self.assertFalse(receipt.exists())

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
                "--patch-output",
                "patch.diff",
                "--receipt-output",
                "receipt.json",
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
