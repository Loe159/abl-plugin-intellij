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
REPO_ROOT = CHECKS_DIR.parents[1]
MODULE_PATH = REPO_ROOT / ".agent" / "adapters" / "manual_read_only.py"
TEMPLATES = REPO_ROOT / ".agent" / "templates"
POLICY_DIR = REPO_ROOT / ".agent" / "policies"
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("manual_read_only", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
adapter = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = adapter
SPEC.loader.exec_module(adapter)
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


def fill_text(text: str, base: str) -> str:
    text = text.replace("{{issue}}", "123")
    text = text.replace("{{base_commit}}", base)
    text = text.replace("{{risk}}", "medium")
    return re.sub(r"\{\{[a-z0-9_]+\}\}", "Concrete recorded evidence.", text)


def create_run(destination: Path, base: str) -> None:
    shutil.copytree(TEMPLATES, destination)
    for path in destination.glob("*.md"):
        text = fill_text(path.read_text(encoding="utf-8"), base)
        if path.name == "task.md":
            text = text.replace("status: awaiting_approval", "status: approved")
        if path.name == "research.md":
            text = text.replace("status: pending", "status: complete")
        path.write_text(text, encoding="utf-8")


def create_response(path: Path, artifact: str, base: str, status: str) -> None:
    text = fill_text((TEMPLATES / artifact).read_text(encoding="utf-8"), base)
    old = "pending" if artifact == "research.md" else "awaiting_approval"
    path.write_text(text.replace(f"status: {old}", f"status: {status}"), encoding="utf-8")


def snapshot(path: Path) -> dict[str, bytes]:
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in path.rglob("*")
        if item.is_file()
    }


def run_adapter(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(MODULE_PATH), *args],
        check=False,
        capture_output=True,
        text=True,
    )


