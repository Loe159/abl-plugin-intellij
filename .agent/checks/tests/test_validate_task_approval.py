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
MODULE_PATH = CHECKS_DIR / "validate_task_approval.py"
REPO_ROOT = CHECKS_DIR.parents[1]
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location("validate_task_approval", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)
import test_approve_task as approval_helpers


def prepare(temp: Path) -> tuple[Path, Path, Path, str]:
    repo, run, initialization_receipt, initialization_digest = approval_helpers.prepare(temp)
    policies = validator.approve_task.load_policies()
    approval_receipt = run.parent / "approval-receipt.json"
    assessment = validator.approve_task.assess_approval(
        repo,
        run,
        initialization_receipt,
        initialization_digest,
        approval_receipt,
        "local-reviewer",
        policies,
    )
    args = validator.argparse.Namespace(
        repo=repo,
        run=run,
        receipt=initialization_receipt,
        receipt_sha256=initialization_digest,
        approval_receipt=approval_receipt,
        approver="local-reviewer",
        confirm=assessment["required_confirmation"],
    )
    result = validator.approve_task.approve(args, policies, assessment)
    return repo, run, approval_receipt, result["approval_receipt_sha256"]


def validate(repo: Path, run: Path, receipt: Path, digest: str) -> dict[str, object]:
    return validator.validate(repo, run, receipt, digest, validator.load_policies())


class ValidateTaskApprovalTest(unittest.TestCase):
    def test_repository_policy_is_exact_validation_only_and_non_authorizing(self) -> None:
        policies = validator.load_policies()

        self.assertEqual(validator.EXPECTED_POLICY, policies["approval_validation"])
        self.assertEqual("validation-only", policies["approval_validation"]["mode"])
        self.assertNotIn("codex", json.dumps(policies["approval_validation"]).lower())

    def test_reverse_transition_changes_only_frontmatter_status(self) -> None:
        approved = (
            b"---\r\nstatus: approved\r\nrisk: low\r\n---\r\n\r\n"
            b"# Goal\r\n\r\nstatus: approved\r\n"
        )

        awaiting = validator.awaiting_task_bytes(approved)

        self.assertEqual(1, awaiting.count(b"status: awaiting_approval"))
        self.assertEqual(1, awaiting.count(b"status: approved"))

    def test_valid_approval_is_accepted_read_only_without_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = prepare(Path(temp_dir))
            before = approval_helpers.snapshot(run)
            receipt_before = receipt.read_bytes()
            result = validate(repo, run, receipt, digest)
            after = approval_helpers.snapshot(run)
            receipt_after = receipt.read_bytes()

        self.assertTrue(result["valid"], result["failures"])
        self.assertEqual(before, after)
        self.assertEqual(receipt_before, receipt_after)
        self.assertTrue(result["task_approved"])
        self.assertTrue(result["research_ready"])
        for field in validator.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_wrong_digest_rejects_before_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, _digest = prepare(Path(temp_dir))
            receipt.write_text("not json", encoding="utf-8")
            result = validate(repo, run, receipt, "0" * 64)

        self.assertEqual("receipt_sha256", result["failures"][0]["rule"])

    def test_rehashed_metadata_identity_transition_and_binding_changes_are_rejected(self) -> None:
        mutations = [
            ("receipt_schema", lambda value: value.update(unexpected=True)),
            ("receipt_metadata", lambda value: value.update(authorized=True)),
            ("receipt_identity", lambda value: value.update(run="C:/different")),
            ("receipt_digest", lambda value: value.update(confirmation_sha256=12)),
            ("transition_mismatch", lambda value: value.update(pre_task_sha256="0" * 64)),
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

    def test_run_drift_unapproved_state_dirty_repo_and_head_mismatch_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = prepare(Path(temp_dir))
            task = run / "task.md"
            task.write_text(
                task.read_text(encoding="utf-8").replace("Fix", "Change"),
                encoding="utf-8",
            )
            drifted = validate(repo, run, receipt, digest)
            self.assertIn("transition_mismatch", [item["rule"] for item in drifted["failures"]])

        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = prepare(Path(temp_dir))
            task = run / "task.md"
            task.write_text(
                task.read_text(encoding="utf-8").replace(
                    "status: approved",
                    "status: awaiting_approval",
                ),
                encoding="utf-8",
            )
            unapproved = validate(repo, run, receipt, digest)
            self.assertIn("approved_state", [item["rule"] for item in unapproved["failures"]])

        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = prepare(Path(temp_dir))
            (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
            dirty = validate(repo, run, receipt, digest)
            self.assertIn("clean_worktree", [item["rule"] for item in dirty["failures"]])

        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = prepare(Path(temp_dir))
            approval_helpers.initialization_helpers.helpers.git(
                repo,
                "commit",
                "--allow-empty",
                "-m",
                "later",
            )
            moved = validate(repo, run, receipt, digest)
            self.assertIn("repo_head_match", [item["rule"] for item in moved["failures"]])

    def test_secret_approver_is_rejected_without_echoing_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, _digest = prepare(Path(temp_dir))
            secret = "github_pat_" + ("A" * 24)
            value = json.loads(receipt.read_text(encoding="utf-8"))
            value["approver_declaration"] = secret
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
            inside = repo / "approval-receipt.json"
            inside.write_bytes(receipt.read_bytes())
            with self.assertRaisesRegex(ValueError, "outside"):
                validate(repo, run, inside, digest)
            inside_run = run / "approval-receipt.json"
            inside_run.write_bytes(receipt.read_bytes())
            with self.assertRaisesRegex(ValueError, "outside the portable run"):
                validate(repo, run, inside_run, digest)
            inside_run.unlink()
            copied = temp / "copied-approval-receipt.json"
            copied.write_bytes(receipt.read_bytes())
            moved = validate(repo, run, copied, digest)
            self.assertIn("transition_mismatch", [item["rule"] for item in moved["failures"]])
            with self.assertRaisesRegex(ValueError, "64 lowercase"):
                validate(repo, run, receipt, "bad")
            link = temp / "approval-receipt-link.json"
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
                "--approval-receipt",
                str(REPO_ROOT / "none.json"),
                "--approval-receipt-sha256",
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

    def test_real_cli_validates_without_stage_authorization(self) -> None:
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
                    "--approval-receipt",
                    str(receipt),
                    "--approval-receipt-sha256",
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
        self.assertTrue(result["task_approved"])
        self.assertFalse(result["stage_start_authorized"])
        self.assertFalse(result["authorized"])


if __name__ == "__main__":
    unittest.main()
