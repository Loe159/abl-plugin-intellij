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
MODULE_PATH = REPO_ROOT / ".agent" / "adapters" / "local_read_only.py"
TEMPLATES = REPO_ROOT / ".agent" / "templates"
PROMPTS = REPO_ROOT / ".agent" / "prompts"
POLICY_DIR = REPO_ROOT / ".agent" / "policies"
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location("local_read_only", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
adapter = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = adapter
SPEC.loader.exec_module(adapter)
import test_validate_task_approval as approval_helpers


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def fill_text(text: str, base: str, risk: str = "medium") -> str:
    text = text.replace("{{issue}}", "123")
    text = text.replace("{{base_commit}}", base)
    text = text.replace("{{risk}}", risk)
    return re.sub(r"\{\{[a-z0-9_]+\}\}", "Concrete recorded evidence.", text)


def create_response(path: Path, artifact: str, base: str, status: str) -> None:
    text = fill_text((TEMPLATES / artifact).read_text(encoding="utf-8"), base)
    if artifact == "research.md":
        text = text.replace("status: pending", f"status: {status}")
    elif artifact in {"progress.md", "review.md"}:
        text = text.replace("status: pending", f"status: {status}")
    else:
        text = text.replace("status: awaiting_approval", f"status: {status}")
    path.write_text(text, encoding="utf-8")


def set_status(path: Path, before: str, after: str) -> None:
    path.write_text(
        path.read_text(encoding="utf-8").replace(f"status: {before}", f"status: {after}"),
        encoding="utf-8",
    )


def build_research_bundle(temp: Path) -> tuple[Path, Path, str, Path]:
    repo, run, receipt, digest = approval_helpers.prepare(temp)
    bundle = temp / "bundle.json"
    policies = adapter.load_policies()
    result = adapter.build_stage_context.build_context(
        repo,
        run,
        "research",
        bundle,
        {
            "artifact": policies["artifact"],
            "prompt": policies["prompt"],
            "readiness": adapter.build_stage_context.check_stage_readiness.load_readiness_policy(
                POLICY_DIR / "stage-readiness.json",
                policies["artifact"],
            ),
            "context": policies["context"],
            "diff": policies["diff"],
        },
        PROMPTS,
        receipt,
        digest,
        None,
        None,
    )
    assert result["produced"], result
    return repo, bundle, result["sha256"], run


def build_review_bundle(temp: Path) -> tuple[Path, Path, str, Path]:
    repo = temp / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "tests@example.invalid")
    git(repo, "config", "user.name", "Tests")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")
    run = temp / "run"
    shutil.copytree(TEMPLATES, run)
    for path in run.glob("*.md"):
        path.write_text(fill_text(path.read_text(encoding="utf-8"), base), encoding="utf-8")
    set_status(run / "task.md", "awaiting_approval", "approved")
    set_status(run / "research.md", "pending", "complete")
    set_status(run / "plan.md", "awaiting_approval", "approved")
    set_status(run / "verification.md", "pending", "failed")
    bundle = temp / "review-bundle.json"
    policies = adapter.load_policies()
    result = adapter.build_stage_context.build_context(
        repo,
        run,
        "review",
        bundle,
        {
            "artifact": policies["artifact"],
            "prompt": policies["prompt"],
            "readiness": adapter.build_stage_context.check_stage_readiness.load_readiness_policy(
                POLICY_DIR / "stage-readiness.json",
                policies["artifact"],
            ),
            "context": policies["context"],
            "diff": policies["diff"],
        },
        PROMPTS,
        None,
        None,
        None,
        None,
    )
    assert result["produced"], result
    return repo, bundle, result["sha256"], run


def run_adapter(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(MODULE_PATH), *args],
        check=False,
        capture_output=True,
        text=True,
    )


