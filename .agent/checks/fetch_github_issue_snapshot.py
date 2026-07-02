#!/usr/bin/env python3
"""Fetch one approved GitHub issue snapshot through gh without authorizing work."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import approve_github_issue_snapshot
import build_stage_context
import diff_policy
import initialize_portable_run


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "github-issue-snapshot-fetch.json"
FALSE_FIELDS = initialize_portable_run.FALSE_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "github_issue_snapshot_fetch",
    "mode": "read-only-gh-issue-view-plus-human-normalization",
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
        "body",
        "labels",
        "number",
        "state",
        "title",
        "url",
    ],
    "max_normalization_bytes": 20000,
    "max_package_bytes": 50000,
    "max_title_characters": 500,
    "max_body_characters": 20000,
    "max_author_characters": 100,
    "max_labels": 50,
    "max_label_characters": 100,
    "require_external_normalization": True,
    "require_external_package": True,
    "require_absent_package": True,
    "bindings": [
        ".agent/checks/fetch_github_issue_snapshot.py",
        ".agent/policies/github-issue-snapshot-fetch.json",
        ".agent/checks/approve_github_issue_snapshot.py",
        ".agent/policies/github-issue-ingestion.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("GitHub issue snapshot-fetch policy does not match the pilot contract")
    return policy


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def binding_records(repo: Path, names: list[str]) -> list[dict[str, Any]]:
    records = []
    for name in names:
        path = repo / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Snapshot-fetch binding must be a regular file: {name}")
        content = path.read_bytes()
        records.append({"name": name, "sha256": sha256_bytes(content), "size_bytes": len(content)})
    return records


def validate_paths(
    repo_root: Path,
    normalization_path: Path,
    package_path: Path,
    policy: dict[str, Any],
) -> tuple[Path, Path]:
    normalization_path = normalization_path.resolve()
    package_path = package_path.resolve()
    if normalization_path.is_symlink() or not normalization_path.is_file():
        raise ValueError("Normalization input must be an existing regular file")
    if package_path.is_symlink():
        raise ValueError("Issue package output symbolic links are not allowed")
    if policy["require_external_normalization"] and build_stage_context.is_within(
        normalization_path,
        repo_root,
    ):
        raise ValueError("Normalization input must be outside the Git checkout")
    if policy["require_external_package"] and build_stage_context.is_within(
        package_path,
        repo_root,
    ):
        raise ValueError("Issue package output must be outside the Git checkout")
    if policy["require_absent_package"] and package_path.exists():
        raise ValueError("Issue package output already exists")
    if not package_path.parent.is_dir():
        raise ValueError("Issue package output parent must exist")
    return normalization_path, package_path


def bounded_text(value: Any, name: str, maximum: int) -> str:
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be a bounded non-empty string")
    return value


def label_names(value: Any, policy: dict[str, Any]) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("Issue labels returned by gh must be a list")
    labels: list[str] = []
    for item in value:
        if isinstance(item, dict):
            name = item.get("name")
        else:
            name = item
        if type(name) is not str or not name or len(name) > policy["max_label_characters"]:
            raise ValueError("Issue labels returned by gh are invalid")
        labels.append(name)
    labels = sorted(set(labels))
    if not labels or len(labels) > policy["max_labels"]:
        raise ValueError("Issue labels returned by gh are outside the contract")
    statuses = sorted(set(labels) & set(policy["workflow_status_labels"]))
    if statuses != [policy["required_approval_label"]]:
        raise ValueError("Issue must carry only the required agent approval status label")
    return labels


def author_login(value: Any, policy: dict[str, Any]) -> str:
    if isinstance(value, dict):
        value = value.get("login")
    return bounded_text(value, "issue.author", policy["max_author_characters"])


def issue_from_gh(value: Any, repository: str, issue_number: int, policy: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("gh issue response must be a JSON object")
    expected_url = f"https://github.com/{repository}/issues/{issue_number}"
    number = value.get("number")
    state = value.get("state")
    if type(number) is not int or number != issue_number:
        raise ValueError("gh issue response number does not match the requested issue")
    if type(state) is not str or state.lower() != policy["required_issue_state"]:
        raise ValueError("gh issue response state does not match the snapshot-fetch contract")
    if value.get("url") != expected_url:
        raise ValueError("gh issue response URL does not match the requested repository and issue")
    return {
        "number": number,
        "url": expected_url,
        "state": state.lower(),
        "title": bounded_text(value.get("title"), "issue.title", policy["max_title_characters"]),
        "body": bounded_text(value.get("body"), "issue.body", policy["max_body_characters"]),
        "author": author_login(value.get("author"), policy),
        "labels": label_names(value.get("labels"), policy),
    }


def run_gh_issue_view(repository: str, issue_number: int, policy: dict[str, Any]) -> dict[str, Any]:
    fields = ",".join(policy["gh_json_fields"])
    completed = subprocess.run(
        [
            "gh",
            "issue",
            "view",
            str(issue_number),
            "--repo",
            repository,
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
        raise ValueError(f"gh issue view failed: {detail}")
    return json.loads(completed.stdout)


def validate_normalization(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"risk", "base_commit", "task"}:
        raise ValueError("Normalization input fields do not match the contract")
    package_probe = {
        "package_version": 1,
        "purpose": "github_issue_manual_normalization_candidate",
        "mode": "external-snapshot-plus-human-normalization",
        "repository": EXPECTED_POLICY["repository"],
        "captured_at": "2026-01-01T00:00:00Z",
        "issue": {
            "number": 1,
            "url": f"https://github.com/{EXPECTED_POLICY['repository']}/issues/1",
            "state": EXPECTED_POLICY["required_issue_state"],
            "title": "Probe",
            "body": "Probe body",
            "author": "probe",
            "labels": [EXPECTED_POLICY["required_approval_label"]],
        },
        "normalization": value,
    }
    approve_github_issue_snapshot.validate_package(
        package_probe,
        approve_github_issue_snapshot.load_policy(),
    )
    return value


def build_package(
    repository: str,
    issue_number: int,
    captured_at: str,
    gh_issue: dict[str, Any],
    normalization: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    package = {
        "package_version": policy["version"],
        "purpose": "github_issue_manual_normalization_candidate",
        "mode": "external-snapshot-plus-human-normalization",
        "repository": repository,
        "captured_at": approve_github_issue_snapshot.parse_utc(captured_at, "captured_at"),
        "issue": issue_from_gh(gh_issue, repository, issue_number, policy),
        "normalization": validate_normalization(normalization),
    }
    approve_github_issue_snapshot.validate_package(
        package,
        approve_github_issue_snapshot.load_policy(),
    )
    package_bytes = canonical_bytes(package)
    if len(package_bytes) > policy["max_package_bytes"]:
        raise ValueError("Issue package exceeds max_package_bytes")
    return package


def produce(args: argparse.Namespace, policy: dict[str, Any]) -> dict[str, Any]:
    if args.github_repo != policy["repository"]:
        raise ValueError("Requested GitHub repository does not match the snapshot-fetch policy")
    if args.issue < 1:
        raise ValueError("Issue number must be positive")
    repo_root = Path(
        diff_policy.run_git(args.repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()
    normalization_path, package_path = validate_paths(
        repo_root,
        args.normalization,
        args.package,
        policy,
    )
    normalization_bytes = normalization_path.read_bytes()
    if len(normalization_bytes) > policy["max_normalization_bytes"]:
        raise ValueError("Normalization input exceeds max_normalization_bytes")
    normalization = json.loads(normalization_bytes.decode("utf-8-sig"))
    gh_issue = run_gh_issue_view(args.github_repo, args.issue, policy)
    package = build_package(
        args.github_repo,
        args.issue,
        args.captured_at or utc_now(),
        gh_issue,
        normalization,
        policy,
    )
    package_bytes = canonical_bytes(package)
    if build_stage_context.detect_secrets(
        [
            build_stage_context.content_record("github-issue-package.json", package_bytes.decode("utf-8")),
            build_stage_context.content_record(
                "github-issue-normalization.json",
                normalization_bytes.decode("utf-8-sig"),
            ),
        ],
        diff_policy.load_policy(REPO_ROOT / ".agent" / "policies" / "diff-policy.json"),
    ):
        raise ValueError("Issue package or normalization contains a high-confidence secret")
    bindings = binding_records(repo_root, policy["bindings"])
    with package_path.open("xb") as stream:
        stream.write(package_bytes)
        stream.flush()
        os.fsync(stream.fileno())
    if package_path.read_bytes() != package_bytes:
        raise ValueError("Issue package changed during final verification")
    return {
        "produced": True,
        **{field: False for field in FALSE_FIELDS},
        "source_state_authenticated": False,
        "github_label_independently_verified": False,
        "github_label_observed_by_gh": True,
        "external_service_written": False,
        "repository_mutated": False,
        "package_approved": False,
        "normalized_task_input_produced": False,
        "repository": args.github_repo,
        "issue": args.issue,
        "package": str(package_path),
        "package_sha256": sha256_bytes(package_bytes),
        "normalization_sha256": sha256_bytes(normalization_bytes),
        "bindings_sha256": sha256_bytes(canonical_bytes(bindings)),
        "bindings": bindings,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True, help="Local Git checkout")
    parser.add_argument("--github-repo", default=EXPECTED_POLICY["repository"])
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--normalization", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--captured-at", help="RFC 3339 UTC timestamp ending in Z")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    return "\n".join(
        [
            "github-issue-snapshot-fetch: PRODUCED",
            f"issue={result['issue']}",
            "source_state_authenticated=false",
            "github_label_independently_verified=false",
            "agent_invocation_authorized=false",
        ]
    )


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = produce(args, load_policy())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"github-issue-snapshot-fetch: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
