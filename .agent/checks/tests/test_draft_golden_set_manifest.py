from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = CHECKS_DIR.parents[1]
MODULE_PATH = CHECKS_DIR / "draft_golden_set_manifest.py"
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("draft_golden_set_manifest", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
draft = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = draft
SPEC.loader.exec_module(draft)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def init_repo(parent: Path) -> Path:
    repo = parent / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "draft@example.invalid")
    git(repo, "config", "user.name", "Golden Draft")
    for name in draft.load_policy()["bindings"]:
        source = REPO_ROOT / name
        destination = repo / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
    (repo / "README.md").write_text("root\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "root")
    commits = [
        ("docs/readme.md", "docs: update setup notes"),
        ("src/test/example.txt", "test: add missing parser test"),
        ("src/main/example.txt", "fix(parser): handle ABL edge case"),
        ("src/main/feature.txt", "feat(psi): add symbol navigation"),
    ]
    for path, subject in commits:
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(subject + "\n", encoding="utf-8")
        git(repo, "add", path)
        git(repo, "commit", "-m", subject)
    return repo


class DraftGoldenSetManifestTest(unittest.TestCase):
    def test_policy_is_exact_draft_only(self) -> None:
        policy = draft.load_policy()

        self.assertEqual(draft.EXPECTED_POLICY, policy)
        self.assertEqual("draft-only", policy["mode"])
        self.assertIn("refuse_or_escalate", policy["required_categories"])

    def test_writes_external_draft_without_claiming_candidate_validity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            repo = init_repo(parent)
            output = parent / "draft.json"

            result = draft.build_draft(repo, output, draft.load_policy())
            value = json.loads(output.read_text(encoding="utf-8"))

        self.assertTrue(result["draft_written"])
        self.assertFalse(result["candidate_manifest_valid"])
        self.assertFalse(result["golden_set_ready"])
        self.assertTrue(value["not_a_candidate_manifest"])
        self.assertTrue(value["requires_closed_github_issues"])
        self.assertGreaterEqual(value["draft_candidate_count"], 4)
        self.assertIn("missing_test", value["covered_category_hints"])
        self.assertIn("refuse_or_escalate", value["missing_category_hints"])
        for field in draft.FALSE_FIELDS:
            self.assertFalse(value[field])

    def test_rejects_output_inside_checkout_and_cli_policy_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            repo = init_repo(parent)
            with self.assertRaisesRegex(ValueError, "outside the Git checkout"):
                draft.build_draft(repo, repo / "draft.json", draft.load_policy())

        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--repo",
                str(REPO_ROOT),
                "--output",
                "draft.json",
                "--policy",
                "untrusted.json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, completed.returncode)
        self.assertIn("unrecognized arguments", completed.stderr)


if __name__ == "__main__":
    unittest.main()
