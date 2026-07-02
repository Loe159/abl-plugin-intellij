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
MODULE_PATH = CHECKS_DIR / "draft_pr_golden_set_manifest.py"
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("draft_pr_golden_set_manifest", MODULE_PATH)
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


def init_repo(parent: Path) -> tuple[Path, str]:
    repo = parent / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "pr-draft@example.invalid")
    git(repo, "config", "user.name", "PR Draft")
    for name in draft.load_policy()["bindings"]:
        source = REPO_ROOT / name
        destination = repo / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")
    (repo / "src.txt").write_text("feature\n", encoding="utf-8")
    git(repo, "add", "src.txt")
    git(repo, "commit", "-m", "feat: merged change")
    return repo, git(repo, "rev-parse", "HEAD")


def pr_record(number: int, commit: str) -> dict[str, object]:
    return {
        "number": number,
        "title": f"feat: merged change {number}",
        "state": "MERGED",
        "mergedAt": "2026-06-01T10:00:00Z",
        "url": f"https://github.com/Loe159/abl-plugin-intellij/pull/{number}",
        "mergeCommit": {"oid": commit},
        "headRefName": f"feature-{number}",
        "baseRefName": "main",
        "files": [{"path": "src.txt", "additions": 1, "deletions": 0, "changeType": "MODIFIED"}],
    }


class DraftPrGoldenSetManifestTest(unittest.TestCase):
    def test_policy_is_exact_draft_only(self) -> None:
        policy = draft.load_policy()

        self.assertEqual(draft.EXPECTED_POLICY, policy)
        self.assertEqual("draft-only", policy["mode"])
        self.assertIn("refuse_or_escalate_case", policy["required_missing_controls"])

    def test_writes_external_pr_draft_without_claiming_golden_set(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            repo, commit = init_repo(parent)
            output = parent / "pr-draft.json"
            records = [pr_record(index, commit) for index in range(41, 46)]

            result = draft.build_draft(repo, output, draft.load_policy(), records)
            value = json.loads(output.read_text(encoding="utf-8"))

        self.assertTrue(result["draft_written"])
        self.assertEqual(5, result["merged_pr_count"])
        self.assertEqual(5, result["local_reference_count"])
        self.assertFalse(result["candidate_manifest_valid"])
        self.assertFalse(result["golden_set_ready"])
        self.assertTrue(value["not_a_candidate_manifest"])
        self.assertIn("closed_issue_snapshot_corpus", value["missing_controls"])
        self.assertIn("refuse_or_escalate_case", value["missing_controls"])
        self.assertEqual("merged_pull_request", value["cases"][0]["source_kind"])
        for field in draft.FALSE_FIELDS:
            self.assertFalse(value[field])

    def test_rejects_output_inside_checkout_and_cli_policy_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, commit = init_repo(Path(temp_dir))
            with self.assertRaisesRegex(ValueError, "outside the Git checkout"):
                draft.build_draft(repo, repo / "draft.json", draft.load_policy(), [pr_record(41, commit)])

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

    def test_rejects_pr_draft_below_policy_minimum(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            repo, commit = init_repo(parent)
            records = [
                pr_record(index, commit)
                for index in range(41, 41 + draft.load_policy()["min_prs"] - 1)
            ]

            with self.assertRaisesRegex(ValueError, "at least 5 merged PR records"):
                draft.build_draft(repo, parent / "too-small.json", draft.load_policy(), records)


if __name__ == "__main__":
    unittest.main()
