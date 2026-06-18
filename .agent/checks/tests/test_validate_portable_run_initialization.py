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
MODULE_PATH = CHECKS_DIR / "validate_portable_run_initialization.py"
REPO_ROOT = CHECKS_DIR.parents[1]
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location("validate_portable_run_initialization", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)
import test_initialize_portable_run as helpers


def prepare(temp: Path) -> tuple[Path, Path, Path, str]:
    repo, input_path, run, receipt = helpers.prepare(temp)
    result = validator.initialize_portable_run.initialize(
        repo,
        input_path,
        run,
        receipt,
        validator.initialize_portable_run.load_policies(),
    )
    return repo, run, receipt, result["receipt_sha256"]


def validate(repo: Path, run: Path, receipt: Path, digest: str) -> dict[str, object]:
    return validator.validate(repo, run, receipt, digest, validator.load_policies())


class ValidatePortableRunInitializationTest(unittest.TestCase):
    def test_repository_policy_is_exact_validation_only_and_non_authorizing(self) -> None:
        policies = validator.load_policies()

        self.assertEqual(validator.EXPECTED_POLICY, policies["validation"])
        self.assertEqual("validation-only", policies["validation"]["mode"])
        self.assertNotIn("codex", json.dumps(policies["validation"]).lower())

    def test_valid_initial_run_is_accepted_read_only_without_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = prepare(Path(temp_dir))
            before = {path.name: path.read_bytes() for path in run.glob("*.md")}
            result = validate(repo, run, receipt, digest)
            after = {path.name: path.read_bytes() for path in run.glob("*.md")}

        self.assertTrue(result["valid"], result["failures"])
        self.assertEqual(before, after)
        self.assertTrue(result["run_initialized"])
        self.assertFalse(result["task_approved"])
        self.assertFalse(result["research_ready"])
        for field in validator.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_wrong_digest_rejects_before_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, _digest = prepare(Path(temp_dir))
            receipt.write_text("not json", encoding="utf-8")
            result = validate(repo, run, receipt, "0" * 64)

        self.assertEqual("receipt_sha256", result["failures"][0]["rule"])

    def test_rehashed_metadata_identity_manifest_and_binding_changes_are_rejected(self) -> None:
        mutations = [
            ("receipt_metadata", lambda value: value.update(authorized=True)),
            ("receipt_identity", lambda value: value.update(run="C:/different")),
            (
                "receipt_manifest",
                lambda value: value["manifest"][0].update(sha256="0" * 64),
            ),
            (
                "trusted_binding_mismatch",
                lambda value: value["bindings"][0].update(sha256="0" * 64),
            ),
        ]
        for expected, mutate in mutations:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp_dir:
                repo, run, receipt, _digest = prepare(Path(temp_dir))
                value = json.loads(receipt.read_text(encoding="utf-8"))
                mutate(value)
                receipt.write_text(json.dumps(value), encoding="utf-8")
                result = validate(repo, run, receipt, validator.sha256_bytes(receipt.read_bytes()))
                self.assertFalse(result["valid"])
                self.assertIn(expected, [item["rule"] for item in result["failures"]])

    def test_run_drift_approval_dirty_repo_and_head_mismatch_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = prepare(Path(temp_dir))
            task = run / "task.md"
            task.write_text(
                task.read_text(encoding="utf-8").replace("Fix", "Change"),
                encoding="utf-8",
            )
            drifted = validate(repo, run, receipt, digest)
            self.assertIn("receipt_manifest", [item["rule"] for item in drifted["failures"]])

        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = prepare(Path(temp_dir))
            task = run / "task.md"
            task.write_text(
                task.read_text(encoding="utf-8").replace(
                    "status: awaiting_approval",
                    "status: approved",
                ),
                encoding="utf-8",
            )
            approved = validate(repo, run, receipt, digest)
            self.assertIn("receipt_manifest", [item["rule"] for item in approved["failures"]])

        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = prepare(Path(temp_dir))
            (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
            dirty = validate(repo, run, receipt, digest)
            self.assertIn("clean_worktree", [item["rule"] for item in dirty["failures"]])

        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = prepare(Path(temp_dir))
            helpers.helpers.git(repo, "commit", "--allow-empty", "-m", "later")
            moved = validate(repo, run, receipt, digest)
            self.assertIn("repo_head_match", [item["rule"] for item in moved["failures"]])

    def test_secret_run_is_rejected_without_echoing_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, _digest = prepare(Path(temp_dir))
            secret = "github_pat_" + ("A" * 24)
            task = run / "task.md"
            task.write_text(
                task.read_text(encoding="utf-8").replace(
                    "Fix the verified behavior.",
                    secret,
                ),
                encoding="utf-8",
            )
            value = json.loads(receipt.read_text(encoding="utf-8"))
            value["manifest"] = validator.initialize_portable_run.manifest(
                run,
                list(validator.load_policies()["artifact"]["artifacts"]),
            )
            receipt.write_text(json.dumps(value), encoding="utf-8")
            result = validate(repo, run, receipt, validator.sha256_bytes(receipt.read_bytes()))

        self.assertIn("high_confidence_secret", [item["rule"] for item in result["failures"]])
        self.assertNotIn(secret, json.dumps(result))

    def test_state_drift_during_validation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = prepare(Path(temp_dir))
            original = validator.initialize_portable_run.binding_records
            calls = 0

            def drifting_bindings(names: list[str]) -> list[dict[str, object]]:
                nonlocal calls
                records = original(names)
                calls += 1
                if calls == 3:
                    receipt.write_text(receipt.read_text(encoding="utf-8") + "\n", encoding="utf-8")
                return records

            with mock.patch.object(
                validator.initialize_portable_run,
                "binding_records",
                side_effect=drifting_bindings,
            ):
                result = validate(repo, run, receipt, digest)

        self.assertIn("state_changed", [item["rule"] for item in result["failures"]])

    def test_refuses_internal_symlink_policy_override_and_invalid_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = prepare(temp)
            inside = repo / "receipt.json"
            inside.write_bytes(receipt.read_bytes())
            with self.assertRaisesRegex(ValueError, "outside"):
                validate(repo, run, inside, digest)
            with self.assertRaisesRegex(ValueError, "64 lowercase"):
                validate(repo, run, receipt, "bad")
            link = temp / "receipt-link.json"
            try:
                link.symlink_to(receipt)
            except OSError:
                link = None
            if link is not None:
                with self.assertRaisesRegex(ValueError, "symbolic links"):
                    validate(repo, run, link, digest)

        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--repo",
                str(REPO_ROOT),
                "--run",
                str(REPO_ROOT),
                "--receipt",
                str(REPO_ROOT / "none.json"),
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

    def test_real_cli_validates_without_approval_or_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = prepare(Path(temp_dir))
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--repo",
                    str(repo),
                    "--run",
                    str(run),
                    "--receipt",
                    str(receipt),
                    "--receipt-sha256",
                    digest,
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            result = json.loads(completed.stdout)

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(result["valid"])
        self.assertFalse(result["task_approved"])
        self.assertFalse(result["authorized"])


if __name__ == "__main__":
    unittest.main()
