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
MODULE_PATH = CHECKS_DIR / "build_stage_context.py"
REPO_ROOT = CHECKS_DIR.parents[1]
TEMPLATES = REPO_ROOT / ".agent" / "templates"
PROMPTS = REPO_ROOT / ".agent" / "prompts"
POLICIES = REPO_ROOT / ".agent" / "policies"
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("build_stage_context", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)
import test_validate_task_approval as approval_helpers
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
    replacements = {
        "{{issue}}": "123",
        "{{base_commit}}": base,
        "{{risk}}": risk,
    }
    for path in destination.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        for old, new in replacements.items():
            text = text.replace(old, new)
        text = re.sub(r"\{\{[a-z0-9_]+\}\}", "Concrete recorded evidence.", text)
        if path.name == "task.md":
            text = text.replace("status: awaiting_approval", "status: approved")
        if path.name == "research.md":
            text = text.replace("status: pending", "status: complete")
        path.write_text(text, encoding="utf-8")


def set_status(run: Path, artifact: str, old: str, new: str) -> None:
    path = run / artifact
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace(f"status: {old}", f"status: {new}", 1), encoding="utf-8")


class StageContextBuilderTest(unittest.TestCase):
    def setUp(self) -> None:
        artifact = builder.validate_artifacts.load_contract(POLICIES / "artifact-contract.json")
        prompt = builder.validate_prompts.load_prompt_contract(
            POLICIES / "prompt-contract.json",
            artifact,
        )
        self.policies = {
            "artifact": artifact,
            "prompt": prompt,
            "readiness": builder.check_stage_readiness.load_readiness_policy(
                POLICIES / "stage-readiness.json",
                artifact,
            ),
            "context": builder.load_context_policy(
                POLICIES / "stage-context.json",
                prompt,
                artifact,
            ),
            "diff": builder.diff_policy.load_policy(POLICIES / "diff-policy.json"),
        }

    def build(
        self,
        repo: Path,
        run: Path,
        stage: str,
        output: Path,
        receipt: Path | None = None,
        digest: str | None = None,
        application_receipt: Path | None = None,
        application_digest: str | None = None,
    ) -> dict[str, object]:
        return builder.build_context(
            repo,
            run,
            stage,
            output,
            self.policies,
            PROMPTS,
            receipt,
            digest,
            application_receipt,
            application_digest,
        )

    def test_repository_context_policy_is_valid(self) -> None:
        self.assertEqual(["plan", "research"], sorted(self.policies["context"]["stages"]))
        self.assertEqual(
            "validated_stage_application",
            self.policies["context"]["stages"]["plan"]["provenance"],
        )

    def test_research_bundle_is_reproducible_and_minimal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = approval_helpers.prepare(temp)
            first = temp / "first.json"
            second = temp / "second.json"

            first_result = self.build(repo, run, "research", first, receipt, digest)
            second_result = self.build(repo, run, "research", second, receipt, digest)
            bundle = json.loads(first.read_text(encoding="utf-8"))
            first_bytes = first.read_bytes()
            second_bytes = second.read_bytes()

        self.assertTrue(first_result["produced"])
        self.assertEqual(first_bytes, second_bytes)
        self.assertEqual(first_result["sha256"], second_result["sha256"])
        self.assertFalse(bundle["authorized"])
        self.assertEqual("read-only", bundle["mode"])
        self.assertEqual(["task.md"], [record["name"] for record in bundle["artifacts"]])
        self.assertEqual("research.md", bundle["prompt"]["name"])
        self.assertEqual(
            {
                "kind": "validated_task_approval",
                "task_approval_receipt_sha256": digest,
            },
            bundle["provenance"],
        )

    def test_plan_bundle_includes_only_task_and_research(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = application_helpers.apply_stage(temp, "research")
            output = temp / "plan.json"

            result = self.build(repo, run, "plan", output, None, None, receipt, digest)
            bundle = json.loads(output.read_text(encoding="utf-8"))

        self.assertTrue(result["produced"])
        self.assertEqual(
            ["task.md", "research.md"],
            [record["name"] for record in bundle["artifacts"]],
        )
        self.assertEqual("plan.md", bundle["prompt"]["name"])
        self.assertEqual(
            {
                "kind": "validated_stage_application",
                "stage_application_receipt_sha256": digest,
            },
            bundle["provenance"],
        )

    def test_plan_requires_valid_research_application_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = application_helpers.apply_stage(temp, "research")
            missing = self.build(repo, run, "plan", temp / "missing-plan.json")
            invalid = self.build(
                repo,
                run,
                "plan",
                temp / "invalid-plan.json",
                None,
                None,
                receipt,
                "0" * 64,
            )

        self.assertFalse(missing["produced"])
        self.assertEqual("stage_application_provenance", missing["failures"][0]["rule"])
        self.assertFalse(invalid["produced"])
        self.assertEqual("stage_application_provenance", invalid["failures"][0]["rule"])

    def test_research_requires_valid_task_approval_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = approval_helpers.prepare(temp)
            missing = self.build(repo, run, "research", temp / "missing.json")
            invalid = self.build(
                repo,
                run,
                "research",
                temp / "invalid.json",
                receipt,
                "0" * 64,
            )

        self.assertFalse(missing["produced"])
        self.assertEqual("task_approval_provenance", missing["failures"][0]["rule"])
        self.assertFalse(invalid["produced"])
        self.assertEqual("task_approval_provenance", invalid["failures"][0]["rule"])

    def test_research_provenance_drift_before_write_does_not_produce(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = approval_helpers.prepare(temp)
            output = temp / "drifted.json"
            original = builder.check_research_provenance
            calls = 0

            def drifting_provenance(*args: object) -> dict[str, object]:
                nonlocal calls
                result = original(*args)
                calls += 1
                if calls == 2:
                    result["ready"] = False
                    result["failures"] = [{"rule": "fixture_drift", "message": "Changed."}]
                return result

            with mock.patch.object(
                builder,
                "check_research_provenance",
                side_effect=drifting_provenance,
            ):
                result = self.build(repo, run, "research", output, receipt, digest)

        self.assertFalse(result["produced"])
        self.assertFalse(output.exists())
        self.assertEqual("provenance_state_changed", result["failures"][0]["rule"])

    def test_not_ready_and_head_mismatch_do_not_write_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            base = create_repo(repo)
            run = temp / "run"
            create_run(run, base)
            set_status(run, "research.md", "complete", "pending")
            not_ready_output = temp / "not-ready.json"
            not_ready = self.build(
                repo,
                run,
                "plan",
                not_ready_output,
                None,
                None,
                temp / "missing.json",
                "0" * 64,
            )
            mismatch_temp = temp / "mismatch"
            mismatch_temp.mkdir()
            repo2, run2, receipt, digest = application_helpers.apply_stage(mismatch_temp, "research")
            (repo2 / "README.md").write_text("next\n", encoding="utf-8")
            git(repo2, "add", "README.md")
            git(repo2, "commit", "-m", "next")
            mismatch_output = temp / "mismatch.json"
            mismatch = self.build(repo2, run2, "plan", mismatch_output, None, None, receipt, digest)

        self.assertFalse(not_ready["produced"])
        self.assertFalse(not_ready_output.exists())
        self.assertEqual("stage_application_provenance", not_ready["failures"][0]["rule"])
        self.assertFalse(mismatch["produced"])
        self.assertFalse(mismatch_output.exists())
        self.assertEqual("stage_application_provenance", mismatch["failures"][0]["rule"])
        self.assertIn("repo_head_match", json.dumps(mismatch))

    def test_dirty_worktree_does_not_write_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = approval_helpers.prepare(temp)
            (repo / "untracked.txt").write_text("dirty\n", encoding="utf-8")
            output = temp / "dirty.json"

            result = self.build(repo, run, "research", output, receipt, digest)

        self.assertFalse(result["produced"])
        self.assertFalse(output.exists())
        self.assertEqual("task_approval_provenance", result["failures"][0]["rule"])
        self.assertIn("clean_worktree", json.dumps(result))

    def test_secret_and_size_limit_do_not_write_or_echo_secret(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = approval_helpers.prepare(temp)
            secret = "github_" + "pat_" + ("A" * 24)
            task = run / "task.md"
            original_task = task.read_bytes()
            task.write_text(task.read_text(encoding="utf-8") + f"\n{secret}\n", encoding="utf-8")
            secret_output = temp / "secret.json"
            secret_result = self.build(repo, run, "research", secret_output, receipt, digest)
            task.write_bytes(original_task)
            self.policies["context"]["max_bundle_bytes"] = 1
            size_output = temp / "large.json"
            size_result = self.build(repo, run, "research", size_output, receipt, digest)

        self.assertFalse(secret_result["produced"])
        self.assertFalse(secret_output.exists())
        self.assertNotIn(secret, json.dumps(secret_result))
        self.assertIn("high_confidence_secret", json.dumps(secret_result))
        self.assertFalse(size_result["produced"])
        self.assertFalse(size_output.exists())
        self.assertEqual("max_bundle_bytes", size_result["failures"][0]["rule"])

    def test_refuses_run_or_output_in_repo_and_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            base = create_repo(repo)
            external_run = temp / "run"
            create_run(external_run, base)
            inside_run = repo / "run"
            create_run(inside_run, base)
            existing = temp / "existing.json"
            existing.write_text("keep", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Run artifact directory"):
                self.build(repo, inside_run, "research", temp / "inside-run.json")
            with self.assertRaisesRegex(ValueError, "output must be outside"):
                self.build(repo, external_run, "research", repo / "bundle.json")
            with self.assertRaisesRegex(ValueError, "already exists"):
                self.build(repo, external_run, "research", existing)
            existing_content = existing.read_text(encoding="utf-8")

        self.assertEqual("keep", existing_content)

    def test_policy_rejects_stage_mismatch_and_missing_task(self) -> None:
        artifact = self.policies["artifact"]
        prompt = self.policies["prompt"]
        for expected, mutate in [
            (
                "exactly match",
                lambda policy: policy["stages"].pop("plan"),
            ),
            (
                "prompt does not match",
                lambda policy: policy["stages"]["research"].update(prompt="plan.md"),
            ),
            (
                "include task.md",
                lambda policy: policy["stages"]["plan"].update(artifacts=["research.md"]),
            ),
            (
                "provenance must be",
                lambda policy: policy["stages"]["research"].update(provenance="none"),
            ),
            (
                "provenance must be",
                lambda policy: policy["stages"]["plan"].update(provenance="none"),
            ),
        ]:
            with self.subTest(expected=expected):
                policy = json.loads((POLICIES / "stage-context.json").read_text(encoding="utf-8"))
                mutate(policy)
                with tempfile.TemporaryDirectory() as temp_dir:
                    path = Path(temp_dir) / "policy.json"
                    path.write_text(json.dumps(policy), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, expected):
                        builder.load_context_policy(path, prompt, artifact)

    def test_cli_produces_bundle_for_ready_external_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = approval_helpers.prepare(temp)
            output = temp / "bundle.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--repo",
                    str(repo),
                    "--run",
                    str(run),
                    "--stage",
                    "research",
                    "--output",
                    str(output),
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

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["produced"])


if __name__ == "__main__":
    unittest.main()
