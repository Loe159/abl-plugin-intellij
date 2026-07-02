from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "diff_policy.py"
REPO_ROOT = MODULE_PATH.parents[2]
REPOSITORY_POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "diff-policy.json"
SPEC = importlib.util.spec_from_file_location("diff_policy", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
diff_policy = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = diff_policy
SPEC.loader.exec_module(diff_policy)


POLICY = {
    "version": 1,
    "max_files": 2,
    "max_changed_lines": 4,
    "allow_binary_files": False,
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
            "id": "private_key_header",
            "pattern": r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----",
        },
        {
            "id": "github_token",
            "pattern": r"(?:github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{36,})",
        },
        {
            "id": "aws_access_key_id",
            "pattern": r"(?:AKIA|ASIA)[A-Z0-9]{16}",
        },
        {
            "id": "google_api_key",
            "pattern": r"AIza[0-9A-Za-z_-]{35}",
        },
    ],
    "protected_patterns": [".github/**", ".agent/**", "build.gradle.kts"],
}


def patch_for(path: str, removed: str = "old", added: str = "new") -> str:
    return "\n".join(
        [
            f"diff --git a/{path} b/{path}",
            "index 1111111..2222222 100644",
            f"--- a/{path}",
            f"+++ b/{path}",
            "@@ -1 +1 @@",
            f"-{removed}",
            f"+{added}",
            "",
        ]
    )


def new_file_patch(path: str, content: str) -> str:
    return "\n".join(
        [
            f"diff --git a/{path} b/{path}",
            "new file mode 100644",
            "--- /dev/null",
            f"+++ b/{path}",
            "@@ -0,0 +1 @@",
            f"+{content}",
            "",
        ]
    )


def run_git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def initialize_git_repo(repo: Path) -> str:
    repo.mkdir()
    run_git(repo, "init")
    run_git(repo, "config", "user.email", "tests@example.invalid")
    run_git(repo, "config", "user.name", "Diff Policy Tests")
    (repo / "tracked.txt").write_text("old\n", encoding="utf-8")
    run_git(repo, "add", "tracked.txt")
    run_git(repo, "commit", "-m", "initial")
    return run_git(repo, "rev-parse", "HEAD")


def write_git_diff(repo: Path, base: str, output: Path) -> None:
    completed = subprocess.run(
        ["git", "-C", str(repo), "diff", "--binary", base, "--"],
        check=True,
        capture_output=True,
    )
    output.write_bytes(completed.stdout)


