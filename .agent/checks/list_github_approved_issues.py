#!/usr/bin/env python3
"""List approved GitHub issue candidates through gh without selecting work."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import build_stage_context
import fetch_github_issue_snapshot
import initialize_portable_run


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "github-approved-issue-queue.json"
FALSE_FIELDS = initialize_portable_run.FALSE_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "github_approved_issue_queue_snapshot",
    "mode": "read-only-gh-issue-list",
    "repository": "Loe159/abl-plugin-intellij",
    "required_issue_state": "open",
    "required_approval_label": "agent:approved",
    "workflow_status_labels": [
        "agent:candidate",
        "agent:approved",
        "agent:researching",
        "agent:research-review",
        "agent:planning",
        "agent:plan-review",
        "agent:implementing",
        "agent:blocked",
        "agent:done",
    ],
    "gh_json_fields": [
        "author",
        "createdAt",
        "labels",
        "number",
        "state",
        "title",
        "updatedAt",
        "url",
    ],
    "max_issues": 100,
    "max_title_characters": 500,
    "max_author_characters": 100,
    "max_labels": 50,
    "max_label_characters": 100,
    "max_queue_bytes": 120000,
    "require_external_queue": True,
    "require_absent_queue": True,
    "bindings": [
        ".agent/checks/list_github_approved_issues.py",
        ".agent/policies/github-approved-issue-queue.json",
        ".agent/checks/fetch_github_issue_snapshot.py",
        ".agent/policies/github-issue-snapshot-fetch.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("GitHub approved-issue queue policy does not match")
    return policy


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def validate_queue_path(repo_root: Path, queue: Path | None, policy: dict[str, Any]) -> Path | None:
    if queue is None:
        return None
    if queue.is_symlink():
        raise ValueError("Queue output symbolic links are not allowed")
    queue = queue.resolve()
    if policy["require_external_queue"] and build_stage_context.is_within(queue, repo_root):
        raise ValueError("Queue output must be outside the Git checkout")
    if policy["require_absent_queue"] and queue.exists():
        raise ValueError("Queue output already exists")
    if not queue.parent.is_dir():
        raise ValueError("Queue output parent must exist")
    return queue


def run_gh_issue_list(repository: str, policy: dict[str, Any]) -> list[Any]:
    fields = ",".join(policy["gh_json_fields"])
    completed = subprocess.run(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repository,
            "--state",
            policy["required_issue_state"],
            "--label",
            policy["required_approval_label"],
            "--limit",
            str(policy["max_issues"]),
            "--json",
            fields,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "unknown gh failure"
        raise ValueError(f"gh issue list failed: {detail}")
    value = json.loads(completed.stdout)
    if not isinstance(value, list):
        raise ValueError("gh issue list response must be a JSON array")
    return value


def normalize_issue(value: Any, repository: str, policy: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Issue list item must be a JSON object")
    number = value.get("number")
    if type(number) is not int or number < 1:
        raise ValueError("Issue number must be a positive integer")
    expected_url = f"https://github.com/{repository}/issues/{number}"
    state = value.get("state")
    if type(state) is not str or state.lower() != policy["required_issue_state"]:
        raise ValueError("Issue state does not match the queue contract")
    if value.get("url") != expected_url:
        raise ValueError("Issue URL does not match the requested repository and issue")
    labels = fetch_github_issue_snapshot.label_names(value.get("labels"), policy)
    return {
        "number": number,
        "url": expected_url,
        "state": state.lower(),
        "title": fetch_github_issue_snapshot.bounded_text(
            value.get("title"),
            "issue.title",
            policy["max_title_characters"],
        ),
        "author": fetch_github_issue_snapshot.author_login(value.get("author"), policy),
        "labels": labels,
        "created_at": fetch_github_issue_snapshot.bounded_text(
            value.get("createdAt"),
            "issue.createdAt",
            100,
        ),
        "updated_at": fetch_github_issue_snapshot.bounded_text(
            value.get("updatedAt"),
            "issue.updatedAt",
            100,
        ),
    }


def snapshot(args: argparse.Namespace, policy: dict[str, Any]) -> dict[str, Any]:
    if args.github_repo != policy["repository"]:
        raise ValueError("Requested GitHub repository does not match the queue policy")
    repo_root = Path(
        fetch_github_issue_snapshot.diff_policy.run_git(
            args.repo,
            "rev-parse",
            "--show-toplevel",
        )
        .decode("utf-8")
        .strip()
    ).resolve()
    queue_path = validate_queue_path(repo_root, args.queue, policy)
    raw = run_gh_issue_list(args.github_repo, policy)
    eligible: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for item in raw:
        try:
            eligible.append(normalize_issue(item, args.github_repo, policy))
        except ValueError as error:
            number = item.get("number") if isinstance(item, dict) else None
            rejected.append({"number": number, "reason": str(error)})
    eligible.sort(key=lambda issue: issue["number"])
    rejected.sort(key=lambda issue: (-1 if issue["number"] is None else issue["number"]))
    value = {
        "queue_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "github_label_observed_by_gh": True,
        "github_label_independently_verified": False,
        "source_state_authenticated": False,
        "external_service_written": False,
        "repository_mutated": False,
        "selected_issue": None,
        "issue_selected": False,
        "repository": args.github_repo,
        "eligible_count": len(eligible),
        "rejected_count": len(rejected),
        "eligible_issues": eligible,
        "rejected_issues": rejected,
        "bindings": fetch_github_issue_snapshot.binding_records(repo_root, policy["bindings"]),
    }
    queue_bytes = canonical_bytes(value)
    if len(queue_bytes) > policy["max_queue_bytes"]:
        raise ValueError("Queue snapshot exceeds max_queue_bytes")
    result = dict(value)
    result["produced"] = queue_path is not None
    result["queue"] = str(queue_path) if queue_path is not None else None
    result["queue_sha256"] = (
        fetch_github_issue_snapshot.sha256_bytes(queue_bytes)
        if queue_path is not None
        else None
    )
    if queue_path is not None:
        with queue_path.open("xb") as stream:
            stream.write(queue_bytes)
            stream.flush()
            os.fsync(stream.fileno())
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--github-repo", default=EXPECTED_POLICY["repository"])
    parser.add_argument("--queue", type=Path)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    return "\n".join(
        [
            "github-approved-issue-queue: LISTED",
            f"eligible_count={result['eligible_count']}",
            f"rejected_count={result['rejected_count']}",
            "issue_selected=false",
            "agent_invocation_authorized=false",
        ]
    )


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = snapshot(args, load_policy())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"github-approved-issue-queue: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
