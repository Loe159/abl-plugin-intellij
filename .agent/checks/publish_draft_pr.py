#!/usr/bin/env python3
"""Publish a validated implementation patch as a draft PR when explicitly requested."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import build_stage_context
import diff_policy
import initialize_portable_run
import validate_implementation_quality_gate
import validate_implementation_result
import validate_implementation_patch


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "draft-pr-publisher.json"
BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,119}")
FALSE_FIELDS = (
    "authorized",
    "agent_invocation_authorized",
    "implementation_authorized",
    "merge_authorized",
    "release_authorized",
)
EXTERNAL_WRITE_FIELDS = (
    "repository_mutation_authorized",
    "network_authorized",
    "publication_authorized",
    "publication_requested",
    "branch_pushed",
    "draft_pr_created",
    "external_service_written",
)

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "deterministic_draft_pr_publisher",
    "mode": "explicit-requested-external-publication",
    "default_dry_run": True,
    "require_execute_flag_for_external_writes": True,
    "require_draft_pr": True,
    "require_quality_gate_receipt_valid": True,
    "require_quality_gate_passed": True,
    "require_external_outputs": True,
    "require_outputs_outside_workspace": True,
    "require_absent_outputs": True,
    "require_distinct_outputs": True,
    "allowed_branch_prefixes": ["codex/"],
    "max_title_chars": 160,
    "max_body_chars": 12000,
    "command_timeout_seconds": 60.0,
    "max_captured_output_bytes": 20000,
    "bindings": [
        ".agent/checks/publish_draft_pr.py",
        ".agent/policies/draft-pr-publisher.json",
        ".agent/checks/validate_implementation_quality_gate.py",
        ".agent/policies/implementation-quality-gate-validation.json",
        "docs/agent-guides/draft-pr-publication-readiness.md",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Draft-PR publisher policy does not match")
    return policy


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True, separators=(",", ": ")).encode(
        "utf-8"
    ) + b"\n"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_exclusive(path: Path, content: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(content)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def failure(rule: str, message: str) -> dict[str, str]:
    return {"rule": rule, "message": message}


def source_root(repo: Path) -> Path:
    return Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel")
        .decode("utf-8")
        .strip()
    ).resolve()


def validate_branch(name: str, policy: dict[str, Any]) -> str:
    if (
        BRANCH.fullmatch(name) is None
        or ".." in name
        or "//" in name
        or name.endswith(("/", ".", ".lock"))
        or not any(name.startswith(prefix) for prefix in policy["allowed_branch_prefixes"])
    ):
        raise ValueError("Draft PR branch name is not allowed")
    return name


def validate_output_path(
    path: Path,
    source_checkout: Path,
    workspace: Path,
    label: str,
    policy: dict[str, Any],
) -> Path:
    if path.is_symlink():
        raise ValueError(f"{label} output must not be a symbolic link")
    parent = path.parent.resolve()
    if not parent.is_dir():
        raise ValueError(f"{label} output parent does not exist")
    resolved = (parent / path.name).resolve()
    if "\n" in str(resolved) or "\r" in str(resolved):
        raise ValueError(f"{label} output path must not contain line breaks")
    if policy["require_external_outputs"] and build_stage_context.is_within(
        resolved,
        source_checkout,
    ):
        raise ValueError(f"{label} output must be outside the source checkout")
    if policy["require_outputs_outside_workspace"] and build_stage_context.is_within(
        resolved,
        workspace,
    ):
        raise ValueError(f"{label} output must be outside the implementation workspace")
    if policy["require_absent_outputs"] and resolved.exists():
        raise ValueError(f"{label} output already exists")
    return resolved


def validate_outputs(
    source_checkout: Path,
    workspace: Path,
    body_output: Path,
    receipt_output: Path,
    policy: dict[str, Any],
) -> tuple[Path, Path]:
    outputs = (
        validate_output_path(body_output, source_checkout, workspace, "PR body", policy),
        validate_output_path(receipt_output, source_checkout, workspace, "Publication receipt", policy),
    )
    if policy["require_distinct_outputs"] and outputs[0] == outputs[1]:
        raise ValueError("Publication output paths must be distinct")
    return outputs


def command_record(argv: Sequence[str], status: str = "planned") -> dict[str, Any]:
    return {
        "argv": list(argv),
        "status": status,
        "returncode": None,
        "stdout_bytes": 0,
        "stderr_bytes": 0,
        "stdout_sha256": None,
        "stderr_sha256": None,
    }


def run_command(
    argv: Sequence[str],
    cwd: Path,
    timeout_seconds: float,
    max_output_bytes: int,
) -> dict[str, Any]:
    completed = subprocess.run(
        list(argv),
        cwd=cwd,
        check=False,
        capture_output=True,
        timeout=timeout_seconds,
    )
    stdout = completed.stdout[:max_output_bytes]
    stderr = completed.stderr[:max_output_bytes]
    return {
        "argv": list(argv),
        "status": "passed" if completed.returncode == 0 else "failed",
        "returncode": completed.returncode,
        "stdout_bytes": len(stdout),
        "stderr_bytes": len(stderr),
        "stdout_sha256": sha256_bytes(stdout),
        "stderr_sha256": sha256_bytes(stderr),
    }


def pr_body(
    title: str,
    summary: str,
    quality_gate_sha256: str,
    patch_sha256: str,
    patch_receipt_sha256: str,
) -> str:
    body = "\n".join(
        [
            title,
            "",
            "Summary:",
            summary,
            "",
            "Deterministic evidence:",
            f"- patch_sha256: {patch_sha256}",
            f"- patch_receipt_sha256: {patch_receipt_sha256}",
            f"- quality_gate_receipt_sha256: {quality_gate_sha256}",
            "",
            "This PR is created as draft for human review.",
            "",
        ]
    )
    return body


def planned_commands(
    branch: str,
    base_commit: str,
    remote: str,
    base_branch: str,
    title: str,
    body_output: Path,
) -> list[list[str]]:
    return [
        ["git", "checkout", "-B", branch, base_commit],
        ["git", "add", "-A"],
        ["git", "commit", "-m", title],
        ["git", "push", "--set-upstream", remote, branch],
        [
            "gh",
            "pr",
            "create",
            "--draft",
            "--base",
            base_branch,
            "--head",
            branch,
            "--title",
            title,
            "--body-file",
            str(body_output),
        ],
    ]


def base_result(receipt_output: Path, execute: bool) -> dict[str, Any]:
    publication_requested = bool(execute)
    return {
        "publisher_complete": False,
        "dry_run": not execute,
        "receipt_written": False,
        "receipt": str(receipt_output),
        "receipt_sha256": None,
        **{field: False for field in FALSE_FIELDS},
        **{field: False for field in EXTERNAL_WRITE_FIELDS},
        "repository_mutation_authorized": publication_requested,
        "network_authorized": publication_requested,
        "publication_authorized": publication_requested,
        "publication_requested": publication_requested,
        "quality_gate_receipt_valid": False,
        "quality_gate_passed": False,
        "issue": None,
        "base_commit": None,
        "workspace": None,
        "branch": None,
        "base_branch": None,
        "title": None,
        "body_output": None,
        "body_sha256": None,
        "patch_sha256": None,
        "patch_receipt_sha256": None,
        "quality_gate_receipt_sha256": None,
        "commands": [],
        "failures": [],
    }


def receipt_value(result: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "publication_receipt_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: result[field] for field in FALSE_FIELDS},
        **{field: result[field] for field in EXTERNAL_WRITE_FIELDS},
        "publisher_complete": result["publisher_complete"],
        "dry_run": result["dry_run"],
        "quality_gate_receipt_valid": result["quality_gate_receipt_valid"],
        "quality_gate_passed": result["quality_gate_passed"],
        "issue": result["issue"],
        "base_commit": result["base_commit"],
        "workspace": result["workspace"],
        "branch": result["branch"],
        "base_branch": result["base_branch"],
        "title": result["title"],
        "body_output": result["body_output"],
        "body_sha256": result["body_sha256"],
        "patch_sha256": result["patch_sha256"],
        "patch_receipt_sha256": result["patch_receipt_sha256"],
        "quality_gate_receipt_sha256": result["quality_gate_receipt_sha256"],
        "commands": result["commands"],
        "failures": result["failures"],
        "bindings": initialize_portable_run.binding_records(policy["bindings"]),
    }


def write_receipt(result: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    receipt = Path(result["receipt"])
    content = canonical_bytes(receipt_value(result, policy))
    write_exclusive(receipt, content)
    result.update(receipt_written=True, receipt_sha256=sha256_bytes(content))
    return result


def publish(
    repo: Path,
    result_path: Path,
    expected_session_path: Path,
    patch: Path,
    patch_receipt: Path,
    patch_receipt_sha256: str,
    quality_gate_receipt: Path,
    quality_gate_receipt_sha256: str,
    gradle_user_home: Path,
    branch: str,
    title: str,
    summary: str,
    body_output: Path,
    receipt_output: Path,
    base_branch: str,
    remote: str,
    execute: bool,
    policy: dict[str, Any],
    quality_gate_validator: Callable[..., dict[str, Any]] = (
        validate_implementation_quality_gate.validate
    ),
    command_runner: Callable[[Sequence[str], Path, float, int], dict[str, Any]] = run_command,
) -> dict[str, Any]:
    source_checkout = source_root(repo)
    expected_session = validate_implementation_result.validate_expected_session(
        json.loads(expected_session_path.read_text(encoding="utf-8-sig"))
    )
    workspace = Path(expected_session["workspace"]).resolve()
    body_output, receipt_output = validate_outputs(
        source_checkout,
        workspace,
        body_output,
        receipt_output,
        policy,
    )
    branch = validate_branch(branch, policy)
    if len(title) > policy["max_title_chars"] or not title.strip():
        raise ValueError("Draft PR title is empty or too long")
    if len(summary) > policy["max_body_chars"]:
        raise ValueError("Draft PR summary is too long")
    result = base_result(receipt_output, execute)
    result.update(
        issue=expected_session["issue"],
        base_commit=expected_session["base_commit"],
        workspace=expected_session["workspace"],
        branch=branch,
        base_branch=base_branch,
        title=title,
        patch_sha256=sha256_file(patch),
        patch_receipt_sha256=patch_receipt_sha256,
        quality_gate_receipt_sha256=quality_gate_receipt_sha256,
    )

    quality_validation = quality_gate_validator(
        source_checkout,
        result_path,
        expected_session_path,
        patch,
        patch_receipt,
        patch_receipt_sha256,
        quality_gate_receipt,
        quality_gate_receipt_sha256,
        gradle_user_home,
        validate_implementation_quality_gate.load_policy(),
    )
    result["quality_gate_receipt_valid"] = quality_validation.get("valid") is True
    result["quality_gate_passed"] = quality_validation.get("quality_gate_passed") is True
    if policy["require_quality_gate_receipt_valid"] and not result["quality_gate_receipt_valid"]:
        result["failures"].append(
            failure("quality_gate_receipt", "Quality-gate receipt is not valid.")
        )
    if policy["require_quality_gate_passed"] and not result["quality_gate_passed"]:
        result["failures"].append(
            failure("quality_gate", "Quality gate did not pass.")
        )

    body = pr_body(
        title,
        summary,
        quality_gate_receipt_sha256,
        result["patch_sha256"],
        patch_receipt_sha256,
    )
    if len(body) > policy["max_body_chars"]:
        raise ValueError("Draft PR body is too long")
    body_bytes = body.encode("utf-8")
    write_exclusive(body_output, body_bytes)
    result.update(
        body_output=str(body_output),
        body_sha256=sha256_bytes(body_bytes),
    )

    commands = planned_commands(
        branch,
        expected_session["base_commit"],
        remote,
        base_branch,
        title,
        body_output,
    )
    if result["failures"]:
        result["commands"] = [command_record(command, "blocked") for command in commands]
        return write_receipt(result, policy)
    if not execute:
        result["commands"] = [command_record(command) for command in commands]
        result["publisher_complete"] = True
        return write_receipt(result, policy)

    records = []
    for command in commands:
        record = command_runner(
            command,
            workspace,
            policy["command_timeout_seconds"],
            policy["max_captured_output_bytes"],
        )
        records.append(record)
        if record["status"] != "passed":
            result["failures"].append(
                failure("publication_command", f"Publication command failed: {command[0]}")
            )
            break
    result["commands"] = records + [
        command_record(command, "not_run") for command in commands[len(records) :]
    ]
    branch_pushed = len(records) >= 4 and records[3]["status"] == "passed"
    draft_pr_created = len(records) >= 5 and records[4]["status"] == "passed"
    result["branch_pushed"] = branch_pushed
    result["draft_pr_created"] = draft_pr_created
    result["external_service_written"] = branch_pushed or draft_pr_created
    result["publisher_complete"] = not result["failures"] and draft_pr_created
    return write_receipt(result, policy)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--expected-session", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--patch-receipt", type=Path, required=True)
    parser.add_argument("--patch-receipt-sha256", required=True)
    parser.add_argument("--quality-gate-receipt", type=Path, required=True)
    parser.add_argument("--quality-gate-receipt-sha256", required=True)
    parser.add_argument("--gradle-user-home", type=Path, required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--summary", default="")
    parser.add_argument("--body-output", type=Path, required=True)
    parser.add_argument("--receipt-output", type=Path, required=True)
    parser.add_argument("--base-branch", default="main")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "COMPLETE" if result["publisher_complete"] else "BLOCKED"
    lines = [
        f"draft-pr-publisher: {status}",
        f"dry_run={str(result['dry_run']).lower()}",
        f"draft_pr_created={str(result['draft_pr_created']).lower()}",
        f"receipt_written={str(result['receipt_written']).lower()}",
    ]
    lines.extend(f"- {item['rule']}: {item['message']}" for item in result["failures"])
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = publish(
            args.repo,
            args.result,
            args.expected_session,
            args.patch,
            args.patch_receipt,
            args.patch_receipt_sha256,
            args.quality_gate_receipt,
            args.quality_gate_receipt_sha256,
            args.gradle_user_home,
            args.branch,
            args.title,
            args.summary,
            args.body_output,
            args.receipt_output,
            args.base_branch,
            args.remote,
            args.execute,
            load_policy(),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"draft-pr-publisher: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["publisher_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
