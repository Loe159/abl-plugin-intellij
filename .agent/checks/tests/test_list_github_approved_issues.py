from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


CHECKS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = CHECKS_DIR.parents[1]
MODULE_PATH = CHECKS_DIR / "list_github_approved_issues.py"
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("list_github_approved_issues", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
queue = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = queue
SPEC.loader.exec_module(queue)


def issue(number: int, labels: list[object] | None = None) -> dict[str, object]:
    return {
        "number": number,
        "url": f"https://github.com/Loe159/abl-plugin-intellij/issues/{number}",
        "state": "OPEN",
        "title": f"Issue {number}",
        "author": {"login": "Loe159"},
        "labels": labels if labels is not None else [{"name": "agent:approved"}],
        "createdAt": "2026-06-18T10:00:00Z",
        "updatedAt": "2026-06-18T11:00:00Z",
    }


class ListGithubApprovedIssuesTest(unittest.TestCase):
    def test_policy_is_exact_read_only_queue_snapshot(self) -> None:
        policy = queue.load_policy()

        self.assertEqual(queue.EXPECTED_POLICY, policy)
        self.assertEqual("read-only-gh-issue-list", policy["mode"])
        self.assertNotIn("body", policy["gh_json_fields"])

    def test_gh_issue_list_command_is_read_only_and_label_bounded(self) -> None:
        def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            self.assertEqual(
                [
                    "gh",
                    "issue",
                    "list",
                    "--repo",
                    "Loe159/abl-plugin-intellij",
                    "--state",
                    "open",
                    "--label",
                    "agent:approved",
                    "--limit",
                    "100",
                    "--json",
                    "author,createdAt,labels,number,state,title,updatedAt,url",
                ],
                command,
            )
            return subprocess.CompletedProcess(command, 0, json.dumps([issue(7)]), "")

        with patch.object(queue.subprocess, "run", fake_run):
            result = queue.run_gh_issue_list(
                "Loe159/abl-plugin-intellij",
                queue.load_policy(),
            )

        self.assertEqual(7, result[0]["number"])

    def test_snapshot_writes_external_queue_without_selecting_issue(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            queue_path = temp / "queue.json"
            args = type(
                "Args",
                (),
                {
                    "repo": REPO_ROOT,
                    "github_repo": "Loe159/abl-plugin-intellij",
                    "queue": queue_path,
                },
            )()
            with patch.object(
                queue,
                "run_gh_issue_list",
                return_value=[
                    issue(8),
                    issue(7, labels=[{"name": "agent:approved"}, {"name": "enhancement"}]),
                    issue(9, labels=[{"name": "agent:approved"}, {"name": "agent:blocked"}]),
                ],
            ):
                result = queue.snapshot(args, queue.load_policy())
            value = json.loads(queue_path.read_text(encoding="utf-8"))

        self.assertTrue(result["produced"])
        self.assertEqual([7, 8], [item["number"] for item in result["eligible_issues"]])
        self.assertEqual(1, result["rejected_count"])
        self.assertFalse(result["issue_selected"])
        self.assertIsNone(result["selected_issue"])
        self.assertFalse(value["issue_selected"])
        self.assertFalse(result["external_service_written"])
        for field in queue.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_queue_output_path_must_be_external_absent_and_parented(self) -> None:
        policy = queue.load_policy()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            inside_checkout = REPO_ROOT / "queue.json"
            with self.assertRaisesRegex(ValueError, "outside the Git checkout"):
                queue.validate_queue_path(REPO_ROOT, inside_checkout, policy)

            existing = temp / "existing-queue.json"
            existing.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already exists"):
                queue.validate_queue_path(REPO_ROOT, existing, policy)

            missing_parent = temp / "missing" / "queue.json"
            with self.assertRaisesRegex(ValueError, "parent must exist"):
                queue.validate_queue_path(REPO_ROOT, missing_parent, policy)

            symlink = temp / "symlink-queue.json"
            try:
                symlink.symlink_to(temp / "target-queue.json")
            except (OSError, NotImplementedError):
                pass
            else:
                with self.assertRaisesRegex(ValueError, "symbolic links"):
                    queue.validate_queue_path(REPO_ROOT, symlink, policy)

    def test_cli_refuses_policy_override(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--repo",
                str(REPO_ROOT),
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
