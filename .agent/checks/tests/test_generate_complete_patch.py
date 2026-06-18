from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "generate_complete_patch.py"
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("generate_complete_patch", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
generator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = generator
SPEC.loader.exec_module(generator)


POLICY = {
    "version": 1,
    "max_files": 20,
    "max_changed_lines": 100,
    "allow_binary_files": True,
    "allow_symlinks": False,
    "test_path_patterns": ["src/test/**"],
    "forbidden_added_test_patterns": [
        r"^\s*@(org\.junit\.)?Ignore\b",
        r"^\s*@(org\.junit\.jupiter\.api\.)?Disabled\b",
        r"^\s*@kotlin\.test\.Ignore\b",
    ],
    "forbidden_removed_test_patterns": [
        r"^\s*@(org\.junit\.)?Test\b",
        r"^\s*@(org\.junit\.jupiter\.api\.)?Test\b",
        r"^\s*@kotlin\.test\.Test\b",
    ],
    "secret_patterns": [
        {
            "id": "github_token",
            "pattern": r"(?:github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{36,})",
        }
    ],
    "protected_patterns": [],
}


def run_git(repo: Path, *arguments: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
    ).stdout


def initialize_repo(repo: Path) -> str:
    repo.mkdir()
    run_git(repo, "init")
    run_git(repo, "config", "user.email", "tests@example.invalid")
    run_git(repo, "config", "user.name", "Patch Generator Tests")
    (repo / "modify.txt").write_text("old\n", encoding="utf-8")
    (repo / "delete.txt").write_text("delete\n", encoding="utf-8")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-m", "initial")
    return run_git(repo, "rev-parse", "HEAD").decode("ascii").strip()


def git_state(repo: Path) -> tuple[bytes, bytes, set[str]]:
    status = run_git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    index_path = Path(run_git(repo, "rev-parse", "--git-path", "index").decode("utf-8").strip())
    if not index_path.is_absolute():
        index_path = repo / index_path
    index = index_path.read_bytes()
    objects_path = repo / ".git" / "objects"
    objects = {
        str(path.relative_to(objects_path))
        for path in objects_path.rglob("*")
        if path.is_file()
    }
    return status, index, objects


class CompletePatchGeneratorTest(unittest.TestCase):
    def test_generates_complete_valid_patch_without_mutating_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            base = initialize_repo(repo)
            (repo / "modify.txt").write_text("new\n", encoding="utf-8")
            (repo / "delete.txt").unlink()
            (repo / "new.txt").write_text("new file\n", encoding="utf-8")
            (repo / "binary.bin").write_bytes(b"\x00\xff\x10binary\x00")
            (repo / "staged.txt").write_text("staged file\n", encoding="utf-8")
            run_git(repo, "add", "staged.txt")
            output = temp / "artifacts" / "patch.diff"
            policy = temp / "policy.json"
            policy.write_text(json.dumps(POLICY), encoding="utf-8")
            before = git_state(repo)

            result = generator.generate_and_validate(repo, base, output, policy, False)

            after = git_state(repo)
            patch_text = output.read_text(encoding="utf-8")
            patch_digest = hashlib.sha256(output.read_bytes()).hexdigest()

        self.assertTrue(result["allowed"])
        self.assertEqual(before, after)
        self.assertEqual(
            ["binary.bin", "delete.txt", "modify.txt", "new.txt", "staged.txt"],
            result["facts"]["paths"],
        )
        self.assertIn("GIT binary patch", patch_text)
        self.assertIn("new file mode 100644", patch_text)
        self.assertIn("deleted file mode 100644", patch_text)
        self.assertEqual(
            patch_digest,
            result["artifact"]["sha256"],
        )
        self.assertEqual(["binary.bin"], result["facts"]["binary_paths"])

    def test_default_style_policy_blocks_generated_binary_patch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            base = initialize_repo(repo)
            (repo / "binary.bin").write_bytes(b"\x00\xff\x10binary\x00")
            output = temp / "patch.diff"
            policy = temp / "policy.json"
            policy.write_text(
                json.dumps({**POLICY, "allow_binary_files": False}),
                encoding="utf-8",
            )

            result = generator.generate_and_validate(repo, base, output, policy, False)

        self.assertFalse(result["allowed"])
        violation = next(
            item
            for item in result["violations"]
            if item["rule"] == "binary_files_require_approval"
        )
        self.assertEqual(["binary.bin"], violation["paths"])

    def test_generated_patch_blocks_added_test_disable_annotation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            base = initialize_repo(repo)
            test_source = repo / "src" / "test" / "kotlin" / "ExampleTest.kt"
            test_source.parent.mkdir(parents=True)
            test_source.write_text(
                "import org.junit.Ignore\n\n@Ignore(\"temporarily broken\")\nclass ExampleTest\n",
                encoding="utf-8",
            )
            output = temp / "patch.diff"
            policy = temp / "policy.json"
            policy.write_text(json.dumps(POLICY), encoding="utf-8")

            result = generator.generate_and_validate(repo, base, output, policy, False)

        self.assertFalse(result["allowed"])
        violation = next(
            item
            for item in result["violations"]
            if item["rule"] == "test_disable_requires_approval"
        )
        self.assertEqual(["src/test/kotlin/ExampleTest.kt"], violation["paths"])

    def test_generated_patch_blocks_deleted_test_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            initialize_repo(repo)
            test_source = repo / "src" / "test" / "kotlin" / "ExampleTest.kt"
            test_source.parent.mkdir(parents=True)
            test_source.write_text("class ExampleTest\n", encoding="utf-8")
            run_git(repo, "add", ".")
            run_git(repo, "commit", "-m", "add test")
            base = run_git(repo, "rev-parse", "HEAD").decode("ascii").strip()
            test_source.unlink()
            output = temp / "patch.diff"
            policy = temp / "policy.json"
            policy.write_text(json.dumps(POLICY), encoding="utf-8")

            result = generator.generate_and_validate(repo, base, output, policy, False)

        self.assertFalse(result["allowed"])
        violation = next(
            item
            for item in result["violations"]
            if item["rule"] == "test_file_removal_requires_approval"
        )
        self.assertEqual(["src/test/kotlin/ExampleTest.kt"], violation["paths"])

    def test_generated_patch_blocks_secret_without_echoing_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            base = initialize_repo(repo)
            secret = "github_" + "pat_" + ("A" * 24)
            (repo / "credentials.txt").write_text(f"token={secret}\n", encoding="utf-8")
            output = temp / "patch.diff"
            policy = temp / "policy.json"
            policy.write_text(json.dumps(POLICY), encoding="utf-8")

            result = generator.generate_and_validate(repo, base, output, policy, False)
            rendered = json.dumps(result) + generator.diff_policy.format_text(result)
            output_exists = output.exists()

        self.assertFalse(result["allowed"])
        self.assertFalse(output_exists)
        self.assertFalse(result["artifact"]["retained"])
        self.assertNotIn(secret, rendered)
        violation = next(
            item
            for item in result["violations"]
            if item["rule"] == "high_confidence_secret"
        )
        self.assertEqual("github_token", violation["detections"][0]["signature"])
        rules = [item["rule"] for item in result["violations"]]
        self.assertNotIn("patch_matches_worktree_content", rules)
        self.assertNotIn("patch_applies_to_base", rules)

    def test_cli_does_not_retain_or_echo_secret_patch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            base = initialize_repo(repo)
            secret = "github_" + "pat_" + ("A" * 24)
            (repo / "credentials.txt").write_text(f"token={secret}\n", encoding="utf-8")
            output = temp / "patch.diff"
            policy = temp / "policy.json"
            policy.write_text(json.dumps(POLICY), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--repo",
                    str(repo),
                    "--base",
                    base,
                    "--output",
                    str(output),
                    "--policy",
                    str(policy),
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            output_exists = output.exists()

        self.assertEqual(2, completed.returncode, completed.stderr)
        self.assertFalse(output_exists)
        self.assertNotIn(secret, completed.stdout + completed.stderr)
        self.assertFalse(json.loads(completed.stdout)["artifact"]["retained"])

    def test_refuses_output_inside_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            base = initialize_repo(repo)
            policy = Path(temp_dir) / "policy.json"
            policy.write_text(json.dumps(POLICY), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "outside"):
                generator.generate_and_validate(
                    repo,
                    base,
                    repo / "patch.diff",
                    policy,
                    False,
                )

    def test_refuses_existing_output_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            base = initialize_repo(repo)
            output = temp / "patch.diff"
            output.write_text("existing", encoding="utf-8")
            policy = temp / "policy.json"
            policy.write_text(json.dumps(POLICY), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "--force"):
                generator.generate_and_validate(repo, base, output, policy, False)

    def test_refuses_active_git_clean_filter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            base = initialize_repo(repo)
            run_git(repo, "config", "filter.danger.tool.clean", "danger-command")
            (repo / ".gitattributes").write_text("*.txt filter=danger.tool\n", encoding="utf-8")
            (repo / "modify.txt").write_text("changed\n", encoding="utf-8")
            policy = temp / "policy.json"
            policy.write_text(json.dumps(POLICY), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "content filters"):
                generator.generate_and_validate(
                    repo,
                    base,
                    temp / "patch.diff",
                    policy,
                    False,
                )

    def test_cli_returns_blocked_but_keeps_verified_patch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            base = initialize_repo(repo)
            (repo / "modify.txt").write_text("new\n", encoding="utf-8")
            output = temp / "patch.diff"
            policy = temp / "policy.json"
            policy.write_text(
                json.dumps({**POLICY, "protected_patterns": ["modify.txt"]}),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--repo",
                    str(repo),
                    "--base",
                    base,
                    "--output",
                    str(output),
                    "--policy",
                    str(policy),
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            output_exists = output.exists()

        self.assertEqual(2, completed.returncode, completed.stderr)
        self.assertTrue(output_exists)
        result = json.loads(completed.stdout)
        self.assertFalse(result["allowed"])
        self.assertTrue(result["artifact"]["retained"])
        self.assertEqual("protected_paths", result["violations"][0]["rule"])


if __name__ == "__main__":
    unittest.main()
