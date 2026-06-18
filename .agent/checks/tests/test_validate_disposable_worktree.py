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
MODULE_PATH = CHECKS_DIR / "validate_disposable_worktree.py"
REPO_ROOT = CHECKS_DIR.parents[1]
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location("validate_disposable_worktree", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)
import test_prepare_disposable_worktree as helpers


def prepare(temp: Path) -> tuple[Path, Path, Path, str]:
    source = temp / "source"
    base = helpers.create_repo(source)
    workspace = temp / "workspace"
    receipt = temp / "receipt.json"
    result = validator.prepare_disposable_worktree.prepare(
        source,
        base,
        workspace,
        receipt,
        validator.prepare_disposable_worktree.load_policy(),
    )
    assert result["prepared"]
    return source, workspace, receipt, result["receipt_sha256"]


def cleanup(source: Path, workspace: Path) -> None:
    helpers.cleanup(source, workspace)


def validate(
    source: Path,
    workspace: Path,
    receipt: Path,
    digest: str,
) -> dict[str, object]:
    return validator.validate(source, workspace, receipt, digest, validator.load_policy())


class ValidateDisposableWorktreeTest(unittest.TestCase):
    def test_repository_policy_is_exact_validation_only_and_non_authorizing(self) -> None:
        policy = validator.load_policy()

        self.assertEqual(validator.EXPECTED_POLICY, policy)
        self.assertEqual("validation-only", policy["mode"])
        self.assertNotIn("codex", json.dumps(policy).lower())

    def test_valid_receipt_and_workspace_are_accepted_without_authorization_or_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source, workspace, receipt, digest = prepare(temp)
            before = helpers.git(source, "worktree", "list", "--porcelain")
            result = validate(source, workspace, receipt, digest)
            after = helpers.git(source, "worktree", "list", "--porcelain")

            self.assertTrue(result["valid"], result["failures"])
            self.assertEqual(before, after)
            for field in validator.FALSE_FIELDS:
                self.assertFalse(result[field])
            cleanup(source, workspace)

    def test_wrong_digest_rejects_before_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "source"
            helpers.create_repo(source)
            workspace = temp / "workspace"
            workspace.mkdir()
            receipt = temp / "receipt.json"
            receipt.write_text("not json", encoding="utf-8")
            result = validate(source, workspace, receipt, "0" * 64)

        self.assertEqual("receipt_sha256", result["failures"][0]["rule"])

    def test_rehashed_authorization_identity_invariant_and_binding_changes_are_rejected(self) -> None:
        mutations = [
            ("receipt_metadata", lambda value: value.update(workspace_use_authorized=True)),
            ("receipt_identity", lambda value: value.update(workspace="C:/different")),
            (
                "receipt_invariants",
                lambda value: value["invariants"].update(workspace_clean=False),
            ),
            (
                "trusted_binding_mismatch",
                lambda value: value["bindings"][0].update(sha256="0" * 64),
            ),
        ]
        for expected, mutate in mutations:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp_dir:
                temp = Path(temp_dir)
                source, workspace, receipt, digest = prepare(temp)
                value = json.loads(receipt.read_text(encoding="utf-8"))
                mutate(value)
                receipt.write_text(json.dumps(value), encoding="utf-8")
                result = validate(source, workspace, receipt, validator.sha256_bytes(receipt.read_bytes()))
                self.assertFalse(result["valid"])
                self.assertIn(expected, [item["rule"] for item in result["failures"]])
                cleanup(source, workspace)

    def test_dirty_branched_or_moved_workspace_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source, workspace, receipt, digest = prepare(temp)
            (workspace / "dirty.txt").write_text("dirty\n", encoding="utf-8")
            dirty = validate(source, workspace, receipt, digest)
            self.assertIn("workspace_clean", [item["rule"] for item in dirty["failures"]])
            cleanup(source, workspace)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source, workspace, receipt, digest = prepare(temp)
            helpers.git(workspace, "switch", "-c", "unexpected")
            branched = validate(source, workspace, receipt, digest)
            rules = [item["rule"] for item in branched["failures"]]
            self.assertIn("workspace_detached", rules)
            self.assertIn("workspace_registered", rules)
            cleanup(source, workspace)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source, workspace, receipt, digest = prepare(temp)
            wrong = temp / "wrong"
            wrong.mkdir()
            moved = validate(source, wrong, receipt, digest)
            self.assertIn("receipt_identity", [item["rule"] for item in moved["failures"]])
            cleanup(source, workspace)

    def test_dirty_source_or_missing_registration_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source, workspace, receipt, digest = prepare(temp)
            (source / "dirty.txt").write_text("dirty\n", encoding="utf-8")
            dirty = validate(source, workspace, receipt, digest)
            self.assertIn("source_clean", [item["rule"] for item in dirty["failures"]])
            cleanup(source, workspace)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source, workspace, receipt, digest = prepare(temp)
            base = helpers.git(source, "rev-parse", "HEAD")
            helpers.git(source, "worktree", "remove", "--force", str(workspace))
            subprocess.run(
                ["git", "clone", "--no-checkout", str(source), str(workspace)],
                check=True,
                capture_output=True,
            )
            helpers.git(workspace, "checkout", "--detach", base)
            unregistered = validate(source, workspace, receipt, digest)
            self.assertIn(
                "workspace_registered",
                [item["rule"] for item in unregistered["failures"]],
            )

    def test_state_drift_during_validation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source, workspace, receipt, digest = prepare(temp)
            original = validator.binding_records
            calls = 0

            def drifting_bindings(names: list[str]) -> list[dict[str, object]]:
                nonlocal calls
                records = original(names)
                calls += 1
                if calls == 3:
                    receipt.write_text(receipt.read_text(encoding="utf-8") + "\n", encoding="utf-8")
                return records

            with mock.patch.object(validator, "binding_records", side_effect=drifting_bindings):
                result = validate(source, workspace, receipt, digest)
            self.assertIn("state_changed", [item["rule"] for item in result["failures"]])
            cleanup(source, workspace)

    def test_refuses_internal_symlink_policy_override_and_invalid_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source, workspace, receipt, digest = prepare(temp)
            inside = source / "receipt.json"
            inside.write_bytes(receipt.read_bytes())
            with self.assertRaisesRegex(ValueError, "outside"):
                validate(source, workspace, inside, digest)
            with self.assertRaisesRegex(ValueError, "64 lowercase"):
                validate(source, workspace, receipt, "bad")
            link = temp / "receipt-link.json"
            try:
                link.symlink_to(receipt)
            except OSError:
                cleanup(source, workspace)
                return
            with self.assertRaisesRegex(ValueError, "symbolic links"):
                validate(source, workspace, link, digest)
            cleanup(source, workspace)

        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--source",
                str(REPO_ROOT),
                "--workspace",
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

    def test_real_cli_validates_without_authorizing_use(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source, workspace, receipt, digest = prepare(temp)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--source",
                    str(source),
                    "--workspace",
                    str(workspace),
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
            self.assertFalse(result["workspace_use_authorized"])
            cleanup(source, workspace)


if __name__ == "__main__":
    unittest.main()