class DiffPolicyTest(unittest.TestCase):
    def test_allows_small_source_patch(self) -> None:
        result = diff_policy.evaluate_patch(
            patch_for("src/main/kotlin/com/example/Example.kt"),
            POLICY,
        )

        self.assertTrue(result["allowed"])
        self.assertEqual(1, result["facts"]["file_count"])
        self.assertEqual(2, result["facts"]["changed_lines"])

    def test_allows_empty_patch(self) -> None:
        result = diff_policy.evaluate_patch("", POLICY)

        self.assertTrue(result["allowed"])
        self.assertEqual(0, result["facts"]["file_count"])

    def test_blocks_protected_path(self) -> None:
        result = diff_policy.evaluate_patch(patch_for(".github/workflows/build.yml"), POLICY)

        self.assertFalse(result["allowed"])
        self.assertEqual("protected_paths", result["violations"][0]["rule"])

    def test_blocks_exact_protected_file(self) -> None:
        result = diff_policy.evaluate_patch(patch_for("build.gradle.kts"), POLICY)

        self.assertFalse(result["allowed"])
        self.assertEqual(["build.gradle.kts"], result["violations"][0]["paths"])

    def test_blocks_protected_path_case_insensitively(self) -> None:
        result = diff_policy.evaluate_patch(patch_for(".GITHUB/workflows/build.yml"), POLICY)

        self.assertFalse(result["allowed"])
        self.assertEqual("protected_paths", result["violations"][0]["rule"])

    def test_blocks_protected_target_hidden_by_diff_header(self) -> None:
        patch = "\n".join(
            [
                "diff --git a/src/Allowed.kt b/src/Allowed.kt",
                "--- a/src/Allowed.kt",
                "+++ b/.github/workflows/build.yml",
                "@@ -1 +1 @@",
                "-old",
                "+new",
                "",
            ]
        )

        result = diff_policy.evaluate_patch(patch, POLICY)

        self.assertFalse(result["allowed"])
        self.assertIn(".github/workflows/build.yml", result["violations"][0]["paths"])

    def test_checks_deleted_file_old_path(self) -> None:
        patch = "\n".join(
            [
                "diff --git a/.agent/config.json b/.agent/config.json",
                "deleted file mode 100644",
                "--- a/.agent/config.json",
                "+++ /dev/null",
                "@@ -1 +0,0 @@",
                "-{}",
                "",
            ]
        )

        result = diff_policy.evaluate_patch(patch, POLICY)

        self.assertFalse(result["allowed"])
        self.assertIn(".agent/config.json", result["violations"][0]["paths"])

    def test_blocks_path_traversal(self) -> None:
        result = diff_policy.evaluate_patch(patch_for("../outside.txt"), POLICY)

        self.assertFalse(result["allowed"])
        self.assertEqual("no_path_traversal", result["violations"][0]["rule"])

    def test_blocks_too_many_files(self) -> None:
        patch = patch_for("src/One.kt") + patch_for("src/Two.kt") + patch_for("src/Three.kt")

        result = diff_policy.evaluate_patch(patch, POLICY)

        rules = [violation["rule"] for violation in result["violations"]]
        self.assertIn("max_files", rules)

    def test_blocks_too_many_changed_lines(self) -> None:
        patch = "\n".join(
            [
                "diff --git a/src/One.kt b/src/One.kt",
                "--- a/src/One.kt",
                "+++ b/src/One.kt",
                "@@ -1,2 +1,3 @@",
                "-one",
                "-two",
                "+three",
                "+four",
                "+five",
                "",
            ]
        )

        result = diff_policy.evaluate_patch(patch, POLICY)

        rules = [violation["rule"] for violation in result["violations"]]
        self.assertIn("max_changed_lines", rules)

    def test_blocks_binary_file_and_reports_path(self) -> None:
        patch = "\n".join(
            [
                "diff --git a/assets/image.png b/assets/image.png",
                "new file mode 100644",
                "index 0000000..1111111",
                "GIT binary patch",
                "literal 1",
                "IcmZPo000310RR91",
                "",
            ]
        )

        result = diff_policy.evaluate_patch(patch, POLICY)

        self.assertFalse(result["allowed"])
        violation = next(
            item
            for item in result["violations"]
            if item["rule"] == "binary_files_require_approval"
        )
        self.assertEqual(["assets/image.png"], violation["paths"])
        self.assertEqual(["assets/image.png"], result["facts"]["binary_paths"])

    def test_detects_binary_files_differ_marker(self) -> None:
        patch = "\n".join(
            [
                "diff --git a/archive.bin b/archive.bin",
                "index 1111111..2222222 100644",
                "Binary files a/archive.bin and b/archive.bin differ",
                "",
            ]
        )

        result = diff_policy.evaluate_patch(patch, POLICY)

        self.assertEqual(["archive.bin"], result["facts"]["binary_paths"])
        rules = [violation["rule"] for violation in result["violations"]]
        self.assertIn("binary_files_require_approval", rules)

    def test_blocks_symlink_and_reports_path(self) -> None:
        patch = "\n".join(
            [
                "diff --git a/current-link b/current-link",
                "new file mode 120000",
                "index 0000000..1111111",
                "--- /dev/null",
                "+++ b/current-link",
                "@@ -0,0 +1 @@",
                "+target.txt",
                "",
            ]
        )

        result = diff_policy.evaluate_patch(patch, POLICY)

        self.assertFalse(result["allowed"])
        violation = next(
            item
            for item in result["violations"]
            if item["rule"] == "symlinks_require_approval"
        )
        self.assertEqual(["current-link"], violation["paths"])
        self.assertEqual(["current-link"], result["facts"]["symlink_paths"])

    def test_blocks_modified_existing_symlink(self) -> None:
        patch = "\n".join(
            [
                "diff --git a/current-link b/current-link",
                "index 1111111..2222222 120000",
                "--- a/current-link",
                "+++ b/current-link",
                "@@ -1 +1 @@",
                "-old-target.txt",
                "+new-target.txt",
                "",
            ]
        )

        result = diff_policy.evaluate_patch(patch, POLICY)

        rules = [violation["rule"] for violation in result["violations"]]
        self.assertIn("symlinks_require_approval", rules)
        self.assertEqual(["current-link"], result["facts"]["symlink_paths"])

    def test_detects_all_symlink_mode_metadata(self) -> None:
        for mode_line in (
            "new file mode 120000",
            "deleted file mode 120000",
            "old mode 120000",
            "new mode 120000",
        ):
            with self.subTest(mode_line=mode_line):
                patch = "\n".join(
                    [
                        "diff --git a/current-link b/current-link",
                        mode_line,
                        "",
                    ]
                )

                result = diff_policy.evaluate_patch(patch, POLICY)

                self.assertEqual(["current-link"], result["facts"]["symlink_paths"])

    def test_allows_binary_and_symlink_when_policy_explicitly_allows_them(self) -> None:
        patch = "\n".join(
            [
                "diff --git a/archive.bin b/archive.bin",
                "index 1111111..2222222 100644",
                "GIT binary patch",
                "literal 1",
                "IcmZPo000310RR91",
                "diff --git a/current-link b/current-link",
                "new file mode 120000",
                "--- /dev/null",
                "+++ b/current-link",
                "@@ -0,0 +1 @@",
                "+target.txt",
                "",
            ]
        )

        result = diff_policy.evaluate_patch(
            patch,
            {**POLICY, "allow_binary_files": True, "allow_symlinks": True},
        )

        self.assertTrue(result["allowed"])

    def test_blocks_added_ignore_annotation_in_test_source(self) -> None:
        patch = new_file_patch(
            "src/test/kotlin/com/example/ExampleTest.kt",
            "@Ignore(\"temporarily broken\")",
        )

        result = diff_policy.evaluate_patch(patch, POLICY)

        violation = next(
            item
            for item in result["violations"]
            if item["rule"] == "test_disable_requires_approval"
        )
        self.assertEqual(["src/test/kotlin/com/example/ExampleTest.kt"], violation["paths"])
        self.assertEqual("added_forbidden_annotation", violation["matches"][0]["change"])

    def test_blocks_test_disable_hidden_by_target_header(self) -> None:
        patch = "\n".join(
            [
                "diff --git a/src/main/kotlin/Allowed.kt b/src/main/kotlin/Allowed.kt",
                "--- /dev/null",
                "+++ b/src/test/kotlin/HiddenTest.kt",
                "@@ -0,0 +1 @@",
                "+@Ignore",
                "",
            ]
        )

        result = diff_policy.evaluate_patch(patch, POLICY)

        violation = next(
            item
            for item in result["violations"]
            if item["rule"] == "test_disable_requires_approval"
        )
        self.assertIn("src/test/kotlin/HiddenTest.kt", violation["paths"])

    def test_blocks_supported_test_disable_annotation_forms(self) -> None:
        for annotation in (
            "@org.junit.Ignore",
            "@Disabled",
            "@org.junit.jupiter.api.Disabled(\"reason\")",
            "@kotlin.test.Ignore",
        ):
            with self.subTest(annotation=annotation):
                result = diff_policy.evaluate_patch(
                    new_file_patch("src/test/kotlin/ExampleTest.kt", annotation),
                    POLICY,
                )

                rules = [violation["rule"] for violation in result["violations"]]
                self.assertIn("test_disable_requires_approval", rules)

    def test_blocks_removed_test_annotation_in_test_source(self) -> None:
        patch = patch_for(
            "src/test/kotlin/com/example/ExampleTest.kt",
            removed="@org.junit.Test",
            added="// test removed",
        )

        result = diff_policy.evaluate_patch(patch, POLICY)

        rules = [violation["rule"] for violation in result["violations"]]
        self.assertIn("test_disable_requires_approval", rules)

    def test_blocks_supported_removed_test_annotation_forms(self) -> None:
        for annotation in (
            "@Test",
            "@org.junit.Test",
            "@org.junit.jupiter.api.Test",
            "@kotlin.test.Test",
        ):
            with self.subTest(annotation=annotation):
                result = diff_policy.evaluate_patch(
                    patch_for(
                        "src/test/kotlin/ExampleTest.kt",
                        removed=annotation,
                        added="// annotation removed",
                    ),
                    POLICY,
                )

                rules = [violation["rule"] for violation in result["violations"]]
                self.assertIn("test_disable_requires_approval", rules)

    def test_allows_existing_ignore_not_added_by_patch(self) -> None:
        patch = patch_for(
            "src/test/kotlin/com/example/ExampleTest.kt",
            removed="assertEquals(1, actual)",
            added="assertEquals(2, actual)",
        )

        result = diff_policy.evaluate_patch(patch, POLICY)

        rules = [violation["rule"] for violation in result["violations"]]
        self.assertNotIn("test_disable_requires_approval", rules)

    def test_allows_ignore_annotation_outside_test_source(self) -> None:
        result = diff_policy.evaluate_patch(
            new_file_patch("docs/example.md", "@Ignore"),
            POLICY,
        )

        self.assertTrue(result["allowed"])

    def test_blocks_deleted_test_file(self) -> None:
        patch = "\n".join(
            [
                "diff --git a/src/test/kotlin/ExampleTest.kt b/src/test/kotlin/ExampleTest.kt",
                "deleted file mode 100644",
                "--- a/src/test/kotlin/ExampleTest.kt",
                "+++ /dev/null",
                "@@ -1 +0,0 @@",
                "-class ExampleTest",
                "",
            ]
        )

        result = diff_policy.evaluate_patch(patch, POLICY)

        violation = next(
            item
            for item in result["violations"]
            if item["rule"] == "test_file_removal_requires_approval"
        )
        self.assertEqual(["src/test/kotlin/ExampleTest.kt"], violation["paths"])

    def test_blocks_deleted_test_hidden_by_old_file_header(self) -> None:
        patch = "\n".join(
            [
                "diff --git a/src/main/kotlin/Allowed.kt b/src/main/kotlin/Allowed.kt",
                "deleted file mode 100644",
                "--- a/src/test/kotlin/HiddenTest.kt",
                "+++ /dev/null",
                "@@ -1 +0,0 @@",
                "-class HiddenTest",
                "",
            ]
        )

        result = diff_policy.evaluate_patch(patch, POLICY)

        violation = next(
            item
            for item in result["violations"]
            if item["rule"] == "test_file_removal_requires_approval"
        )
        self.assertIn("src/test/kotlin/HiddenTest.kt", violation["paths"])

    def test_blocks_renamed_test_file(self) -> None:
        patch = "\n".join(
            [
                "diff --git a/src/test/kotlin/ExampleTest.kt b/archive/ExampleTest.kt",
                "similarity index 100%",
                "rename from src/test/kotlin/ExampleTest.kt",
                "rename to archive/ExampleTest.kt",
                "",
            ]
        )

        result = diff_policy.evaluate_patch(patch, POLICY)

        rules = [violation["rule"] for violation in result["violations"]]
        self.assertIn("test_file_removal_requires_approval", rules)

    def test_allows_deleted_non_test_file(self) -> None:
        patch = "\n".join(
            [
                "diff --git a/src/main/kotlin/Obsolete.kt b/src/main/kotlin/Obsolete.kt",
                "deleted file mode 100644",
                "--- a/src/main/kotlin/Obsolete.kt",
                "+++ /dev/null",
                "@@ -1 +0,0 @@",
                "-class Obsolete",
                "",
            ]
        )

        result = diff_policy.evaluate_patch(patch, POLICY)

        rules = [violation["rule"] for violation in result["violations"]]
        self.assertNotIn("test_file_removal_requires_approval", rules)

    def test_blocks_high_confidence_secret_signatures_without_echoing_values(self) -> None:
        secrets = {
            "private_key_header": "-----BEGIN " + "PRIVATE KEY-----",
            "github_token": "github_" + "pat_" + ("A" * 24),
            "aws_access_key_id": "AKIA" + ("A" * 16),
            "google_api_key": "AIza" + ("A" * 35),
        }

        for expected_signature, secret in secrets.items():
            with self.subTest(signature=expected_signature):
                result = diff_policy.evaluate_patch(
                    new_file_patch("src/main/resources/local.properties", f"token={secret}"),
                    POLICY,
                )
                violation = next(
                    item
                    for item in result["violations"]
                    if item["rule"] == "high_confidence_secret"
                )
                rendered = json.dumps(result) + diff_policy.format_text(result)

                self.assertEqual(expected_signature, violation["detections"][0]["signature"])
                self.assertNotIn(secret, rendered)

    def test_test_disable_diagnostic_does_not_echo_secret_on_same_line(self) -> None:
        secret = "github_" + "pat_" + ("A" * 24)

        result = diff_policy.evaluate_patch(
            new_file_patch("src/test/kotlin/ExampleTest.kt", f"@Ignore(\"{secret}\")"),
            POLICY,
        )
        rendered = json.dumps(result) + diff_policy.format_text(result)

        self.assertFalse(result["allowed"])
        self.assertNotIn(secret, rendered)

    def test_allows_removing_high_confidence_secret(self) -> None:
        secret = "github_" + "pat_" + ("A" * 24)

        result = diff_policy.evaluate_patch(
            patch_for("config.txt", removed=f"token={secret}", added="token=<removed>"),
            POLICY,
        )

        rules = [violation["rule"] for violation in result["violations"]]
        self.assertNotIn("high_confidence_secret", rules)

    def test_policy_requires_explicit_binary_and_symlink_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            policy_path = Path(temp_dir) / "policy.json"
            policy_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "max_files": 2,
                        "max_changed_lines": 4,
                        "protected_patterns": [],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "allow_binary_files, allow_symlinks"):
                diff_policy.load_policy(policy_path)

    def test_policy_requires_explicit_test_disable_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            policy_path = Path(temp_dir) / "policy.json"
            policy_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "max_files": 2,
                        "max_changed_lines": 4,
                        "allow_binary_files": False,
                        "allow_symlinks": False,
                        "protected_patterns": [],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "forbidden_added_test_patterns"):
                diff_policy.load_policy(policy_path)

    def test_policy_rejects_invalid_test_disable_regex(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            policy_path = Path(temp_dir) / "policy.json"
            policy_path.write_text(
                json.dumps({**POLICY, "forbidden_added_test_patterns": ["("]}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Invalid regular expression"):
                diff_policy.load_policy(policy_path)

    def test_policy_rejects_duplicate_or_invalid_secret_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            duplicate_policy = temp / "duplicate.json"
            duplicate_policy.write_text(
                json.dumps(
                    {
                        **POLICY,
                        "secret_patterns": [
                            {"id": "duplicate", "pattern": "one"},
                            {"id": "duplicate", "pattern": "two"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            invalid_policy = temp / "invalid.json"
            invalid_policy.write_text(
                json.dumps(
                    {
                        **POLICY,
                        "secret_patterns": [{"id": "invalid", "pattern": "("}],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Duplicate secret pattern id"):
                diff_policy.load_policy(duplicate_policy)
            with self.assertRaisesRegex(ValueError, "Invalid regular expression"):
                diff_policy.load_policy(invalid_policy)

    def test_policy_requires_explicit_secret_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            policy_path = Path(temp_dir) / "policy.json"
            policy_path.write_text(
                json.dumps({key: value for key, value in POLICY.items() if key != "secret_patterns"}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "secret_patterns"):
                diff_policy.load_policy(policy_path)

    def test_counts_content_that_looks_like_file_headers(self) -> None:
        patch = "\n".join(
            [
                "diff --git a/src/One.kt b/src/One.kt",
                "--- a/src/One.kt",
                "+++ b/src/One.kt",
                "@@ -1 +1 @@",
                "--- old comment",
                "+++ new comment",
                "",
            ]
        )

        result = diff_policy.evaluate_patch(patch, POLICY)

        self.assertTrue(result["allowed"])
        self.assertEqual(2, result["facts"]["changed_lines"])

    def test_preserves_real_path_starting_with_a_prefix(self) -> None:
        result = diff_policy.evaluate_patch(patch_for("a/actual.txt"), POLICY, ("a/actual.txt",))

        self.assertTrue(result["allowed"])
        self.assertEqual(["a/actual.txt"], result["facts"]["paths"])

    def test_blocks_malformed_nonempty_input(self) -> None:
        result = diff_policy.evaluate_patch("not a Git patch", POLICY)

        self.assertFalse(result["allowed"])
        self.assertEqual("valid_git_patch", result["violations"][0]["rule"])

    def test_blocks_patch_that_omits_worktree_path(self) -> None:
        result = diff_policy.evaluate_patch(
            patch_for("tracked.txt"),
            POLICY,
            ("tracked.txt", "untracked.txt"),
        )

        self.assertFalse(result["allowed"])
        violation = result["violations"][0]
        self.assertEqual("patch_matches_worktree", violation["rule"])
        self.assertEqual(["untracked.txt"], violation["missing_from_patch"])

    def test_blocks_patch_path_absent_from_worktree(self) -> None:
        result = diff_policy.evaluate_patch(
            patch_for("tracked.txt") + patch_for("invented.txt"),
            POLICY,
            ("tracked.txt",),
        )

        self.assertFalse(result["allowed"])
        violation = result["violations"][0]
        self.assertEqual(["invented.txt"], violation["absent_from_worktree"])

    def test_collects_tracked_staged_deleted_and_untracked_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            base = initialize_git_repo(repo)
            (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
            (repo / "staged.txt").write_text("staged\n", encoding="utf-8")
            run_git(repo, "add", "staged.txt")
            (repo / "deleted.txt").write_text("delete me\n", encoding="utf-8")
            run_git(repo, "add", "deleted.txt")
            run_git(repo, "commit", "-m", "add deleted fixture")
            base = run_git(repo, "rev-parse", "HEAD")
            (repo / "deleted.txt").unlink()
            (repo / "untracked.txt").write_text("untracked\n", encoding="utf-8")
            (repo / "a").mkdir()
            (repo / "a" / "actual.txt").write_text("actual\n", encoding="utf-8")

            repo_root, base_commit, paths = diff_policy.collect_worktree_paths(repo, base)

        self.assertEqual(repo.resolve(), repo_root)
        self.assertEqual(base, base_commit)
        self.assertEqual(
            ("a/actual.txt", "deleted.txt", "tracked.txt", "untracked.txt"),
            paths,
        )

    def test_cli_exit_codes_and_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            policy_path = temp / "policy.json"
            allowed_patch = temp / "allowed.diff"
            blocked_patch = temp / "blocked.diff"
            policy_path.write_text(json.dumps(POLICY), encoding="utf-8")
            allowed_patch.write_text(patch_for("src/Example.kt"), encoding="utf-8")
            blocked_patch.write_text(patch_for(".github/workflows/build.yml"), encoding="utf-8")

            allowed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--patch",
                    str(allowed_patch),
                    "--policy",
                    str(policy_path),
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            blocked = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--patch",
                    str(blocked_patch),
                    "--policy",
                    str(policy_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(0, allowed.returncode)
        self.assertTrue(json.loads(allowed.stdout)["allowed"])
        self.assertEqual(2, blocked.returncode)
        self.assertIn("diff-policy: BLOCKED", blocked.stdout)

    def test_cli_blocks_patch_that_omits_untracked_worktree_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            base = initialize_git_repo(repo)
            (repo / "tracked.txt").write_text("new\n", encoding="utf-8")
            (repo / "untracked.txt").write_text("untracked\n", encoding="utf-8")
            patch_path = temp / "patch.diff"
            write_git_diff(repo, base, patch_path)
            policy_path = temp / "policy.json"
            policy_path.write_text(json.dumps(POLICY), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--patch",
                    str(patch_path),
                    "--policy",
                    str(policy_path),
                    "--repo",
                    str(repo),
                    "--base",
                    base,
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(2, completed.returncode)
        result = json.loads(completed.stdout)
        mismatch = next(
            violation
            for violation in result["violations"]
            if violation["rule"] == "patch_matches_worktree"
        )
        self.assertEqual(["untracked.txt"], mismatch["missing_from_patch"])

    def test_cli_allows_patch_that_matches_base_and_worktree_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            base = initialize_git_repo(repo)
            (repo / "tracked.txt").write_text("new\n", encoding="utf-8")
            patch_path = temp / "patch.diff"
            write_git_diff(repo, base, patch_path)
            policy_path = temp / "policy.json"
            policy_path.write_text(json.dumps(POLICY), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--patch",
                    str(patch_path),
                    "--policy",
                    str(policy_path),
                    "--repo",
                    str(repo),
                    "--base",
                    base,
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["allowed"])

    def test_cli_allows_complete_patch_with_untracked_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            base = initialize_git_repo(repo)
            (repo / "untracked.txt").write_text("untracked\n", encoding="utf-8")
            patch_path = temp / "patch.diff"
            patch_path.write_text(new_file_patch("untracked.txt", "untracked"), encoding="utf-8")
            policy_path = temp / "policy.json"
            policy_path.write_text(json.dumps(POLICY), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--patch",
                    str(patch_path),
                    "--policy",
                    str(policy_path),
                    "--repo",
                    str(repo),
                    "--base",
                    base,
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["allowed"])

    def test_cli_blocks_patch_with_correct_path_but_wrong_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            base = initialize_git_repo(repo)
            (repo / "tracked.txt").write_text("actual worktree content\n", encoding="utf-8")
            patch_path = temp / "patch.diff"
            patch_path.write_text(
                patch_for("tracked.txt", removed="old", added="invented content"),
                encoding="utf-8",
            )
            policy_path = temp / "policy.json"
            policy_path.write_text(json.dumps(POLICY), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--patch",
                    str(patch_path),
                    "--policy",
                    str(policy_path),
                    "--repo",
                    str(repo),
                    "--base",
                    base,
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(2, completed.returncode)
        rules = [violation["rule"] for violation in json.loads(completed.stdout)["violations"]]
        self.assertIn("patch_matches_worktree_content", rules)

    def test_cli_secret_block_stops_before_content_verification_without_echo(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            base = initialize_git_repo(repo)
            secret = "github_" + "pat_" + ("A" * 24)
            (repo / "tracked.txt").write_text("actual worktree content\n", encoding="utf-8")
            patch_path = temp / "patch.diff"
            patch_path.write_text(
                patch_for("tracked.txt", removed="old", added=f"token={secret}"),
                encoding="utf-8",
            )
            policy_path = temp / "policy.json"
            policy_path.write_text(json.dumps(POLICY), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--patch",
                    str(patch_path),
                    "--policy",
                    str(policy_path),
                    "--repo",
                    str(repo),
                    "--base",
                    base,
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(2, completed.returncode)
        self.assertNotIn(secret, completed.stdout + completed.stderr)
        rules = [violation["rule"] for violation in json.loads(completed.stdout)["violations"]]
        self.assertIn("high_confidence_secret", rules)
        self.assertNotIn("patch_matches_worktree_content", rules)

    def test_repository_policy_protects_quality_gate_inputs(self) -> None:
        repository_policy = diff_policy.load_policy(REPOSITORY_POLICY_PATH)
        protected_paths = [
            ".github/workflows/quality-gate.yml",
            ".agent/checks/diff_policy.py",
            ".agents/skills/proparse-research/SKILL.md",
            "agents/reviewer.md",
            ".gitignore",
            "AGENTS.md",
            "skills/legacy-experiment/SKILL.md",
            "docs/agent-guides/diff-policy.md",
            "scripts/legacy-build.sh",
            "config/detekt/detekt.yml",
            "build.gradle.kts",
            "gradle/wrapper/gradle-wrapper.properties",
            "src/main/resources/META-INF/plugin.xml",
        ]

        for path in protected_paths:
            with self.subTest(path=path):
                result = diff_policy.evaluate_patch(patch_for(path), repository_policy)
                rules = [violation["rule"] for violation in result["violations"]]
                self.assertIn("protected_paths", rules)


if __name__ == "__main__":
    unittest.main()
