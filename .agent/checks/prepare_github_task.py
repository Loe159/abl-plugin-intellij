#!/usr/bin/env python3
"""Two-phase local preparation from one approved GitHub issue snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import approve_github_issue_snapshot
import fetch_github_issue_snapshot
import initialize_portable_run


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "prepare-github-task.json"
FALSE_FIELDS = initialize_portable_run.FALSE_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "prepare_github_task_from_approved_issue",
    "mode": "two-phase-fetch-approve-initialize",
    "repository": "Loe159/abl-plugin-intellij",
    "require_fetch_before_check": True,
    "require_exact_snapshot_confirmation": True,
    "task_approval_performed": False,
    "bindings": [
        ".agent/checks/prepare_github_task.py",
        ".agent/policies/prepare-github-task.json",
        ".agent/checks/fetch_github_issue_snapshot.py",
        ".agent/policies/github-issue-snapshot-fetch.json",
        ".agent/checks/approve_github_issue_snapshot.py",
        ".agent/policies/github-issue-ingestion.json",
        ".agent/checks/initialize_portable_run.py",
        ".agent/policies/portable-run-initialization.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Prepare-github-task policy does not match the pilot contract")
    return policy


def base_result(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "prepared": False,
        "fetched": False,
        "snapshot_approvable": False,
        "snapshot_approved": False,
        "portable_run_initialized": False,
        "task_approved": False,
        "task_approval_performed": policy["task_approval_performed"],
        **{field: False for field in FALSE_FIELDS},
        "failures": [],
    }


def fetch_check(args: argparse.Namespace, policy: dict[str, Any]) -> dict[str, Any]:
    if args.github_repo != policy["repository"]:
        raise ValueError("Requested GitHub repository does not match the preparation policy")
    result = base_result(policy)
    fetch = fetch_github_issue_snapshot.produce(
        argparse.Namespace(
            repo=args.repo,
            github_repo=args.github_repo,
            issue=args.issue,
            normalization=args.normalization,
            package=args.package,
            captured_at=args.captured_at,
        ),
        fetch_github_issue_snapshot.load_policy(),
    )
    assessment = approve_github_issue_snapshot.assess(
        args.repo,
        args.package,
        args.normalized_input,
        args.approval_receipt,
        args.approver,
        approve_github_issue_snapshot.load_policy(),
    )
    result.update(
        prepared=assessment["approvable"],
        fetched=fetch["produced"],
        snapshot_approvable=assessment["approvable"],
        repository=args.github_repo,
        issue=args.issue,
        package=str(args.package.resolve()),
        package_sha256=fetch["package_sha256"],
        normalized_input=str(args.normalized_input.resolve()),
        approval_receipt=str(args.approval_receipt.resolve()),
        required_confirmation=assessment["required_confirmation"],
        failures=assessment["failures"],
    )
    return result


def approve_init(args: argparse.Namespace, policy: dict[str, Any]) -> dict[str, Any]:
    result = base_result(policy)
    approval = approve_github_issue_snapshot.approve(
        argparse.Namespace(
            repo=args.repo,
            package=args.package,
            normalized_input=args.normalized_input,
            approval_receipt=args.approval_receipt,
            approver=args.approver,
            confirm=args.confirm,
        ),
        approve_github_issue_snapshot.load_policy(),
    )
    result.update(
        snapshot_approvable=approval.get("approvable") is True,
        snapshot_approved=approval.get("approved") is True,
        repository=approval.get("repository"),
        issue=approval.get("issue"),
        package=str(args.package.resolve()),
        normalized_input=str(args.normalized_input.resolve()),
        approval_receipt=str(args.approval_receipt.resolve()),
        failures=approval.get("failures", []),
    )
    if approval.get("approved") is not True:
        return result
    initialization = initialize_portable_run.initialize(
        args.repo,
        args.normalized_input,
        args.run,
        args.initialization_receipt,
        initialize_portable_run.load_policies(),
    )
    result.update(
        prepared=initialization["initialized"],
        portable_run_initialized=initialization["initialized"],
        run=str(args.run.resolve()),
        initialization_receipt=str(args.initialization_receipt.resolve()),
        initialization_receipt_sha256=initialization.get("receipt_sha256"),
        approval_receipt_sha256=approval.get("approval_receipt_sha256"),
        failures=initialization["failures"],
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch = subparsers.add_parser("fetch-check")
    fetch.add_argument("--repo", type=Path, required=True)
    fetch.add_argument("--github-repo", default=EXPECTED_POLICY["repository"])
    fetch.add_argument("--issue", type=int, required=True)
    fetch.add_argument("--normalization", type=Path, required=True)
    fetch.add_argument("--package", type=Path, required=True)
    fetch.add_argument("--normalized-input", type=Path, required=True)
    fetch.add_argument("--approval-receipt", type=Path, required=True)
    fetch.add_argument("--approver", required=True)
    fetch.add_argument("--captured-at")
    fetch.add_argument("--format", choices=("text", "json"), default="text")

    approve = subparsers.add_parser("approve-init")
    approve.add_argument("--repo", type=Path, required=True)
    approve.add_argument("--package", type=Path, required=True)
    approve.add_argument("--normalized-input", type=Path, required=True)
    approve.add_argument("--approval-receipt", type=Path, required=True)
    approve.add_argument("--approver", required=True)
    approve.add_argument("--confirm", required=True)
    approve.add_argument("--run", type=Path, required=True)
    approve.add_argument("--initialization-receipt", type=Path, required=True)
    approve.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "PREPARED" if result["prepared"] else "BLOCKED"
    lines = [
        f"prepare-github-task: {status}",
        f"fetched={str(result['fetched']).lower()}",
        f"snapshot_approved={str(result['snapshot_approved']).lower()}",
        f"portable_run_initialized={str(result['portable_run_initialized']).lower()}",
        "task_approved=false",
        "agent_invocation_authorized=false",
    ]
    lines.extend(f"- {item['rule']}: {item['message']}" for item in result["failures"])
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        policy = load_policy()
        result = fetch_check(args, policy) if args.command == "fetch-check" else approve_init(args, policy)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"prepare-github-task: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["prepared"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
