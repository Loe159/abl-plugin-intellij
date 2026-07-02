from __future__ import annotations

import argparse
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
MODULE_PATH = CHECKS_DIR / "apply_stage_output.py"
REPO_ROOT = CHECKS_DIR.parents[1]
TEMPLATES = REPO_ROOT / ".agent" / "templates"
POLICY_DIR = REPO_ROOT / ".agent" / "policies"
PROMPTS = REPO_ROOT / ".agent" / "prompts"
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("apply_stage_output", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
application = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = application
SPEC.loader.exec_module(application)
import test_validate_task_approval as approval_helpers


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


def fill_text(text: str, base: str, marker: str = "Recorded evidence.") -> str:
    text = text.replace("{{issue}}", "123").replace("{{base_commit}}", base)
    text = text.replace("{{risk}}", "medium")
    return re.sub(r"\{\{[a-z0-9_]+\}\}", marker, text)


def create_run(destination: Path, base: str) -> None:
    shutil.copytree(TEMPLATES, destination)
    for path in destination.glob("*.md"):
        text = fill_text(path.read_text(encoding="utf-8"), base)
        if path.name == "task.md":
            text = text.replace("status: awaiting_approval", "status: approved")
        path.write_text(text, encoding="utf-8")


def set_status(path: Path, old: str, new: str) -> None:
    path.write_text(
        path.read_text(encoding="utf-8").replace(f"status: {old}", f"status: {new}", 1),
        encoding="utf-8",
    )


def create_response(path: Path, artifact: str, base: str, status: str) -> None:
    text = fill_text((TEMPLATES / artifact).read_text(encoding="utf-8"), base, "New reviewed evidence.")
    old = "pending" if artifact in {"research.md", "progress.md", "review.md"} else "awaiting_approval"
    path.write_text(text.replace(f"status: {old}", f"status: {status}"), encoding="utf-8")


def prepare(temp: Path, stage: str) -> tuple[Path, Path, Path, str, Path]:
    receipt = None
    digest = None
    application_receipt = None
    application_digest = None
    policies = application.load_policies()
    if stage == "research":
        repo, run, receipt, digest = approval_helpers.prepare(temp)
        base = git(repo, "rev-parse", "HEAD")
    else:
        repo, run, receipt, digest = approval_helpers.prepare(temp)
        base = git(repo, "rev-parse", "HEAD")
        research_bundle = temp / "research-bundle.json"
        research_built = application.build_stage_context.build_context(
            repo,
            run,
            "research",
            research_bundle,
            {
                "artifact": policies["artifact"],
                "prompt": policies["prompt"],
                "readiness": application.build_stage_context.check_stage_readiness.load_readiness_policy(
                    POLICY_DIR / "stage-readiness.json",
                    policies["artifact"],
                ),
                "context": policies["context"],
                "diff": policies["diff"],
            },
            PROMPTS,
            receipt,
            digest,
        )
        assert research_built["produced"], research_built
        research_response = temp / "research-response.md"
        create_response(research_response, "research.md", base, "complete")
        application_receipt = temp / "research-application-receipt.json"
        research_assessment = application.assess_application(
            repo,
            run,
            research_bundle,
            research_built["sha256"],
            research_response,
            application_receipt,
            policies,
        )
        assert research_assessment["applicable"], research_assessment
        applied = application.apply_response(
            argparse.Namespace(
                repo=repo,
                run=run,
                bundle=research_bundle,
                bundle_sha256=research_built["sha256"],
                response=research_response,
                application_receipt=application_receipt,
                reviewer="local-operator",
                confirm=research_assessment["required_confirmation"],
            ),
            policies,
            research_assessment,
        )
        assert applied["applied"], applied
        assert not applied["failures"], applied
        application_digest = applied["application_receipt_sha256"]
        if stage == "review":
            set_status(run / "plan.md", "awaiting_approval", "approved")
            set_status(run / "verification.md", "pending", "failed")
    bundle = temp / ("bundle.json" if stage == "research" else "plan-bundle.json")
    built = application.build_stage_context.build_context(
        repo,
        run,
        stage,
        bundle,
        {
            "artifact": policies["artifact"],
            "prompt": policies["prompt"],
            "readiness": application.build_stage_context.check_stage_readiness.load_readiness_policy(
                POLICY_DIR / "stage-readiness.json",
                policies["artifact"],
            ),
            "context": policies["context"],
            "diff": policies["diff"],
        },
        PROMPTS,
        receipt if stage == "research" else None,
        digest if stage == "research" else None,
        application_receipt if stage == "plan" else None,
        application_digest if stage == "plan" else None,
    )
    assert built["produced"], built
    response = temp / "response.md"
    artifact = {
        "research": "research.md",
        "plan": "plan.md",
        "review": "review.md",
    }[stage]
    status = {
        "research": "complete",
        "plan": "awaiting_approval",
        "review": "complete",
    }[stage]
    create_response(response, artifact, base, status)
    return repo, run, bundle, built["sha256"], response


def cli(action: str, repo: Path, run: Path, bundle: Path, digest: str, response: Path, *extra: str):
    return subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            action,
            "--repo",
            str(repo),
            "--run",
            str(run),
            "--bundle",
            str(bundle),
        "--bundle-sha256",
        digest,
        "--response",
        str(response),
        "--application-receipt",
        str(run.parent / "application-receipt.json"),
        *extra,
    ],
        check=False,
        capture_output=True,
        text=True,
    )


