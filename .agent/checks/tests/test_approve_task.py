from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "approve_task.py"
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location("approve_task", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
approval = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = approval
SPEC.loader.exec_module(approval)
import test_initialize_portable_run as initialization_helpers


def prepare(temp: Path) -> tuple[Path, Path, Path, str]:
    repo, input_path, run, receipt = initialization_helpers.prepare(temp)
    initialized = approval.initialize_portable_run.initialize(
        repo,
        input_path,
        run,
        receipt,
        approval.initialize_portable_run.load_policies(),
    )
    return repo, run, receipt, initialized["receipt_sha256"]


def snapshot(run: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in run.glob("*.md")}


def cli(
    action: str,
    repo: Path,
    run: Path,
    receipt: Path,
    receipt_sha256: str,
    *extra: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            action,
            "--repo",
            str(repo),
            "--run",
            str(run),
            "--receipt",
            str(receipt),
            "--receipt-sha256",
            receipt_sha256,
            "--approval-receipt",
            str(run.parent / "approval-receipt.json"),
            "--approver",
            "local-reviewer",
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


class ApproveTaskTest(unittest.TestCase):
    def test_repository_policy_is_exact_and_non_authorizing(self) -> None:
        policies = approval.load_policies()

        self.assertEqual(approval.EXPECTED_POLICY, policies["approval"])
        self.assertEqual("research", policies["approval"]["readiness_stage"])
        self.assertNotIn("codex", json.dumps(policies["approval"]).lower())

    def test_check_is_read_only_and_binds_receipt_run_task_approver_and_controls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = prepare(Path(temp_dir))
            before = snapshot(run)
            completed = cli("check", repo, run, receipt, digest)
            result = json.loads(completed.stdout)
            after = snapshot(run)

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(result["approvable"])
        self.assertEqual(before, after)
        for value in (
            digest,
            result["run_snapshot_sha256"],
            result["task_sha256"],
            result["approval_bindings_sha256"],
            "approver=local-reviewer",
        ):
            self.assertIn(value, result["required_confirmation"])
        self.assertFalse(result["authorized"])
        self.assertFalse(result["task_approval_authenticated"])

    def test_approve_changes_only_task_status_and_makes_research_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = prepare(Path(temp_dir))
            before = snapshot(run)
            checked = json.loads(cli("check", repo, run, receipt, digest).stdout)
            completed = cli(
                "approve",
                repo,
                run,
                receipt,
                digest,
                "--confirm",
                checked["required_confirmation"],
            )
            result = json.loads(completed.stdout)
            after = snapshot(run)
            receipt_value = json.loads(
                (run.parent / "approval-receipt.json").read_text(encoding="utf-8")
            )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(result["task_approved"])
        self.assertTrue(result["research_ready"])
        self.assertTrue(result["run_mutated"])
        self.assertTrue(result["receipt_written"])
        self.assertFalse(result["stage_start_authorized"])
        self.assertFalse(result["agent_invocation_authorized"])
        self.assertEqual(
            before["task.md"].replace(b"status: awaiting_approval", b"status: approved"),
            after["task.md"],
        )
        self.assertEqual(
            {name: content for name, content in before.items() if name != "task.md"},
            {name: content for name, content in after.items() if name != "task.md"},
        )
        self.assertTrue(receipt_value["task_approved"])
        self.assertTrue(receipt_value["research_ready"])
        self.assertFalse(receipt_value["task_approval_authenticated"])
        self.assertEqual(result["post_task_sha256"], receipt_value["post_task_sha256"])

    def test_wrong_digest_confirmation_and_replay_do_not_mutate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = prepare(Path(temp_dir))
            before = snapshot(run)
            wrong_digest = cli("check", repo, run, receipt, "0" * 64)
            self.assertEqual(before, snapshot(run))
            failures = json.loads(wrong_digest.stdout)["failures"]
            self.assertIn("initialization_validation", [item["rule"] for item in failures])
            self.assertIn("receipt_sha256", [item["rule"] for item in failures])

            checked = json.loads(cli("check", repo, run, receipt, digest).stdout)
            wrong = cli("approve", repo, run, receipt, digest, "--confirm", "wrong")
            self.assertEqual(before, snapshot(run))
            failures = json.loads(wrong.stdout)["failures"]
            self.assertIn("confirmation_mismatch", [item["rule"] for item in failures])

            approved = cli(
                "approve",
                repo,
                run,
                receipt,
                digest,
                "--confirm",
                checked["required_confirmation"],
            )
            replay = cli("check", repo, run, receipt, digest)
            self.assertEqual(0, approved.returncode, approved.stderr)
            self.assertEqual(2, replay.returncode)
            self.assertIn(
                "receipt_manifest",
                [item["rule"] for item in json.loads(replay.stdout)["failures"]],
            )

    def test_tampered_receipt_run_and_dirty_repo_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = prepare(Path(temp_dir))
            value = json.loads(receipt.read_text(encoding="utf-8"))
            value["authorized"] = True
            receipt.write_text(json.dumps(value), encoding="utf-8")
            rehashed = approval.apply_stage_output.sha256_bytes(receipt.read_bytes())
            tampered = cli("check", repo, run, receipt, rehashed)
            self.assertEqual(2, tampered.returncode)
            self.assertIn(
                "receipt_metadata",
                [item["rule"] for item in json.loads(tampered.stdout)["failures"]],
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = prepare(Path(temp_dir))
            task = run / "task.md"
            task.write_text(
                task.read_text(encoding="utf-8").replace("Fix", "Change"),
                encoding="utf-8",
            )
            drifted = cli("check", repo, run, receipt, digest)
            self.assertEqual(2, drifted.returncode)
            self.assertIn(
                "receipt_manifest",
                [item["rule"] for item in json.loads(drifted.stdout)["failures"]],
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = prepare(Path(temp_dir))
            (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
            dirty = cli("check", repo, run, receipt, digest)
            failures = json.loads(dirty.stdout)["failures"]
            self.assertIn("clean_worktree", [item["rule"] for item in failures])

    def test_stale_approver_or_run_confirmation_does_not_mutate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = prepare(Path(temp_dir))
            checked = json.loads(cli("check", repo, run, receipt, digest).stdout)
            stale_approver = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "approve",
                    "--repo",
                    str(repo),
                    "--run",
                    str(run),
                    "--receipt",
                    str(receipt),
                    "--receipt-sha256",
                    digest,
                    "--approval-receipt",
                    str(run.parent / "approval-receipt.json"),
                    "--approver",
                    "different-reviewer",
                    "--confirm",
                    checked["required_confirmation"],
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertIn(
                "confirmation_mismatch",
                [item["rule"] for item in json.loads(stale_approver.stdout)["failures"]],
            )

            task = run / "task.md"
            task.write_text(
                task.read_text(encoding="utf-8").replace("Fix", "Change"),
                encoding="utf-8",
            )
            stale_run = cli(
                "approve",
                repo,
                run,
                receipt,
                digest,
                "--confirm",
                checked["required_confirmation"],
            )
            self.assertEqual(2, stale_run.returncode)
            self.assertIn(
                "receipt_manifest",
                [item["rule"] for item in json.loads(stale_run.stdout)["failures"]],
            )

    def test_last_moment_control_drift_does_not_mutate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = prepare(Path(temp_dir))
            policies = approval.load_policies()
            assessment = approval.assess_approval(
                repo,
                run,
                receipt,
                digest,
                run.parent / "approval-receipt.json",
                "local-reviewer",
                policies,
            )
            before = snapshot(run)
            original = approval.approval_bindings
            calls = 0

            def drifting_bindings(policy: dict[str, object]) -> tuple[list[dict[str, object]], str]:
                nonlocal calls
                calls += 1
                records, current_digest = original(policy)
                return records, ("0" * 64 if calls == 2 else current_digest)

            args = argparse.Namespace(
                repo=repo,
                run=run,
                receipt=receipt,
                receipt_sha256=digest,
                approval_receipt=run.parent / "approval-receipt.json",
                approver="local-reviewer",
                confirm=assessment["required_confirmation"],
            )
            with mock.patch.object(
                approval,
                "approval_bindings",
                side_effect=drifting_bindings,
            ):
                result = approval.approve(args, policies, assessment)

            self.assertFalse(result["task_approved"])
            self.assertEqual(before, snapshot(run))
            self.assertIn("state_changed", [item["rule"] for item in result["failures"]])
            self.assertFalse((run.parent / "approval-receipt.json").exists())

    def test_receipt_write_failure_rolls_back_without_approving(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = prepare(Path(temp_dir))
            policies = approval.load_policies()
            approval_receipt = run.parent / "approval-receipt.json"
            assessment = approval.assess_approval(
                repo,
                run,
                receipt,
                digest,
                approval_receipt,
                "local-reviewer",
                policies,
            )
            before = snapshot(run)
            args = argparse.Namespace(
                repo=repo,
                run=run,
                receipt=receipt,
                receipt_sha256=digest,
                approval_receipt=approval_receipt,
                approver="local-reviewer",
                confirm=assessment["required_confirmation"],
            )
            with mock.patch.object(
                approval.initialize_portable_run,
                "write_exclusive",
                side_effect=OSError("fixture failure"),
            ), self.assertRaisesRegex(ValueError, "rollback succeeded"):
                approval.approve(args, policies, assessment)

            self.assertEqual(before, snapshot(run))
            self.assertFalse(approval_receipt.exists())

    def test_post_mutation_failure_rolls_back_task_and_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = prepare(Path(temp_dir))
            policies = approval.load_policies()
            approval_receipt = run.parent / "approval-receipt.json"
            assessment = approval.assess_approval(
                repo,
                run,
                receipt,
                digest,
                approval_receipt,
                "local-reviewer",
                policies,
            )
            before = snapshot(run)
            args = argparse.Namespace(
                repo=repo,
                run=run,
                receipt=receipt,
                receipt_sha256=digest,
                approval_receipt=approval_receipt,
                approver="local-reviewer",
                confirm=assessment["required_confirmation"],
            )
            original = approval.check_stage_readiness.check_readiness

            def not_ready_after_mutation(*args: object, **kwargs: object) -> dict[str, object]:
                result = original(*args, **kwargs)
                if (run / "task.md").read_bytes() != before["task.md"]:
                    result["ready"] = False
                return result

            with mock.patch.object(
                approval.check_stage_readiness,
                "check_readiness",
                side_effect=not_ready_after_mutation,
            ), self.assertRaisesRegex(ValueError, "rollback succeeded"):
                approval.approve(args, policies, assessment)

            self.assertEqual(before, snapshot(run))
            self.assertFalse(approval_receipt.exists())

    def test_internal_paths_symlinks_policy_override_and_secret_approver_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = prepare(temp)
            internal = repo / "receipt.json"
            internal.write_bytes(receipt.read_bytes())
            result = cli("check", repo, run, internal, digest)
            self.assertEqual(1, result.returncode)
            self.assertIn("outside", result.stderr)
            internal.unlink()

            link = temp / "receipt-link.json"
            try:
                link.symlink_to(receipt)
            except OSError:
                link = None
            if link is not None:
                linked = cli("check", repo, run, link, digest)
                self.assertEqual(1, linked.returncode)
                self.assertIn("symbolic links", linked.stderr)

            approval_receipt = run.parent / "approval-receipt.json"
            approval_receipt.write_text("existing\n", encoding="utf-8")
            existing = cli("check", repo, run, receipt, digest)
            self.assertEqual(1, existing.returncode)
            self.assertIn("already exists", existing.stderr)
            approval_receipt.unlink()

            override = cli("check", repo, run, receipt, digest, "--policy", "untrusted")
            self.assertEqual(2, override.returncode)
            self.assertIn("unrecognized arguments", override.stderr)

            secret = "github_pat_" + ("A" * 24)
            secret_result = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "check",
                    "--repo",
                    str(repo),
                    "--run",
                    str(run),
                    "--receipt",
                    str(receipt),
                    "--receipt-sha256",
                    digest,
                    "--approval-receipt",
                    str(run.parent / "approval-receipt.json"),
                    "--approver",
                    secret,
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(1, secret_result.returncode)
            self.assertIn("secret signature", secret_result.stderr)
            self.assertNotIn(secret, secret_result.stderr + secret_result.stdout)


if __name__ == "__main__":
    unittest.main()
