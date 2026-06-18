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
MODULE_PATH = CHECKS_DIR / "validate_disposable_worktree_cleanup.py"
REPO_ROOT = CHECKS_DIR.parents[1]
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location("validate_disposable_worktree_cleanup", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)
import test_cleanup_disposable_worktree as cleanup_helpers


def cleaned(temp: Path) -> tuple[Path, Path, Path, str, Path, str]:
    source, workspace, preparation_receipt, preparation_digest = cleanup_helpers.prepare(temp)
    cleanup_receipt = temp / "cleanup.json"
    result = cleanup_helpers.run_cleanup(
        source,
        workspace,
        preparation_receipt,
        preparation_digest,
        cleanup_receipt,
    )
    assert result["cleaned"]
    return (
        source,
        workspace,
        preparation_receipt,
        preparation_digest,
        cleanup_receipt,
        result["cleanup_receipt_sha256"],
    )


def validate(values: tuple[Path, Path, Path, str, Path, str]) -> dict[str, object]:
    return validator.validate(*values, validator.load_policy())


class ValidateDisposableWorktreeCleanupTest(unittest.TestCase):
    def test_repository_policy_is_exact_validation_only_and_non_authorizing(self) -> None:
        policy = validator.load_policy()

        self.assertEqual(validator.EXPECTED_POLICY, policy)
        self.assertEqual("validation-only", policy["mode"])
        self.assertNotIn("codex", json.dumps(policy).lower())

    def test_real_cleanup_receipt_is_accepted_read_only_without_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            values = cleaned(Path(temp_dir))
            source = values[0]
            before = cleanup_helpers.validation_helpers.helpers.git(
                source,
                "worktree",
                "list",
                "--porcelain",
            )
            result = validate(values)
            after = cleanup_helpers.validation_helpers.helpers.git(
                source,
                "worktree",
                "list",
                "--porcelain",
            )

            self.assertTrue(result["valid"], result["failures"])
            self.assertEqual(before, after)
            for field in validator.FALSE_FIELDS:
                self.assertFalse(result[field])

    def test_wrong_digest_rejects_before_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            values = list(cleaned(Path(temp_dir)))
            values[4].write_text("not json", encoding="utf-8")
            values[5] = "0" * 64
            result = validate(tuple(values))

        self.assertEqual("cleanup_receipt_sha256", result["failures"][0]["rule"])

    def test_rehashed_authorization_identity_postcondition_and_binding_changes_are_rejected(
        self,
    ) -> None:
        mutations = [
            ("cleanup_receipt_metadata", lambda value: value.update(workspace_use_authorized=True)),
            ("cleanup_receipt_identity", lambda value: value.update(workspace="C:/different")),
            (
                "cleanup_receipt_postconditions",
                lambda value: value["postconditions"].update(workspace_absent=False),
            ),
            (
                "trusted_cleanup_binding_mismatch",
                lambda value: value["bindings"][0].update(sha256="0" * 64),
            ),
        ]
        for expected, mutate in mutations:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp_dir:
                values = list(cleaned(Path(temp_dir)))
                cleanup_receipt = values[4]
                value = json.loads(cleanup_receipt.read_text(encoding="utf-8"))
                mutate(value)
                cleanup_receipt.write_text(json.dumps(value), encoding="utf-8")
                values[5] = validator.validate_disposable_worktree.sha256_bytes(
                    cleanup_receipt.read_bytes()
                )
                result = validate(tuple(values))
                self.assertIn(expected, [item["rule"] for item in result["failures"]])

    def test_changed_preparation_receipt_and_cross_receipt_digest_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            values = list(cleaned(Path(temp_dir)))
            preparation_receipt = values[2]
            preparation_receipt.write_text(
                preparation_receipt.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            result = validate(tuple(values))
            self.assertIn("preparation_receipt_sha256", [item["rule"] for item in result["failures"]])

        with tempfile.TemporaryDirectory() as temp_dir:
            values = list(cleaned(Path(temp_dir)))
            cleanup_receipt = values[4]
            value = json.loads(cleanup_receipt.read_text(encoding="utf-8"))
            value["preparation_receipt_sha256"] = "0" * 64
            cleanup_receipt.write_text(json.dumps(value), encoding="utf-8")
            values[5] = validator.validate_disposable_worktree.sha256_bytes(
                cleanup_receipt.read_bytes()
            )
            result = validate(tuple(values))
            self.assertIn("cleanup_receipt_identity", [item["rule"] for item in result["failures"]])

        with tempfile.TemporaryDirectory() as temp_dir:
            values = list(cleaned(Path(temp_dir)))
            cleanup_receipt = values[4]
            value = json.loads(cleanup_receipt.read_text(encoding="utf-8"))
            value["base_commit"] = "0" * 40
            cleanup_receipt.write_text(json.dumps(value), encoding="utf-8")
            values[5] = validator.validate_disposable_worktree.sha256_bytes(
                cleanup_receipt.read_bytes()
            )
            result = validate(tuple(values))
            self.assertIn("receipt_base_match", [item["rule"] for item in result["failures"]])

    def test_recreated_or_registered_workspace_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            values = cleaned(Path(temp_dir))
            workspace = values[1]
            workspace.mkdir()
            result = validate(values)
            self.assertIn("workspace_absent", [item["rule"] for item in result["failures"]])

        with tempfile.TemporaryDirectory() as temp_dir:
            values = cleaned(Path(temp_dir))
            source, workspace = values[:2]
            base = cleanup_helpers.validation_helpers.helpers.git(source, "rev-parse", "HEAD")
            cleanup_helpers.validation_helpers.helpers.git(
                source,
                "worktree",
                "add",
                "--detach",
                str(workspace),
                base,
            )
            result = validate(values)
            rules = [item["rule"] for item in result["failures"]]
            self.assertIn("workspace_absent", rules)
            self.assertIn("workspace_unregistered", rules)
            cleanup_helpers.validation_helpers.cleanup(source, workspace)

    def test_dirty_or_moved_source_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            values = cleaned(Path(temp_dir))
            source = values[0]
            (source / "dirty.txt").write_text("dirty\n", encoding="utf-8")
            result = validate(values)
            self.assertIn("source_clean", [item["rule"] for item in result["failures"]])

        with tempfile.TemporaryDirectory() as temp_dir:
            values = cleaned(Path(temp_dir))
            source = values[0]
            (source / "README.md").write_text("next\n", encoding="utf-8")
            cleanup_helpers.validation_helpers.helpers.git(source, "add", "README.md")
            cleanup_helpers.validation_helpers.helpers.git(source, "commit", "-m", "next")
            result = validate(values)
            self.assertIn("source_head_match", [item["rule"] for item in result["failures"]])

    def test_state_drift_during_validation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            values = cleaned(Path(temp_dir))
            cleanup_receipt = values[4]
            original = validator.validate_disposable_worktree.binding_records
            calls = 0

            def drifting_bindings(names: list[str]) -> list[dict[str, object]]:
                nonlocal calls
                records = original(names)
                calls += 1
                if calls == 4:
                    cleanup_receipt.write_text(
                        cleanup_receipt.read_text(encoding="utf-8") + "\n",
                        encoding="utf-8",
                    )
                return records

            with mock.patch.object(
                validator.validate_disposable_worktree,
                "binding_records",
                side_effect=drifting_bindings,
            ):
                result = validate(values)
            self.assertIn("state_changed", [item["rule"] for item in result["failures"]])

    def test_refuses_internal_symlink_policy_override_and_invalid_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            values = list(cleaned(temp))
            source = values[0]
            inside = source / "cleanup.json"
            inside.write_bytes(values[4].read_bytes())
            values[4] = inside
            with self.assertRaisesRegex(ValueError, "outside"):
                validate(tuple(values))

            second = temp / "second"
            second.mkdir()
            values = list(cleaned(second))
            with self.assertRaisesRegex(ValueError, "64 lowercase"):
                validator.validate(*values[:3], "bad", *values[4:], validator.load_policy())

            link = temp / "cleanup-link.json"
            try:
                link.symlink_to(values[4])
            except OSError:
                return
            values[4] = link
            with self.assertRaisesRegex(ValueError, "symbolic links"):
                validate(tuple(values))

        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--source",
                str(REPO_ROOT),
                "--workspace",
                str(REPO_ROOT.parent / "absent"),
                "--preparation-receipt",
                str(REPO_ROOT / "none.json"),
                "--preparation-receipt-sha256",
                "0" * 64,
                "--cleanup-receipt",
                str(REPO_ROOT / "none-cleanup.json"),
                "--cleanup-receipt-sha256",
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

    def test_real_cli_validates_without_authorizing_or_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            values = cleaned(Path(temp_dir))
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--source",
                    str(values[0]),
                    "--workspace",
                    str(values[1]),
                    "--preparation-receipt",
                    str(values[2]),
                    "--preparation-receipt-sha256",
                    values[3],
                    "--cleanup-receipt",
                    str(values[4]),
                    "--cleanup-receipt-sha256",
                    values[5],
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
            self.assertFalse(result["agent_invocation_authorized"])


if __name__ == "__main__":
    unittest.main()
