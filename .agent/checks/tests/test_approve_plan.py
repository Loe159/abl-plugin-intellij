from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "approve_plan.py"
REPO_ROOT = CHECKS_DIR.parents[1]
TEMPLATES = REPO_ROOT / ".agent" / "templates"
POLICY_DIR = REPO_ROOT / ".agent" / "policies"
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location("approve_plan", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
approval = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = approval
SPEC.loader.exec_module(approval)
import test_validate_stage_application as application_helpers


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def create_repo(path: Path) -> str:
    path.mkdir()
    git(path, "init")
    git(path, "config", "user.email", "tests@example.invalid")
    git(path, "config", "user.name", "Tests")
    (path / "README.md").write_text("base\n", encoding="utf-8")
    git(path, "add", "README.md")
    git(path, "commit", "-m", "base")
    return git(path, "rev-parse", "HEAD")


def create_run(destination: Path, base: str, risk: str = "medium") -> None:
    shutil.copytree(TEMPLATES, destination)
    for path in destination.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        text = text.replace("{{issue}}", "123").replace("{{base_commit}}", base)
        text = text.replace("{{risk}}", risk)
        text = re.sub(r"\{\{[a-z0-9_]+\}\}", "Reviewed workflow evidence.", text)
        if path.name == "task.md":
            text = text.replace("status: awaiting_approval", "status: approved")
        if path.name == "research.md":
            text = text.replace("status: pending", "status: complete")
        path.write_text(text, encoding="utf-8")


def snapshot(run: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in run.glob("*.md")}


def prepare(temp: Path, risk: str = "medium") -> tuple[Path, Path, Path, str]:
    if risk != "medium":
        raise ValueError("Applied-plan test helper currently supports only medium risk")
    return application_helpers.apply_stage(temp, "plan")


def cli(
    action: str,
    repo: Path,
    run: Path,
    receipt: Path,
    digest: str,
    *extra: str,
    approval_receipt: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    approval_receipt = approval_receipt or (run.parent / "plan-approval-receipt.json")
    return subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            action,
            "--repo",
            str(repo),
            "--run",
            str(run),
            "--application-receipt",
            str(receipt),
            "--application-receipt-sha256",
            digest,
            "--approval-receipt",
            str(approval_receipt),
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


class ApprovePlanTest(unittest.TestCase):
    def test_repository_policy_is_valid_and_exact_transition(self) -> None:
        policies = approval.load_policies()
        self.assertEqual(3, policies["approval"]["version"])
        self.assertEqual("portable_plan_approval", policies["approval"]["purpose"])
        self.assertEqual("awaiting_approval", policies["approval"]["current_status"])
        self.assertEqual("approved", policies["approval"]["approved_status"])
        self.assertEqual("plan", policies["approval"]["readiness_stage"])
        self.assertTrue(policies["approval"]["require_valid_plan_application"])
        self.assertTrue(policies["approval"]["require_absent_approval_receipt"])

    def test_policy_rejects_unsafe_or_drifted_transition(self) -> None:
        policies = approval.load_policies()
        for expected, mutate in [
            ("explicitly be true", lambda policy: policy.update(require_clean_worktree=False)),
            ("explicitly be true", lambda policy: policy.update(require_valid_plan_application=False)),
            ("explicitly be true", lambda policy: policy.update(require_absent_approval_receipt=False)),
            ("transition", lambda policy: policy.update(approved_status="blocked")),
            ("readiness_stage", lambda policy: policy.update(readiness_stage="implement")),
        ]:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp_dir:
                policy = json.loads((POLICY_DIR / "plan-approval.json").read_text(encoding="utf-8"))
                mutate(policy)
                path = Path(temp_dir) / "policy.json"
                path.write_text(json.dumps(policy), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, expected):
                    approval.load_approval_policy(path, policies["artifact"], policies["readiness"])

    def test_check_is_read_only_and_binds_exact_run_and_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = prepare(temp)
            before = snapshot(run)
            completed = cli("check", repo, run, receipt, digest)
            result = json.loads(completed.stdout)
            after = snapshot(run)

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(result["approvable"])
        self.assertFalse(result["plan_approved"])
        self.assertFalse(result["run_mutated"])
        self.assertFalse(result["authorized"])
        self.assertFalse(result["implementation_authorized"])
        self.assertIn(result["run_snapshot_sha256"], result["required_confirmation"])
        self.assertIn(result["plan_sha256"], result["required_confirmation"])
        self.assertIn(digest, result["required_confirmation"])
        self.assertIn(str(run.parent / "plan-approval-receipt.json"), result["required_confirmation"])
        self.assertEqual(before, after)
        self.assertFalse((run.parent / "plan-approval-receipt.json").exists())

    def test_approve_changes_only_status_and_makes_medium_implementation_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = prepare(temp)
            before = snapshot(run)
            checked = json.loads(cli("check", repo, run, receipt, digest).stdout)
            completed = cli(
                "approve",
                repo,
                run,
                receipt,
                digest,
                "--approver",
                "local-reviewer",
                "--confirm",
                checked["required_confirmation"],
            )
            result = json.loads(completed.stdout)
            receipt_value = json.loads(
                (run.parent / "plan-approval-receipt.json").read_text(encoding="utf-8")
            )
            after = snapshot(run)
            plan = (run / "plan.md").read_text(encoding="utf-8")

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(result["plan_approved"])
        self.assertTrue(result["run_mutated"])
        self.assertTrue(result["receipt_written"])
        self.assertTrue(result["implementation_ready"])
        self.assertFalse(result["implementation_authorized"])
        self.assertFalse(result["publication_authorized"])
        self.assertEqual(result["approval_receipt_sha256"], approval.apply_stage_output.sha256_bytes(
            json.dumps(receipt_value, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        ))
        self.assertEqual(3, receipt_value["plan_approval_receipt_version"])
        self.assertTrue(receipt_value["plan_approved"])
        self.assertFalse(receipt_value["implementation_authorized"])
        self.assertEqual(result["post_plan_sha256"], receipt_value["post_plan_sha256"])
        self.assertEqual(
            before["plan.md"].replace(b"status: awaiting_approval", b"status: approved"),
            after["plan.md"],
        )
        self.assertEqual(
            {name: content for name, content in before.items() if name != "plan.md"},
            {name: content for name, content in after.items() if name != "plan.md"},
        )
        self.assertIn("status: approved", plan)

    def test_approved_plan_reports_implementation_ready_without_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = prepare(temp)
            checked = json.loads(cli("check", repo, run, receipt, digest).stdout)
            completed = cli(
                "approve",
                repo,
                run,
                receipt,
                digest,
                "--approver",
                "local-reviewer",
                "--confirm",
                checked["required_confirmation"],
            )
            result = json.loads(completed.stdout)

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(result["implementation_ready"])
        self.assertFalse(result["implementation_authorized"])

    def test_missing_research_dirty_repo_wrong_confirmation_and_replay_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = prepare(temp)
            research = run / "research.md"
            research.write_text(
                research.read_text(encoding="utf-8").replace("status: complete", "status: pending"),
                encoding="utf-8",
            )
            missing = cli("check", repo, run, receipt, digest)
            self.assertIn("plan_prerequisites", [item["rule"] for item in json.loads(missing.stdout)["failures"]])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = prepare(temp)
            checked = json.loads(cli("check", repo, run, receipt, digest).stdout)
            before = snapshot(run)
            wrong = cli("approve", repo, run, receipt, digest, "--approver", "reviewer", "--confirm", "wrong")
            self.assertEqual(before, snapshot(run))
            self.assertIn("confirmation_mismatch", [item["rule"] for item in json.loads(wrong.stdout)["failures"]])
            approved = cli(
                "approve",
                repo,
                run,
                receipt,
                digest,
                "--approver",
                "reviewer",
                "--confirm",
                checked["required_confirmation"],
            )
            replay = cli(
                "check",
                repo,
                run,
                receipt,
                digest,
                approval_receipt=run.parent / "second-plan-approval-receipt.json",
            )
            self.assertEqual(0, approved.returncode, approved.stderr)
            self.assertIn("current_status", [item["rule"] for item in json.loads(replay.stdout)["failures"]])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = prepare(temp)
            (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
            dirty = cli("check", repo, run, receipt, digest)
            self.assertIn("clean_worktree", [item["rule"] for item in json.loads(dirty.stdout)["failures"]])

    def test_stale_confirmation_and_blocked_artifact_do_not_mutate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = prepare(temp)
            checked = json.loads(cli("check", repo, run, receipt, digest).stdout)
            progress = run / "progress.md"
            progress.write_text(
                progress.read_text(encoding="utf-8").replace(
                    "Reviewed workflow evidence.",
                    "Independent valid change.",
                    1,
                ),
                encoding="utf-8",
            )
            before = snapshot(run)
            stale = cli(
                "approve",
                repo,
                run,
                receipt,
                digest,
                "--approver",
                "reviewer",
                "--confirm",
                checked["required_confirmation"],
            )
            self.assertEqual(before, snapshot(run))
            self.assertIn("plan_application", [item["rule"] for item in json.loads(stale.stdout)["failures"]])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = prepare(temp)
            progress = run / "progress.md"
            progress.write_text(
                progress.read_text(encoding="utf-8").replace("status: not_started", "status: blocked"),
                encoding="utf-8",
            )
            blocked = cli("check", repo, run, receipt, digest)
            self.assertIn("plan_prerequisites", [item["rule"] for item in json.loads(blocked.stdout)["failures"]])

    def test_missing_or_invalid_plan_application_receipt_blocks_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = prepare(temp)

            missing = cli("check", repo, run, temp / "missing.json", digest)
            invalid = cli("check", repo, run, receipt, "0" * 64)

        self.assertEqual(2, missing.returncode)
        self.assertIn("plan_application", [item["rule"] for item in json.loads(missing.stdout)["failures"]])
        self.assertEqual(2, invalid.returncode)
        self.assertIn("plan_application", [item["rule"] for item in json.loads(invalid.stdout)["failures"]])

    def test_refuses_internal_run_symlink_policy_override_and_secret_approver(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = prepare(temp)
            inside = repo / "run"
            shutil.copytree(run, inside)
            internal = cli("check", repo, inside, receipt, digest)
            self.assertEqual(1, internal.returncode)
            self.assertIn("outside", internal.stderr)

            link = temp / "run-link"
            try:
                link.symlink_to(run, target_is_directory=True)
            except OSError:
                return
            linked = cli("check", repo, link, receipt, digest)
            self.assertEqual(1, linked.returncode)
            self.assertIn("symbolic links", linked.stderr)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = prepare(temp)
            internal_receipt = repo / "plan-approval-receipt.json"
            internal_result = cli("check", repo, run, receipt, digest, approval_receipt=internal_receipt)
            self.assertEqual(1, internal_result.returncode)
            self.assertIn("outside", internal_result.stderr)
            inside_run_receipt = run / "plan-approval-receipt.json"
            inside_run_result = cli("check", repo, run, receipt, digest, approval_receipt=inside_run_receipt)
            self.assertEqual(1, inside_run_result.returncode)
            self.assertIn("outside the portable run", inside_run_result.stderr)
            existing_receipt = run.parent / "plan-approval-receipt.json"
            existing_receipt.write_text("existing\n", encoding="utf-8")
            existing = cli("check", repo, run, receipt, digest)
            self.assertEqual(1, existing.returncode)
            self.assertIn("already exists", existing.stderr)
            existing_receipt.unlink()
            override = cli("check", repo, run, receipt, digest, "--approval-policy", "untrusted")
            self.assertEqual(2, override.returncode)
            self.assertIn("unrecognized arguments", override.stderr)
            checked = json.loads(cli("check", repo, run, receipt, digest).stdout)
            secret = "github_" + "pat_" + ("A" * 24)
            secret_result = cli(
                "approve",
                repo,
                run,
                receipt,
                digest,
                "--approver",
                secret,
                "--confirm",
                checked["required_confirmation"],
            )
            self.assertEqual(1, secret_result.returncode)
            self.assertIn("secret signature", secret_result.stderr)
            self.assertNotIn(secret, secret_result.stderr + secret_result.stdout)


if __name__ == "__main__":
    unittest.main()
