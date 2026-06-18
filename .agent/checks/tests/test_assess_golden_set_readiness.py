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
MODULE_PATH = CHECKS_DIR / "assess_golden_set_readiness.py"
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("assess_golden_set_readiness", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
golden = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = golden
SPEC.loader.exec_module(golden)


def run_git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def initialize_repo(parent: Path) -> tuple[Path, list[str]]:
    repo = parent / "repo"
    repo.mkdir()
    run_git(repo, "init")
    run_git(repo, "config", "user.email", "tests@example.invalid")
    run_git(repo, "config", "user.name", "Golden Set Tests")
    (repo / "case.txt").write_text("root\n", encoding="utf-8")
    run_git(repo, "add", "case.txt")
    run_git(repo, "commit", "-m", "root")
    commits = []
    for index in range(1, 5):
        (repo / "case.txt").write_text(f"case {index}\n", encoding="utf-8")
        run_git(repo, "add", "case.txt")
        run_git(repo, "commit", "-m", f"case {index}")
        commits.append(run_git(repo, "rev-parse", "HEAD"))
    for name in golden.load_policy()["bindings"]:
        source = REPO_ROOT / name
        destination = repo / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
    return repo, commits


def case(
    number: int,
    categories: list[str],
    commit: str | None,
    outcome: str = "patch",
) -> dict[str, object]:
    return {
        "id": f"issue-{number}",
        "issue": {
            "number": number,
            "url": f"https://github.com/Loe159/abl-plugin-intellij/issues/{number}",
            "state": "closed",
            "title_sha256": f"{number:064x}",
            "snapshot_sha256": f"{number + 100:064x}",
        },
        "categories": categories,
        "expected_outcome": outcome,
        "success_criteria": [f"Criterion for issue {number}"],
        "reference": {
            "kind": "commit" if commit is not None else "decision",
            "commit": commit,
            "verification": [f"Verify issue {number} deterministically"],
        },
    }


def manifest(commits: list[str]) -> dict[str, object]:
    return {
        "manifest_version": 1,
        "purpose": "historical_golden_set_candidate_manifest",
        "mode": "candidate-data-only",
        "repository": "Loe159/abl-plugin-intellij",
        "captured_at": "2026-06-18T10:00:00Z",
        "cases": [
            case(101, ["docs_or_typo"], commits[0]),
            case(102, ["simple_bug"], commits[1]),
            case(103, ["missing_test"], commits[2]),
            case(104, ["local_feature", "abl_rssw_research"], commits[3]),
            case(105, ["refuse_or_escalate"], None, "refuse_or_escalate"),
        ],
    }


def prepare(parent: Path) -> tuple[Path, Path, dict[str, object]]:
    repo, commits = initialize_repo(parent)
    value = manifest(commits)
    path = parent / "golden-set.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return repo, path, value


class AssessGoldenSetReadinessTest(unittest.TestCase):
    def test_policy_is_exact_candidate_only_and_non_authorizing(self) -> None:
        policy = golden.load_policy()

        self.assertEqual(golden.EXPECTED_POLICY, policy)
        self.assertEqual("candidate-only", policy["mode"])
        self.assertEqual(5, policy["min_cases"])
        self.assertIn("refuse_or_escalate", policy["required_categories"])

    def test_valid_candidate_manifest_verifies_local_commits_but_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, path, _value = prepare(Path(temp_dir))
            result = golden.assess(repo, path, golden.load_policy())

        self.assertTrue(result["candidate_manifest_valid"], result["reference_failures"])
        self.assertTrue(result["coverage_complete"])
        self.assertTrue(result["local_references_verified"])
        self.assertEqual(4, len(result["local_references"]))
        self.assertFalse(result["source_state_authenticated"])
        self.assertFalse(result["issue_closure_independently_verified"])
        self.assertFalse(result["issue_reference_equivalence_verified"])
        self.assertFalse(result["golden_set_ready"])
        for field in golden.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_open_issue_and_in_checkout_manifest_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            repo, path, value = prepare(parent)
            value["cases"][0]["issue"]["state"] = "open"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exact closed issue"):
                golden.assess(repo, path, golden.load_policy())

            value["cases"][0]["issue"]["state"] = "closed"
            inside = repo / "golden-set.json"
            inside.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "outside the Git checkout"):
                golden.assess(repo, inside, golden.load_policy())

    def test_missing_category_or_commit_keeps_candidate_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, path, value = prepare(Path(temp_dir))
            value["cases"][3]["categories"] = ["local_feature"]
            path.write_text(json.dumps(value), encoding="utf-8")
            missing_category = golden.assess(repo, path, golden.load_policy())

            value["cases"][3]["categories"] = ["local_feature", "abl_rssw_research"]
            value["cases"][0]["reference"]["commit"] = "f" * 40
            path.write_text(json.dumps(value), encoding="utf-8")
            missing_commit = golden.assess(repo, path, golden.load_policy())

        self.assertFalse(missing_category["candidate_manifest_valid"])
        self.assertIn("abl_rssw_research", missing_category["missing_categories"])
        self.assertFalse(missing_commit["candidate_manifest_valid"])
        self.assertEqual("issue-101", missing_commit["reference_failures"][0]["case"])

    def test_cli_refuses_policy_override(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--repo",
                str(REPO_ROOT),
                "--manifest",
                "candidate.json",
                "--policy",
                "untrusted",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(2, completed.returncode)
        self.assertIn("unrecognized arguments", completed.stderr)


if __name__ == "__main__":
    unittest.main()