class ApplyStageOutputTest(unittest.TestCase):
    def test_repository_policy_is_valid_and_non_approving(self) -> None:
        policies = application.load_policies()
        self.assertEqual(
            ["compact-progress", "plan", "research", "review"],
            sorted(policies["application"]["stages"]),
        )
        self.assertEqual(2, policies["application"]["version"])
        self.assertEqual("pending", policies["application"]["stages"]["research"]["allowed_current_statuses"][0])
        self.assertTrue(policies["application"]["require_absent_application_receipt"])
        self.assertNotIn(
            "approved",
            policies["application"]["stages"]["plan"]["allowed_current_statuses"],
        )

    def test_policy_rejects_approved_target_and_stage_drift(self) -> None:
        policies = application.load_policies()
        for expected, mutate in [
            (
                "approved or blocked",
                lambda policy: policy["stages"]["plan"]["allowed_current_statuses"].append("approved"),
            ),
            (
                "max_application_receipt_bytes",
                lambda policy: policy.update(max_application_receipt_bytes=0),
            ),
            ("exactly match", lambda policy: policy["stages"].pop("plan")),
        ]:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp_dir:
                policy = json.loads((POLICY_DIR / "stage-application.json").read_text(encoding="utf-8"))
                mutate(policy)
                path = Path(temp_dir) / "policy.json"
                path.write_text(json.dumps(policy), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, expected):
                    application.load_application_policy(
                        path,
                        policies["output"],
                        policies["artifact"],
                    )

    def test_check_is_read_only_and_prints_content_bound_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, bundle, digest, response = prepare(temp, "research")
            before = (run / "research.md").read_bytes()

            completed = cli("check", repo, run, bundle, digest, response)
            result = json.loads(completed.stdout)
            after = (run / "research.md").read_bytes()

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(result["applicable"])
        self.assertFalse(result["applied"])
        self.assertFalse(result["authorized"])
        self.assertFalse(result["stage_authorized"])
        self.assertIn(result["bundle_sha256"], result["required_confirmation"])
        self.assertIn(result["run_snapshot_sha256"], result["required_confirmation"])
        self.assertIn(result["response_sha256"], result["required_confirmation"])
        self.assertIn(result["replaced_sha256"], result["required_confirmation"])
        self.assertIn(result["application_bindings_sha256"], result["required_confirmation"])
        self.assertIn(result["application_receipt"], result["required_confirmation"])
        self.assertEqual(before, after)
        self.assertFalse((run.parent / "application-receipt.json").exists())

    def test_apply_exact_confirmation_writes_receipt_and_replaces_only_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, bundle, digest, response = prepare(temp, "research")
            unchanged = {
                path.name: path.read_bytes()
                for path in run.glob("*.md")
                if path.name != "research.md"
            }
            checked = json.loads(cli("check", repo, run, bundle, digest, response).stdout)

            completed = cli(
                "apply",
                repo,
                run,
                bundle,
                digest,
                response,
                "--reviewer",
                "local-operator",
                "--confirm",
                checked["required_confirmation"],
            )
            result = json.loads(completed.stdout)
            final_validation = application.validate_artifacts.validate_directory(
                run,
                application.load_policies()["artifact"],
                False,
            )
            receipt = json.loads((run.parent / "application-receipt.json").read_text(encoding="utf-8"))

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertTrue(result["applied"])
            self.assertTrue(result["run_mutated"])
            self.assertTrue(result["response_applied"])
            self.assertTrue(result["copy_confirmed"])
            self.assertTrue(result["receipt_written"])
            self.assertFalse(result["authorized"])
            self.assertFalse(result["stage_authorized"])
            self.assertEqual(response.read_bytes(), (run / "research.md").read_bytes())
            self.assertEqual(unchanged, {path.name: path.read_bytes() for path in run.glob("*.md") if path.name != "research.md"})
            self.assertTrue(final_validation["valid"], final_validation["errors"])
            self.assertEqual([], list(run.glob("tmp*")))
            self.assertEqual(2, receipt["stage_application_receipt_version"])
            self.assertTrue(receipt["response_applied"])
            self.assertFalse(receipt["authorized"])
            self.assertFalse(receipt["stage_authorized"])
            self.assertEqual(result["post_run_snapshot_sha256"], receipt["post_application_run_snapshot_sha256"])
            self.assertEqual(result["response_sha256"], receipt["response_sha256"])
            self.assertEqual(result["application_receipt_sha256"], application.sha256_bytes((run.parent / "application-receipt.json").read_bytes()))

    def test_plan_application_does_not_approve_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, bundle, digest, response = prepare(temp, "plan")
            checked = json.loads(cli("check", repo, run, bundle, digest, response).stdout)

            completed = cli(
                "apply",
                repo,
                run,
                bundle,
                digest,
                response,
                "--reviewer",
                "local-operator",
                "--confirm",
                checked["required_confirmation"],
            )
            plan_text = (run / "plan.md").read_text(encoding="utf-8")

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("status: awaiting_approval", plan_text)

    def test_review_application_replaces_only_review_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, bundle, digest, response = prepare(temp, "review")
            unchanged = {
                path.name: path.read_bytes()
                for path in run.glob("*.md")
                if path.name != "review.md"
            }
            checked = json.loads(cli("check", repo, run, bundle, digest, response).stdout)

            completed = cli(
                "apply",
                repo,
                run,
                bundle,
                digest,
                response,
                "--reviewer",
                "local-operator",
                "--confirm",
                checked["required_confirmation"],
            )
            result = json.loads(completed.stdout)
            receipt = json.loads((run.parent / "application-receipt.json").read_text(encoding="utf-8"))
            response_bytes = response.read_bytes()
            review_bytes = (run / "review.md").read_bytes()
            changed = {
                path.name: path.read_bytes()
                for path in run.glob("*.md")
                if path.name != "review.md"
            }

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(result["applied"])
        self.assertTrue(result["response_applied"])
        self.assertFalse(result["authorized"])
        self.assertFalse(result["stage_authorized"])
        self.assertEqual(response_bytes, review_bytes)
        self.assertEqual(unchanged, changed)
        self.assertEqual("review", receipt["stage"])
        self.assertEqual("review.md", receipt["artifact"])
        self.assertFalse(receipt["authorized"])

    def test_wrong_or_stale_confirmation_does_not_mutate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, bundle, digest, response = prepare(temp, "research")
            checked = json.loads(cli("check", repo, run, bundle, digest, response).stdout)
            before = (run / "research.md").read_bytes()
            wrong = cli(
                "apply",
                repo,
                run,
                bundle,
                digest,
                response,
                "--reviewer",
                "local-operator",
                "--confirm",
                "wrong",
            )
            target = run / "research.md"
            target.write_text(
                target.read_text(encoding="utf-8").replace(
                    "Research has not run.",
                    "Changed evidence.",
                    1,
                ),
                encoding="utf-8",
            )
            stale_before = target.read_bytes()
            stale = cli(
                "apply",
                repo,
                run,
                bundle,
                digest,
                response,
                "--reviewer",
                "local-operator",
                "--confirm",
                checked["required_confirmation"],
            )
            stale_after = target.read_bytes()

        self.assertEqual(2, wrong.returncode)
        self.assertNotEqual(before, stale_before)
        self.assertEqual(2, stale.returncode)
        self.assertEqual(stale_before, stale_after)
        self.assertIn("confirmation_mismatch", [item["rule"] for item in json.loads(stale.stdout)["failures"]])

    def test_receipt_write_failure_rolls_back_without_replacing_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, bundle, digest, response = prepare(temp, "research")
            policies = application.load_policies()
            receipt = temp / "application-receipt.json"
            assessment = application.assess_application(
                repo,
                run,
                bundle,
                digest,
                response,
                receipt,
                policies,
            )
            args = argparse.Namespace(
                repo=repo,
                run=run,
                bundle=bundle,
                bundle_sha256=digest,
                response=response,
                application_receipt=receipt,
                reviewer="local-operator",
                confirm=assessment["required_confirmation"],
            )
            before = (run / "research.md").read_bytes()

            with mock.patch.object(application, "write_atomic_existing", side_effect=OSError("disk")):
                with self.assertRaisesRegex(ValueError, "rollback succeeded"):
                    application.apply_response(args, policies, assessment)

            self.assertEqual(before, (run / "research.md").read_bytes())
            self.assertFalse(receipt.exists())

    def test_confirmation_binds_unrelated_run_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, bundle, digest, response = prepare(temp, "research")
            checked = json.loads(cli("check", repo, run, bundle, digest, response).stdout)
            progress = run / "progress.md"
            progress.write_text(
                progress.read_text(encoding="utf-8").replace(
                    "Recorded evidence.",
                    "Independent valid progress change.",
                    1,
                ),
                encoding="utf-8",
            )
            before = progress.read_bytes()
            stale = cli(
                "apply",
                repo,
                run,
                bundle,
                digest,
                response,
                "--reviewer",
                "local-operator",
                "--confirm",
                checked["required_confirmation"],
            )
            after = progress.read_bytes()

        self.assertEqual(2, stale.returncode)
        self.assertEqual(before, after)
        self.assertIn(
            "confirmation_mismatch",
            [item["rule"] for item in json.loads(stale.stdout)["failures"]],
        )

    def test_replay_context_drift_dirty_repo_and_self_approval_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, bundle, digest, response = prepare(temp, "research")
            checked = json.loads(cli("check", repo, run, bundle, digest, response).stdout)
            applied = cli("apply", repo, run, bundle, digest, response, "--reviewer", "operator", "--confirm", checked["required_confirmation"])
            replay = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "check",
                    "--repo",
                    str(repo),
                    "--run",
                    str(run),
                    "--bundle",
                    str(bundle),
                    "--bundle-sha256",
                    digest,
                    "--response",
                    str(response),
                    "--application-receipt",
                    str(run.parent / "replay-receipt.json"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, applied.returncode, applied.stderr)
            self.assertEqual(2, replay.returncode)
            self.assertIn("current_status", [item["rule"] for item in json.loads(replay.stdout)["failures"]])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, bundle, digest, response = prepare(temp, "research")
            task = run / "task.md"
            task.write_text(
                task.read_text(encoding="utf-8").replace(
                    "Fix the verified behavior.",
                    "Changed evidence.",
                    1,
                ),
                encoding="utf-8",
            )
            drift = cli("check", repo, run, bundle, digest, response)
            self.assertIn("context_source_changed", [item["rule"] for item in json.loads(drift.stdout)["failures"]])
            (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
            dirty = cli("check", repo, run, bundle, digest, response)
            self.assertIn("clean_worktree", [item["rule"] for item in json.loads(dirty.stdout)["failures"]])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, bundle, digest, response = prepare(temp, "plan")
            set_status(response, "awaiting_approval", "approved")
            self_approved = cli("check", repo, run, bundle, digest, response)
            self.assertIn("response_status", [item["rule"] for item in json.loads(self_approved.stdout)["failures"]])

    def test_no_change_and_approved_target_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, bundle, digest, response = prepare(temp, "plan")
            response.write_bytes((run / "plan.md").read_bytes())
            no_change = cli("check", repo, run, bundle, digest, response)
            self.assertEqual(2, no_change.returncode)
            self.assertIn("no_change", [item["rule"] for item in json.loads(no_change.stdout)["failures"]])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, bundle, digest, response = prepare(temp, "plan")
            set_status(run / "plan.md", "awaiting_approval", "approved")
            approved = cli("check", repo, run, bundle, digest, response)
            self.assertEqual(2, approved.returncode)
            self.assertIn("current_status", [item["rule"] for item in json.loads(approved.stdout)["failures"]])

    def test_refuses_run_inside_repo_and_symbolic_links(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, bundle, digest, response = prepare(temp, "research")
            (run.parent / "application-receipt.json").write_text("existing\n", encoding="utf-8")
            existing = cli("check", repo, run, bundle, digest, response)
            self.assertEqual(1, existing.returncode)
            self.assertIn("already exists", existing.stderr)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, bundle, digest, response = prepare(temp, "research")
            inside_run = repo / "run"
            shutil.copytree(run, inside_run)
            inside = cli("check", repo, inside_run, bundle, digest, response)
            self.assertEqual(1, inside.returncode)
            self.assertIn("outside", inside.stderr)

            response_link = temp / "response-link.md"
            try:
                response_link.symlink_to(response)
            except OSError:
                return
            linked = cli("check", repo, run, bundle, digest, response_link)
            self.assertEqual(1, linked.returncode)
            self.assertIn("symbolic links", linked.stderr)

    def test_cli_refuses_policy_overrides_and_invalid_reviewer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, bundle, digest, response = prepare(temp, "research")
            override = cli(
                "check",
                repo,
                run,
                bundle,
                digest,
                response,
                "--application-policy",
                "untrusted",
            )
            checked = json.loads(cli("check", repo, run, bundle, digest, response).stdout)
            invalid = cli(
                "apply",
                repo,
                run,
                bundle,
                digest,
                response,
                "--reviewer",
                " operator ",
                "--confirm",
                checked["required_confirmation"],
            )
            secret = "github_" + "pat_" + ("A" * 24)
            secret_reviewer = cli(
                "apply",
                repo,
                run,
                bundle,
                digest,
                response,
                "--reviewer",
                secret,
                "--confirm",
                checked["required_confirmation"],
            )
        self.assertEqual(2, override.returncode)
        self.assertIn("unrecognized arguments", override.stderr)
        self.assertEqual(1, invalid.returncode)
        self.assertIn("Reviewer declaration", invalid.stderr)
        self.assertEqual(1, secret_reviewer.returncode)
        self.assertIn("secret signature", secret_reviewer.stderr)
        self.assertNotIn(secret, secret_reviewer.stderr + secret_reviewer.stdout)


if __name__ == "__main__":
    unittest.main()