class ManualReadOnlyAdapterTest(unittest.TestCase):
    def test_repository_policy_is_explicitly_non_authorizing(self) -> None:
        artifact = adapter.validate_artifacts.load_contract(POLICY_DIR / "artifact-contract.json")
        prompt = adapter.validate_prompts.load_prompt_contract(
            POLICY_DIR / "prompt-contract.json",
            artifact,
        )
        context = adapter.build_stage_context.load_context_policy(
            POLICY_DIR / "stage-context.json",
            prompt,
            artifact,
        )
        output = adapter.validate_stage_output.load_output_policy(
            POLICY_DIR / "stage-output.json",
            context,
            prompt,
            artifact,
        )

        policy = adapter.load_adapter_policy(
            POLICY_DIR / "manual-read-only-adapter.json",
            context,
            output,
        )

        self.assertEqual(
            ["research", "plan", "compact-progress", "review"],
            policy["supported_stages"],
        )
        self.assertEqual(
            {
                "invokes_agent": False,
                "mutates_run": False,
                "applies_response": False,
                "authorizes": False,
            },
            policy["safety"],
        )

    def test_policy_rejects_unsafe_flags_and_stage_drift(self) -> None:
        artifact = adapter.validate_artifacts.load_contract(POLICY_DIR / "artifact-contract.json")
        prompt = adapter.validate_prompts.load_prompt_contract(
            POLICY_DIR / "prompt-contract.json",
            artifact,
        )
        context = adapter.build_stage_context.load_context_policy(
            POLICY_DIR / "stage-context.json",
            prompt,
            artifact,
        )
        output = adapter.validate_stage_output.load_output_policy(
            POLICY_DIR / "stage-output.json",
            context,
            prompt,
            artifact,
        )
        for expected, mutate in [
            ("safety flags", lambda policy: policy["safety"].update(authorizes=True)),
            ("stages", lambda policy: policy.update(supported_stages=["research"])),
        ]:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp_dir:
                policy = json.loads(
                    (POLICY_DIR / "manual-read-only-adapter.json").read_text(encoding="utf-8")
                )
                mutate(policy)
                path = Path(temp_dir) / "policy.json"
                path.write_text(json.dumps(policy), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, expected):
                    adapter.load_adapter_policy(path, context, output)

    def test_prepare_produces_bundle_without_mutating_repo_or_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = approval_helpers.prepare(temp)
            bundle = temp / "plan-bundle.json"
            before_run = snapshot(run)
            before_status = git(repo, "status", "--porcelain=v1", "--untracked-files=all")

            completed = run_adapter(
                "prepare",
                "--repo",
                str(repo),
                "--run",
                str(run),
                "--stage",
                "research",
                "--bundle",
                str(bundle),
                "--approval-receipt",
                str(receipt),
                "--approval-receipt-sha256",
                digest,
            )
            result = json.loads(completed.stdout)

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertTrue(result["result"]["produced"])
            self.assertEqual("prepare", result["action"])
            self.assertFalse(result["agent_invoked"])
            self.assertFalse(result["authorized"])
            self.assertEqual(before_run, snapshot(run))
            self.assertEqual(before_status, git(repo, "status", "--porcelain=v1", "--untracked-files=all"))
            self.assertEqual(result["result"]["sha256"], adapter.validate_stage_output.file_sha256(bundle))

    def test_prepare_refuses_dirty_repo_and_unsupported_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = approval_helpers.prepare(temp)
            (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
            bundle = temp / "plan-bundle.json"
            dirty = run_adapter(
                "prepare",
                "--repo",
                str(repo),
                "--run",
                str(run),
                "--stage",
                "research",
                "--bundle",
                str(bundle),
                "--approval-receipt",
                str(receipt),
                "--approval-receipt-sha256",
                digest,
            )
            unsupported = run_adapter(
                "prepare",
                "--repo",
                str(repo),
                "--run",
                str(run),
                "--stage",
                "implement",
                "--bundle",
                str(bundle),
            )

        self.assertEqual(2, dirty.returncode)
        self.assertFalse(json.loads(dirty.stdout)["result"]["produced"])
        self.assertFalse(bundle.exists())
        self.assertEqual(2, unsupported.returncode)
        self.assertIn("invalid choice", unsupported.stderr)

    def test_cli_does_not_accept_policy_or_prompt_overrides(self) -> None:
        for option in ("--adapter-policy", "--context-policy", "--prompts"):
            with self.subTest(option=option):
                completed = run_adapter(
                    "prepare",
                    "--repo",
                    ".",
                    "--run",
                    ".",
                    "--stage",
                    "research",
                    "--bundle",
                    "bundle.json",
                    option,
                    "untrusted",
                )

                self.assertEqual(2, completed.returncode)
                self.assertIn("unrecognized arguments", completed.stderr)

    def test_validate_accepts_response_without_applying_or_authorizing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, receipt_digest = application_helpers.apply_stage(
                temp,
                "research",
            )
            base = git(repo, "rev-parse", "HEAD")
            bundle = temp / "plan-bundle.json"
            prepared = run_adapter(
                "prepare",
                "--repo",
                str(repo),
                "--run",
                str(run),
                "--stage",
                "plan",
                "--bundle",
                str(bundle),
                "--application-receipt",
                str(receipt),
                "--application-receipt-sha256",
                receipt_digest,
            )
            digest = json.loads(prepared.stdout)["result"]["sha256"]
            response = temp / "response.md"
            create_response(response, "plan.md", base, "awaiting_approval")
            before_run = snapshot(run)

            completed = run_adapter(
                "validate",
                "--repo",
                str(repo),
                "--bundle",
                str(bundle),
                "--bundle-sha256",
                digest,
                "--response",
                str(response),
            )
            result = json.loads(completed.stdout)
            after_run = snapshot(run)

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(result["result"]["accepted"])
        self.assertFalse(result["authorized"])
        self.assertFalse(result["response_applied"])
        self.assertFalse(result["run_mutated"])
        self.assertEqual(before_run, after_run)

    def test_validate_rejects_self_approval_and_wrong_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, receipt_digest = application_helpers.apply_stage(
                temp,
                "research",
            )
            base = git(repo, "rev-parse", "HEAD")
            bundle = temp / "plan-bundle.json"
            prepared = run_adapter(
                "prepare",
                "--repo",
                str(repo),
                "--run",
                str(run),
                "--stage",
                "plan",
                "--bundle",
                str(bundle),
                "--application-receipt",
                str(receipt),
                "--application-receipt-sha256",
                receipt_digest,
            )
            digest = json.loads(prepared.stdout)["result"]["sha256"]
            response = temp / "response.md"
            create_response(response, "plan.md", base, "approved")
            self_approved = run_adapter(
                "validate",
                "--repo",
                str(repo),
                "--bundle",
                str(bundle),
                "--bundle-sha256",
                digest,
                "--response",
                str(response),
            )
            wrong_digest = run_adapter(
                "validate",
                "--repo",
                str(repo),
                "--bundle",
                str(bundle),
                "--bundle-sha256",
                "a" * 64,
                "--response",
                str(response),
            )

        self.assertEqual(2, self_approved.returncode)
        self.assertIn(
            "response_status",
            [failure["rule"] for failure in json.loads(self_approved.stdout)["result"]["failures"]],
        )
        self.assertEqual(2, wrong_digest.returncode)
        self.assertEqual(
            "bundle_sha256",
            json.loads(wrong_digest.stdout)["result"]["failures"][0]["rule"],
        )


if __name__ == "__main__":
    unittest.main()
