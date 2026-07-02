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
from unittest import mock


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "build_implementation_handoff.py"
REPO_ROOT = CHECKS_DIR.parents[1]
TEMPLATES = REPO_ROOT / ".agent" / "templates"
POLICY_DIR = REPO_ROOT / ".agent" / "policies"
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location("build_implementation_handoff", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
handoff = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = handoff
SPEC.loader.exec_module(handoff)
import test_validate_plan_approval as plan_approval_helpers


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


def create_run(destination: Path, base: str, risk: str = "medium", approved: bool = True) -> None:
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
        if path.name == "plan.md" and approved:
            text = text.replace("status: awaiting_approval", "status: approved")
        path.write_text(text, encoding="utf-8")


def prepare(
    temp: Path,
    risk: str = "medium",
    approved: bool = True,
) -> tuple[Path, Path, Path, str]:
    if risk == "medium" and approved:
        return plan_approval_helpers.prepare(temp)
    repo = temp / "repo"
    base = create_repo(repo)
    run = temp / "run"
    create_run(run, base, risk, approved)
    return repo, run, temp / "missing-plan-approval-receipt.json", "0" * 64


def build(
    repo: Path,
    run: Path,
    output: Path,
    receipt: Path,
    digest: str,
    policies: dict[str, object] | None = None,
) -> dict[str, object]:
    return handoff.build_handoff(
        repo,
        run,
        output,
        receipt,
        digest,
        policies or handoff.load_policies(),
    )


def cli(
    repo: Path,
    run: Path,
    output: Path,
    receipt: Path,
    digest: str,
    *extra: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "--repo",
            str(repo),
            "--run",
            str(run),
            "--output",
            str(output),
            "--plan-approval-receipt",
            str(receipt),
            "--plan-approval-receipt-sha256",
            digest,
            "--format",
            "json",
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


class BuildImplementationHandoffTest(unittest.TestCase):
    def test_repository_policy_is_valid_and_conservative(self) -> None:
        policies = handoff.load_policies()
        self.assertEqual(2, policies["handoff"]["version"])
        self.assertTrue(policies["handoff"]["require_approved_plan"])
        self.assertTrue(policies["handoff"]["require_valid_plan_approval"])
        self.assertEqual("implement", policies["handoff"]["readiness_stage"])
        self.assertEqual(
            ["task.md", "research.md", "plan.md"],
            policies["handoff"]["content_artifacts"],
        )

    def test_policy_rejects_unsafe_or_expanded_contract(self) -> None:
        policies = handoff.load_policies()
        for expected, mutate in [
            ("explicitly be true", lambda policy: policy.update(require_approved_plan=False)),
            (
                "explicitly be true",
                lambda policy: policy.update(require_valid_plan_approval=False),
            ),
            ("non-authorizing", lambda policy: policy.update(mode="write")),
            (
                "exactly task.md",
                lambda policy: policy.update(
                    content_artifacts=["task.md", "research.md", "plan.md", "progress.md"]
                ),
            ),
        ]:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp_dir:
                policy = json.loads(
                    (POLICY_DIR / "implementation-handoff.json").read_text(encoding="utf-8")
                )
                mutate(policy)
                path = Path(temp_dir) / "policy.json"
                path.write_text(json.dumps(policy), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, expected):
                    handoff.load_handoff_policy(
                        path,
                        policies["artifact"],
                        policies["readiness"],
                    )

    def test_bundle_is_reproducible_bounded_and_non_authorizing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = prepare(temp)
            first = temp / "first.json"
            second = temp / "second.json"
            first_result = build(repo, run, first, receipt, digest)
            second_result = build(repo, run, second, receipt, digest)
            bundle = json.loads(first.read_text(encoding="utf-8"))
            first_bytes = first.read_bytes()
            second_bytes = second.read_bytes()

        self.assertTrue(first_result["produced"])
        self.assertEqual(first_bytes, second_bytes)
        self.assertEqual(first_result["sha256"], second_result["sha256"])
        for field in (
            "authorized",
            "agent_invocation_authorized",
            "implementation_authorized",
            "repository_mutation_authorized",
            "network_authorized",
            "publication_authorized",
        ):
            self.assertFalse(bundle[field])
        self.assertEqual("handoff-only", bundle["mode"])
        self.assertEqual(digest, bundle["plan_approval_receipt_sha256"])
        self.assertEqual(
            ["task.md", "research.md", "plan.md"],
            [record["name"] for record in bundle["artifacts"]],
        )
        expected_manifest_names = sorted(handoff.load_policies()["artifact"]["artifacts"])
        self.assertEqual(expected_manifest_names, sorted(record["name"] for record in bundle["run_manifest"]))
        self.assertTrue(all("content" not in record for record in bundle["run_manifest"]))

    def test_low_risk_still_requires_approved_plan_and_valid_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = prepare(temp, "low", approved=False)
            policies = handoff.load_policies()
            readiness = handoff.check_stage_readiness.check_readiness(
                run,
                "implement",
                policies["artifact"],
                policies["readiness"],
            )
            output = temp / "handoff.json"
            result = build(repo, run, output, receipt, digest, policies)

        self.assertTrue(readiness["ready"])
        self.assertFalse(result["produced"])
        self.assertFalse(output.exists())
        self.assertIn("approved_plan", [item["rule"] for item in result["failures"]])
        self.assertIn("plan_approval_receipt", [item["rule"] for item in result["failures"]])

    def test_approved_plan_without_valid_approval_receipt_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, _receipt, digest = prepare(temp)
            missing_receipt = temp / "missing.json"
            output = temp / "handoff.json"
            result = build(repo, run, output, missing_receipt, digest)

        self.assertFalse(result["produced"])
        self.assertFalse(output.exists())
        self.assertIn("plan_approval_receipt", [item["rule"] for item in result["failures"]])

    def test_not_ready_dirty_or_head_mismatch_do_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = prepare(temp)
            research = run / "research.md"
            research.write_text(
                research.read_text(encoding="utf-8").replace("status: complete", "status: pending"),
                encoding="utf-8",
            )
            output = temp / "not-ready.json"
            result = build(repo, run, output, receipt, digest)
            self.assertIn("implementation_readiness", [item["rule"] for item in result["failures"]])
            self.assertIn("plan_approval_receipt", [item["rule"] for item in result["failures"]])
            self.assertFalse(output.exists())

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = prepare(temp)
            (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
            dirty = build(repo, run, temp / "dirty.json", receipt, digest)
            self.assertIn("clean_worktree", [item["rule"] for item in dirty["failures"]])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = prepare(temp)
            (repo / "README.md").write_text("next\n", encoding="utf-8")
            git(repo, "add", "README.md")
            git(repo, "commit", "-m", "next")
            mismatch = build(repo, run, temp / "mismatch.json", receipt, digest)
            self.assertIn("repo_head_match", [item["rule"] for item in mismatch["failures"]])

    def test_secret_and_size_limit_do_not_write_or_echo_secret(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = prepare(temp)
            secret = "github_" + "pat_" + ("A" * 24)
            progress = run / "progress.md"
            progress.write_text(progress.read_text(encoding="utf-8") + secret, encoding="utf-8")
            output = temp / "secret.json"
            result = build(repo, run, output, receipt, digest)
            self.assertNotIn(secret, json.dumps(result))
            self.assertIn("high_confidence_secret", [item["rule"] for item in result["failures"]])
            self.assertFalse(output.exists())

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = prepare(temp)
            policies = handoff.load_policies()
            policies["handoff"]["max_bundle_bytes"] = 1
            output = temp / "large.json"
            result = build(repo, run, output, receipt, digest, policies)
            self.assertIn("max_bundle_bytes", [item["rule"] for item in result["failures"]])
            self.assertFalse(output.exists())

    def test_run_drift_during_build_does_not_write_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = prepare(temp)
            output = temp / "drift.json"
            original = handoff.artifact_record
            changed = False

            def drifting_record(name: str, path: Path, include_content: bool) -> dict[str, object]:
                nonlocal changed
                record = original(name, path, include_content)
                if not changed:
                    progress = run / "progress.md"
                    progress.write_text(
                        progress.read_text(encoding="utf-8").replace(
                            "Reviewed workflow evidence.",
                            "Concurrent valid change.",
                            1,
                        ),
                        encoding="utf-8",
                    )
                    changed = True
                return record

            with mock.patch.object(handoff, "artifact_record", side_effect=drifting_record):
                result = build(repo, run, output, receipt, digest)

        self.assertFalse(result["produced"])
        self.assertFalse(output.exists())
        self.assertIn("state_changed", [item["rule"] for item in result["failures"]])

    def test_refuses_internal_paths_existing_output_symlinks_and_policy_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = prepare(temp)
            inside_run = repo / "run"
            shutil.copytree(run, inside_run)
            with self.assertRaisesRegex(ValueError, "outside"):
                build(repo, inside_run, temp / "inside-run.json", receipt, digest)
            with self.assertRaisesRegex(ValueError, "outside"):
                build(repo, run, repo / "handoff.json", receipt, digest)
            with self.assertRaisesRegex(ValueError, "outside the run"):
                build(repo, run, run / "handoff.json", receipt, digest)
            existing = temp / "existing.json"
            existing.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already exists"):
                build(repo, run, existing, receipt, digest)
            self.assertEqual("keep", existing.read_text(encoding="utf-8"))

            link = temp / "run-link"
            try:
                link.symlink_to(run, target_is_directory=True)
            except OSError:
                return
            with self.assertRaisesRegex(ValueError, "symbolic links"):
                build(repo, link, temp / "linked.json", receipt, digest)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = prepare(temp)
            completed = cli(
                repo,
                run,
                temp / "handoff.json",
                receipt,
                digest,
                "--handoff-policy",
                "untrusted",
            )
            self.assertEqual(2, completed.returncode)
            self.assertIn("unrecognized arguments", completed.stderr)

    def test_cli_produces_external_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = prepare(temp)
            output = temp / "handoff.json"
            completed = cli(repo, run, output, receipt, digest)
            result = json.loads(completed.stdout)

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(result["produced"])
        self.assertEqual(digest, result["plan_approval_receipt_sha256"])
        self.assertFalse(result["implementation_authorized"])


if __name__ == "__main__":
    unittest.main()
