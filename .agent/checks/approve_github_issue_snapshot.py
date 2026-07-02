#!/usr/bin/env python3
"""Approve one exact external GitHub issue snapshot and manual normalization."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import apply_stage_output
import build_stage_context
import diff_policy
import initialize_portable_run


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "github-issue-ingestion.json"
SHA256 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")
UTC_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z")
FALSE_FIELDS = initialize_portable_run.FALSE_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "approved_github_issue_snapshot_ingestion",
    "mode": "exact-manual-normalization-only",
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
    "confirmation_prefix": "APPROVE-EXACT-GITHUB-ISSUE-SNAPSHOT",
    "max_package_bytes": 50000,
    "max_title_characters": 500,
    "max_body_characters": 20000,
    "max_author_characters": 100,
    "max_labels": 50,
    "max_label_characters": 100,
    "max_approver_characters": 100,
    "max_receipt_bytes": 40000,
    "require_external_package": True,
    "require_external_normalized_input": True,
    "require_external_receipt": True,
    "require_absent_normalized_input": True,
    "require_absent_receipt": True,
    "require_clean_worktree": True,
    "require_repo_head_match": True,
    "bindings": [
        ".agent/checks/approve_github_issue_snapshot.py",
        ".agent/policies/github-issue-ingestion.json",
        ".agent/checks/initialize_portable_run.py",
        ".agent/policies/portable-run-initialization.json",
        ".agent/checks/build_stage_context.py",
        ".agent/checks/diff_policy.py",
        ".agent/policies/diff-policy.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("GitHub issue-ingestion policy does not match the pilot contract")
    return policy


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def exact_mapping(value: Any, fields: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{name} fields do not match the contract")
    return value


def bounded_text(value: Any, name: str, maximum: int) -> str:
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be a bounded non-empty string")
    return value


def parse_utc(value: Any, name: str) -> str:
    if type(value) is not str or UTC_TIMESTAMP.fullmatch(value) is None:
        raise ValueError(f"{name} must be an RFC 3339 UTC timestamp ending in Z")
    parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    if parsed.tzinfo != timezone.utc:
        raise ValueError(f"{name} must use UTC")
    return value


def binding_records(repo: Path, names: list[str]) -> list[dict[str, Any]]:
    records = []
    for name in names:
        path = repo / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Issue-ingestion binding must be a regular file: {name}")
        content = path.read_bytes()
        records.append(
            {
                "name": name,
                "sha256": sha256_bytes(content),
                "size_bytes": len(content),
            }
        )
    return records


def validate_package(value: Any, policy: dict[str, Any]) -> dict[str, Any]:
    package = exact_mapping(
        value,
        {
            "package_version",
            "purpose",
            "mode",
            "repository",
            "captured_at",
            "issue",
            "normalization",
        },
        "Package",
    )
    if (
        type(package["package_version"]) is not int
        or package["package_version"] != policy["version"]
        or package["purpose"] != "github_issue_manual_normalization_candidate"
        or package["mode"] != "external-snapshot-plus-human-normalization"
        or package["repository"] != policy["repository"]
    ):
        raise ValueError("Package identity does not match the contract")
    parse_utc(package["captured_at"], "captured_at")
    issue = exact_mapping(
        package["issue"],
        {"number", "url", "state", "title", "body", "author", "labels"},
        "issue",
    )
    if type(issue["number"]) is not int or issue["number"] < 1:
        raise ValueError("issue.number must be a positive integer")
    expected_url = (
        f"https://github.com/{policy['repository']}/issues/{issue['number']}"
    )
    if issue["url"] != expected_url or issue["state"] != policy["required_issue_state"]:
        raise ValueError("Issue URL or state does not match the ingestion contract")
    bounded_text(issue["title"], "issue.title", policy["max_title_characters"])
    bounded_text(issue["body"], "issue.body", policy["max_body_characters"])
    bounded_text(issue["author"], "issue.author", policy["max_author_characters"])
    labels = issue["labels"]
    if (
        not isinstance(labels, list)
        or not labels
        or len(labels) > policy["max_labels"]
        or len(labels) != len(set(labels))
        or labels != sorted(labels)
        or any(
            type(label) is not str
            or not label
            or len(label) > policy["max_label_characters"]
            for label in labels
        )
    ):
        raise ValueError("Issue labels must be a bounded sorted unique list")
    statuses = sorted(set(labels) & set(policy["workflow_status_labels"]))
    if statuses != [policy["required_approval_label"]]:
        raise ValueError("Issue must carry only the required agent approval status label")

    normalization = exact_mapping(
        package["normalization"],
        {"risk", "base_commit", "task"},
        "normalization",
    )
    if (
        normalization["risk"] not in {"low", "medium", "high"}
        or type(normalization["base_commit"]) is not str
        or COMMIT.fullmatch(normalization["base_commit"]) is None
    ):
        raise ValueError("Normalization risk or base commit is invalid")
    task = exact_mapping(
        normalization["task"],
        set(initialize_portable_run.TASK_FIELDS),
        "normalization.task",
    )
    initialization_policy = initialize_portable_run.load_policy()
    for field in initialize_portable_run.TASK_FIELDS:
        bounded_text(
            task[field],
            f"normalization.task.{field}",
            initialization_policy["max_task_section_characters"],
        )
    return package


def normalized_input(package: dict[str, Any], package_sha256: str) -> dict[str, Any]:
    issue = package["issue"]
    normalization = package["normalization"]
    value = {
        "input_version": 1,
        "purpose": "portable_run_normalized_task_input",
        "mode": "normalized-task-only",
        "issue": issue["number"],
        "risk": normalization["risk"],
        "base_commit": normalization["base_commit"],
        "source": {
            "kind": "human_normalized_input",
            "reference": (
                f"approved-github-issue-snapshot repository={package['repository']} "
                f"issue={issue['number']} package_sha256={package_sha256}"
            ),
        },
        "task": normalization["task"],
    }
    return initialize_portable_run.validate_input(
        value,
        initialize_portable_run.load_policy(),
    )


def validate_paths(
    repo_root: Path,
    package_path: Path,
    normalized_path: Path,
    receipt_path: Path,
    policy: dict[str, Any],
    existing_outputs: bool,
) -> tuple[Path, Path, Path]:
    if package_path.is_symlink() or not package_path.is_file():
        raise ValueError("Issue package must be an existing regular file")
    package_path = package_path.resolve()
    normalized_path = normalized_path.resolve()
    receipt_path = receipt_path.resolve()
    if normalized_path == receipt_path:
        raise ValueError("Normalized input and approval receipt paths must differ")
    if normalized_path.is_symlink() or receipt_path.is_symlink():
        raise ValueError("Issue-ingestion output symbolic links are not allowed")
    if policy["require_external_package"] and build_stage_context.is_within(
        package_path,
        repo_root,
    ):
        raise ValueError("Issue package must be outside the Git checkout")
    if policy["require_external_normalized_input"] and build_stage_context.is_within(
        normalized_path,
        repo_root,
    ):
        raise ValueError("Normalized task input must be outside the Git checkout")
    if policy["require_external_receipt"] and build_stage_context.is_within(
        receipt_path,
        repo_root,
    ):
        raise ValueError("Issue-ingestion receipt must be outside the Git checkout")
    if existing_outputs:
        if not normalized_path.is_file() or not receipt_path.is_file():
            raise ValueError("Normalized input and receipt must be existing regular files")
    else:
        if policy["require_absent_normalized_input"] and normalized_path.exists():
            raise ValueError("Normalized task input already exists")
        if policy["require_absent_receipt"] and receipt_path.exists():
            raise ValueError("Issue-ingestion receipt already exists")
    if not normalized_path.parent.is_dir() or not receipt_path.parent.is_dir():
        raise ValueError("Issue-ingestion output parents must exist")
    return package_path, normalized_path, receipt_path


def assess(
    repo: Path,
    package_path: Path,
    normalized_path: Path,
    receipt_path: Path,
    approver: str,
    policy: dict[str, Any],
    existing_outputs: bool = False,
) -> dict[str, Any]:
    repo_root = Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()
    package_path, normalized_path, receipt_path = validate_paths(
        repo_root,
        package_path,
        normalized_path,
        receipt_path,
        policy,
        existing_outputs,
    )
    approver = apply_stage_output.validate_reviewer(
        approver,
        policy["max_approver_characters"],
    )
    package_bytes = package_path.read_bytes()
    if len(package_bytes) > policy["max_package_bytes"]:
        raise ValueError("Issue package exceeds max_package_bytes")
    if build_stage_context.detect_secrets(
        [
            build_stage_context.content_record(
                "github-issue-package.json",
                package_bytes.decode("utf-8-sig"),
            ),
            build_stage_context.content_record("approver", approver),
        ],
        diff_policy.load_policy(REPO_ROOT / ".agent" / "policies" / "diff-policy.json"),
    ):
        raise ValueError("Issue package or approver contains a high-confidence secret")
    package = validate_package(json.loads(package_bytes.decode("utf-8-sig")), policy)
    package_sha256 = sha256_bytes(package_bytes)
    normalized = normalized_input(package, package_sha256)
    normalized_bytes = canonical_bytes(normalized)
    if len(normalized_bytes) > initialize_portable_run.load_policy()["max_input_bytes"]:
        raise ValueError("Normalized task input exceeds initialization input limit")
    head = diff_policy.run_git(repo_root, "rev-parse", "HEAD").decode("ascii").strip()
    failures = []
    if policy["require_repo_head_match"] and head != normalized["base_commit"]:
        failures.append(
            {"rule": "repo_head_match", "message": "Repository HEAD differs from package base."}
        )
    status = diff_policy.run_git_with_environment(
        repo_root,
        {"GIT_OPTIONAL_LOCKS": "0"},
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if policy["require_clean_worktree"] and status:
        failures.append({"rule": "clean_worktree", "message": "Repository worktree is not clean."})
    bindings = binding_records(repo_root, policy["bindings"])
    bindings_sha256 = sha256_bytes(canonical_bytes(bindings))
    required_confirmation = (
        f"{policy['confirmation_prefix']} approver={approver} "
        f"repository={package['repository']} issue={normalized['issue']} "
        f"base_commit={normalized['base_commit']} package_sha256={package_sha256} "
        f"normalized_input_sha256={sha256_bytes(normalized_bytes)} "
        f"bindings_sha256={bindings_sha256} normalized_input={normalized_path} "
        f"approval_receipt={receipt_path}"
    )
    return {
        "approvable": not failures,
        "approved": False,
        "normalized_task_input_produced": False,
        **{field: False for field in FALSE_FIELDS},
        "source_state_authenticated": False,
        "github_label_independently_verified": False,
        "approver_authenticated": False,
        "repository": package["repository"],
        "issue": normalized["issue"],
        "risk": normalized["risk"],
        "base_commit": normalized["base_commit"],
        "approver_declaration": approver,
        "package_sha256": package_sha256,
        "normalized_input_sha256": sha256_bytes(normalized_bytes),
        "bindings_sha256": bindings_sha256,
        "normalized_input": str(normalized_path),
        "approval_receipt": str(receipt_path),
        "required_confirmation": required_confirmation,
        "normalized_value": normalized,
        "normalized_bytes": normalized_bytes,
        "bindings": bindings,
        "failures": failures,
    }


def receipt_value(assessment: dict[str, Any], confirmation: str, policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "receipt_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "issue_snapshot_approved": True,
        "normalized_task_input_produced": True,
        "source_state_authenticated": False,
        "github_label_independently_verified": False,
        "approver_authenticated": False,
        "repository": assessment["repository"],
        "issue": assessment["issue"],
        "risk": assessment["risk"],
        "base_commit": assessment["base_commit"],
        "approver_declaration": assessment["approver_declaration"],
        "package_sha256": assessment["package_sha256"],
        "normalized_input_sha256": assessment["normalized_input_sha256"],
        "confirmation_sha256": sha256_bytes(confirmation.encode("utf-8")),
        "normalized_input": assessment["normalized_input"],
        "bindings": assessment["bindings"],
    }


def write_exclusive(path: Path, content: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def approve(args: argparse.Namespace, policy: dict[str, Any]) -> dict[str, Any]:
    assessment = assess(
        args.repo,
        args.package,
        args.normalized_input,
        args.approval_receipt,
        args.approver,
        policy,
    )
    if not assessment["approvable"]:
        return assessment
    if args.confirm != assessment["required_confirmation"]:
        assessment["failures"].append(
            {"rule": "confirmation_mismatch", "message": "Confirmation does not match."}
        )
        assessment["approvable"] = False
        return assessment
    refreshed = assess(
        args.repo,
        args.package,
        args.normalized_input,
        args.approval_receipt,
        args.approver,
        policy,
    )
    if (
        not refreshed["approvable"]
        or args.confirm != refreshed["required_confirmation"]
        or refreshed["package_sha256"] != assessment["package_sha256"]
        or refreshed["normalized_input_sha256"] != assessment["normalized_input_sha256"]
    ):
        refreshed["failures"].append(
            {"rule": "state_changed", "message": "Issue-ingestion state changed before approval."}
        )
        refreshed["approvable"] = False
        return refreshed
    receipt = receipt_value(refreshed, args.confirm, policy)
    receipt_bytes = canonical_bytes(receipt)
    if len(receipt_bytes) > policy["max_receipt_bytes"]:
        raise ValueError("Issue-ingestion receipt exceeds max_receipt_bytes")
    receipt_path = args.approval_receipt.resolve()
    normalized_path = args.normalized_input.resolve()
    receipt_written = False
    normalized_written = False
    try:
        write_exclusive(receipt_path, receipt_bytes)
        receipt_written = True
        write_exclusive(normalized_path, refreshed["normalized_bytes"])
        normalized_written = True
        if (
            receipt_path.read_bytes() != receipt_bytes
            or normalized_path.read_bytes() != refreshed["normalized_bytes"]
        ):
            raise ValueError("Issue-ingestion outputs changed during final verification")
    except (OSError, ValueError):
        if normalized_written and normalized_path.read_bytes() == refreshed["normalized_bytes"]:
            normalized_path.unlink(missing_ok=True)
        if receipt_written and receipt_path.read_bytes() == receipt_bytes:
            receipt_path.unlink(missing_ok=True)
        raise
    refreshed.update(
        approved=True,
        normalized_task_input_produced=True,
        approval_receipt_sha256=sha256_bytes(receipt_bytes),
        approval_receipt_size_bytes=len(receipt_bytes),
    )
    refreshed.pop("normalized_bytes", None)
    return refreshed


def validate(
    repo: Path,
    package_path: Path,
    normalized_path: Path,
    receipt_path: Path,
    receipt_sha256: str,
    policy: dict[str, Any],
) -> dict[str, Any]:
    if SHA256.fullmatch(receipt_sha256) is None:
        raise ValueError("Receipt SHA-256 must be 64 lowercase hexadecimal characters")
    repo_root = Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()
    package_path, normalized_path, receipt_path = validate_paths(
        repo_root,
        package_path,
        normalized_path,
        receipt_path,
        policy,
        existing_outputs=True,
    )
    receipt_bytes = receipt_path.read_bytes()
    if len(receipt_bytes) > policy["max_receipt_bytes"]:
        raise ValueError("Issue-ingestion receipt exceeds max_receipt_bytes")
    if sha256_bytes(receipt_bytes) != receipt_sha256:
        raise ValueError("Issue-ingestion receipt SHA-256 does not match")
    receipt = json.loads(receipt_bytes.decode("utf-8-sig"))
    approver = receipt.get("approver_declaration") if isinstance(receipt, dict) else None
    if type(approver) is not str:
        raise ValueError("Issue-ingestion receipt approver is invalid")
    assessment = assess(
        repo,
        package_path,
        normalized_path,
        receipt_path,
        approver,
        policy,
        existing_outputs=True,
    )
    expected = receipt_value(assessment, assessment["required_confirmation"], policy)
    failures = []
    if receipt != expected:
        failures.append(
            {"rule": "receipt_mismatch", "message": "Receipt differs from current exact evidence."}
        )
    if normalized_path.read_bytes() != assessment["normalized_bytes"]:
        failures.append(
            {
                "rule": "normalized_input_mismatch",
                "message": "Normalized input differs from current exact evidence.",
            }
        )
    return {
        "valid": not failures and assessment["approvable"],
        **{field: False for field in FALSE_FIELDS},
        "issue_snapshot_approved": not failures and assessment["approvable"],
        "normalized_task_input_produced": not failures and assessment["approvable"],
        "source_state_authenticated": False,
        "github_label_independently_verified": False,
        "approver_authenticated": False,
        "repository": assessment["repository"],
        "issue": assessment["issue"],
        "package_sha256": assessment["package_sha256"],
        "normalized_input_sha256": assessment["normalized_input_sha256"],
        "approval_receipt_sha256": receipt_sha256,
        "failures": assessment["failures"] + failures,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("check", "approve", "validate"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--repo", type=Path, required=True)
        subparser.add_argument("--package", type=Path, required=True)
        subparser.add_argument("--normalized-input", type=Path, required=True)
        subparser.add_argument("--approval-receipt", type=Path, required=True)
        if command in {"check", "approve"}:
            subparser.add_argument("--approver", required=True)
        if command == "approve":
            subparser.add_argument("--confirm", required=True)
        if command == "validate":
            subparser.add_argument("--approval-receipt-sha256", required=True)
        subparser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def serializable(result: dict[str, Any]) -> dict[str, Any]:
    value = dict(result)
    value.pop("normalized_bytes", None)
    return value


def format_text(result: dict[str, Any]) -> str:
    if "valid" in result:
        status = "VALID" if result["valid"] else "INVALID"
    elif result.get("approved"):
        status = "APPROVED"
    else:
        status = "APPROVABLE" if result.get("approvable") else "BLOCKED"
    return "\n".join(
        [
            f"github-issue-ingestion: {status}",
            f"issue={result.get('issue')}",
            "source_state_authenticated=false",
            "agent_invocation_authorized=false",
        ]
    )


def main() -> int:
    args = build_parser().parse_args()
    try:
        policy = load_policy()
        if args.command == "check":
            result = assess(
                args.repo,
                args.package,
                args.normalized_input,
                args.approval_receipt,
                args.approver,
                policy,
            )
            success = result["approvable"]
        elif args.command == "approve":
            result = approve(args, policy)
            success = result["approved"]
        else:
            result = validate(
                args.repo,
                args.package,
                args.normalized_input,
                args.approval_receipt,
                args.approval_receipt_sha256,
                policy,
            )
            success = result["valid"]
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"github-issue-ingestion: ERROR\n- {error}", file=sys.stderr)
        return 1
    output = serializable(result)
    if args.format == "json":
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        print(format_text(output))
    return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(main())