class LocalReadOnlyAdapterTest(unittest.TestCase):
    def test_policy_is_non_authorizing_command_wrapper(self) -> None:
        policy = adapter.load_adapter_policy()

        self.assertEqual("local-read-only-command", policy["adapter"])
        self.assertFalse(policy["safety"]["mutates_run"])
        self.assertFalse(policy["safety"]["applies_response"])
        self.assertFalse(policy["safety"]["authorizes"])
        self.assertFalse(policy["safety"]["network_authorized"])

    def test_valid_command_stdout_is_captured_and_validated_without_run_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, bundle, digest, run = build_research_bundle(temp)
            base = git(repo, "rev-parse", "HEAD")
            seed = temp / "seed-response.md"
            response = temp / "captured-response.md"
            create_response(seed, "research.md", base, "complete")
            before_run = {
                path.relative_to(run).as_posix(): path.read_bytes()
                for path in run.rglob("*")
                if path.is_file()
            }

            completed = run_adapter(
                "--repo",
                str(repo),
                "--bundle",
                str(bundle),
                "--bundle-sha256",
                digest,
                "--response",
                str(response),
                "--",
                sys.executable,
                "-c",
                "from pathlib import Path; import sys; print(Path(sys.argv[1]).read_text(encoding='utf-8'), end='')",
                str(seed),
            )
            result = json.loads(completed.stdout)
            after_run = {
                path.relative_to(run).as_posix(): path.read_bytes()
                for path in run.rglob("*")
                if path.is_file()
            }

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(result["result"]["accepted"], result)
        self.assertTrue(result["command_invoked"])
        self.assertFalse(result["authorized"])
        self.assertFalse(result["run_mutated"])
        self.assertFalse(result["response_applied"])
        self.assertEqual(before_run, after_run)

    def test_review_stage_stdout_is_captured_and_validated_without_run_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, bundle, digest, run = build_review_bundle(temp)
            base = git(repo, "rev-parse", "HEAD")
            seed = temp / "seed-review.md"
            response = temp / "captured-review.md"
            create_response(seed, "review.md", base, "complete")
            before_run = {
                path.relative_to(run).as_posix(): path.read_bytes()
                for path in run.rglob("*")
                if path.is_file()
            }

            completed = run_adapter(
                "--repo",
                str(repo),
                "--bundle",
                str(bundle),
                "--bundle-sha256",
                digest,
                "--response",
                str(response),
                "--",
                sys.executable,
                "-c",
                "from pathlib import Path; import sys; print(Path(sys.argv[1]).read_text(encoding='utf-8'), end='')",
                str(seed),
            )
            result = json.loads(completed.stdout)
            after_run = {
                path.relative_to(run).as_posix(): path.read_bytes()
                for path in run.rglob("*")
                if path.is_file()
            }

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(result["result"]["accepted"], result)
        self.assertEqual("review.md", result["result"]["validation"]["artifact"])
        self.assertFalse(result["authorized"])
        self.assertFalse(result["run_mutated"])
        self.assertFalse(result["response_applied"])
        self.assertEqual(before_run, after_run)

    def test_command_that_mutates_repo_is_rejected_and_response_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, bundle, digest, _run = build_research_bundle(temp)
            base = git(repo, "rev-parse", "HEAD")
            seed = temp / "seed-response.md"
            response = temp / "captured-response.md"
            create_response(seed, "research.md", base, "complete")

            completed = run_adapter(
                "--repo",
                str(repo),
                "--bundle",
                str(bundle),
                "--bundle-sha256",
                digest,
                "--response",
                str(response),
                "--",
                sys.executable,
                "-c",
                (
                    "from pathlib import Path; import sys; "
                    "Path('mutation.txt').write_text('changed', encoding='utf-8'); "
                    "print(Path(sys.argv[1]).read_text(encoding='utf-8'), end='')"
                ),
                str(seed),
            )
            result = json.loads(completed.stdout)

        self.assertEqual(2, completed.returncode)
        self.assertFalse(result["result"]["accepted"])
        self.assertEqual("clean_worktree_after", result["result"]["failures"][0]["rule"])
        self.assertFalse(response.exists())

    def test_failed_command_that_mutates_repo_reports_read_only_violation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, bundle, digest, _run = build_research_bundle(temp)
            response = temp / "captured-response.md"

            completed = run_adapter(
                "--repo",
                str(repo),
                "--bundle",
                str(bundle),
                "--bundle-sha256",
                digest,
                "--response",
                str(response),
                "--",
                sys.executable,
                "-c",
                (
                    "from pathlib import Path; "
                    "Path('failed-mutation.txt').write_text('changed', encoding='utf-8'); "
                    "raise SystemExit(3)"
                ),
            )
            result = json.loads(completed.stdout)
            failures = [item["rule"] for item in result["result"]["failures"]]

        self.assertEqual(2, completed.returncode)
        self.assertFalse(result["result"]["accepted"])
        self.assertIn("clean_worktree_after", failures)
        self.assertIn("command_failed", failures)
        self.assertFalse(response.exists())


if __name__ == "__main__":
    unittest.main()
