#!/usr/bin/env python3
"""Validate one exact approved portable task without authorizing a stage."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import apply_stage_output
import approve_task
import build_stage_context
import check_stage_readiness
import diff_policy
import initialize_portable_run
import validate_artifacts


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "task-approval-validation.json"
SHA256 = re.compile(r"[0-9a-f]{64}")
APPROVED_STATUS_LINE = re.compile(rb"(?m)^status: approved(\r?)$")
FRONTMATTER_DELIMITER = re.compile(rb"(?m)^---\r?$")
FALSE_FIELDS = initialize_portable_run.FALSE_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "portable_task_approval_validation",
    "mode": "validation-only",
    "require_external_run": True,
    "require_external_approval_receipt": True,
    "require_approval_receipt_outside_run": True,
    "require_clean_worktree": True,
    "require_repo_head_match": True,
    "validator_bindings": [
        ".agent/checks/validate_task_approval.py",
        ".agent/policies/task-approval-validation.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Task-approval-validation policy does not match the contract")
    return policy


def load_policies() -> dict[str, Any]:
    return {
        **approve_task.load_policies(),
        "approval_validation": load_policy(),
    }


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def failure(rule: str, message: str) -> dict[str, str]:
    return {"rule": rule, "message": message}


def base_result(expected_sha256: str) -> dict[str, Any]:
    return {
        "valid": False,
        **{field: False for field in FALSE_FIELDS},
        "task_approved": False,
        "research_ready": False,
        "approval_receipt_sha256": expected_sha256,
        "initialization_receipt_sha256": None,
        "approver_declaration": None,
        "issue": None,
        "risk": None,
        "base_commit": None,
        "pre_approval_run_snapshot_sha256": None,
        "post_approval_run_snapshot_sha256": None,
        "pre_task_sha256": None,
        "post_task_sha256": None,
        "failures": [],
    }


def exact_equal(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(actual) == set(expected) and all(
            exact_equal(actual[key], value) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            exact_equal(actual_item, expected_item)
            for actual_item, expected_item in zip(actual, expected, strict=True)
        )
    return actual == expected


def valid_sha256(value: Any) -> bool:
    return type(value) is str and SHA256.fullmatch(value) is not None


def approval_bindings(policy: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    records = initialize_portable_run.binding_records(policy["bindings"])
    content = (json.dumps(records, sort_keys=True) + "\n").encode("utf-8")
    return records, sha256_bytes(content)


def snapshot_with_task(run: Path, artifact_names: list[str], task_bytes: bytes) -> str:
    snapshot = b"".join(
        name.encode("utf-8")
        + b"\0"
        + sha256_bytes(task_bytes if name == "task.md" else (run / name).read_bytes()).encode(
            "ascii"
        )
        + b"\n"
        for name in sorted(artifact_names)
    )
    return sha256_bytes(snapshot)


def awaiting_task_bytes(task_bytes: bytes) -> bytes:
    opening_end = task_bytes.find(b"\n") + 1
    closing = FRONTMATTER_DELIMITER.search(task_bytes, opening_end)
    if opening_end == 0 or closing is None:
        raise ValueError("Task frontmatter delimiters do not match the contract")
    matches = [
        match
        for match in APPROVED_STATUS_LINE.finditer(task_bytes)
        if match.start() < closing.start()
    ]
    if len(matches) != 1:
        raise ValueError("Task frontmatter must contain exactly one approved status line")
    match = matches[0]
    replacement = b"status: awaiting_approval" + match.group(1)
    return task_bytes[: match.start()] + replacement + task_bytes[match.end() :]


def validate_receipt_value(
    value: Any,
    run: Path,
    approval_receipt: Path,
    artifacts: dict[str, validate_artifacts.Artifact],
    policies: dict[str, Any],
) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    expected_fields = {
        "task_approval_receipt_version",
        "purpose",
        "mode",
        *FALSE_FIELDS,
        "task_approved",
        "research_ready",
        "approver_declaration",
        "issue",
        "risk",
        "base_commit",
        "run",
        "initialization_receipt_sha256",
        "confirmation_sha256",
        "pre_approval_run_snapshot_sha256",
        "post_approval_run_snapshot_sha256",
        "pre_task_sha256",
        "post_task_sha256",
        "bindings",
    }
    if not isinstance(value, dict) or set(value) != expected_fields:
        return [failure("receipt_schema", "Task-approval receipt fields do not match.")]
    approval = policies["approval"]
    if (
        type(value["task_approval_receipt_version"]) is not int
        or value["task_approval_receipt_version"] != approval["version"]
        or value["purpose"] != approval["purpose"]
        or value["mode"] != approval["mode"]
        or value["task_approved"] is not True
        or value["research_ready"] is not True
        or any(value[field] is not False for field in FALSE_FIELDS)
    ):
        failures.append(failure("receipt_metadata", "Task-approval receipt state does not match."))
    task = artifacts["task.md"].frontmatter
    approver = value["approver_declaration"]
    if (
        type(approver) is not str
        or not approver.strip()
        or len(approver) > approval["max_approver_chars"]
        or value["issue"] != int(task["issue"])
        or value["risk"] != task["risk"]
        or value["base_commit"] != task["base_commit"]
        or value["run"] != str(run)
        or not valid_sha256(value["initialization_receipt_sha256"])
    ):
        failures.append(failure("receipt_identity", "Receipt identity does not match the run."))
    digest_fields = (
        "confirmation_sha256",
        "pre_approval_run_snapshot_sha256",
        "post_approval_run_snapshot_sha256",
        "pre_task_sha256",
        "post_task_sha256",
    )
    if any(not valid_sha256(value[field]) for field in digest_fields):
        failures.append(failure("receipt_digest", "Receipt digest fields are not valid SHA-256."))
        return failures
    if task["status"] != approval["approved_status"]:
        failures.append(failure("approved_state", "Current task status is not approved."))
        return failures
    task_bytes = run.joinpath("task.md").read_bytes()
    pre_task = awaiting_task_bytes(task_bytes)
    artifact_names = list(policies["artifact"]["artifacts"])
    pre_snapshot = snapshot_with_task(run, artifact_names, pre_task)
    post_snapshot = apply_stage_output.run_snapshot_sha256(run, artifact_names)
    bindings, bindings_sha256 = approval_bindings(approval)
    confirmation = (
        f"{approval['confirmation_prefix']} approver={approver} issue={value['issue']} "
        f"risk={value['risk']} base_commit={value['base_commit']} "
        f"receipt_sha256={value['initialization_receipt_sha256']} "
        f"run_snapshot_sha256={pre_snapshot} task_sha256={sha256_bytes(pre_task)} "
        f"post_run_snapshot_sha256={post_snapshot} post_task_sha256={sha256_bytes(task_bytes)} "
        f"approval_bindings_sha256={bindings_sha256} approval_receipt={approval_receipt}"
    )
    expected_hashes = {
        "confirmation_sha256": sha256_bytes(confirmation.encode("utf-8")),
        "pre_approval_run_snapshot_sha256": pre_snapshot,
        "post_approval_run_snapshot_sha256": post_snapshot,
        "pre_task_sha256": sha256_bytes(pre_task),
        "post_task_sha256": sha256_bytes(task_bytes),
    }
    if any(value[name] != digest for name, digest in expected_hashes.items()):
        failures.append(
            failure("transition_mismatch", "Receipt does not match the exact task transition.")
        )
    if not exact_equal(value["bindings"], bindings):
        failures.append(
            failure("trusted_binding_mismatch", "Receipt bindings differ from trusted bytes.")
        )
    return failures


def validate(
    repo: Path,
    run: Path,
    approval_receipt: Path,
    expected_sha256: str,
    policies: dict[str, Any],
) -> dict[str, Any]:
    result = base_result(expected_sha256)
    if SHA256.fullmatch(expected_sha256) is None:
        raise ValueError("Expected receipt SHA-256 must be 64 lowercase hexadecimal characters")
    if repo.is_symlink() or run.is_symlink() or approval_receipt.is_symlink():
        raise ValueError(
            "Repository, run, and task-approval receipt symbolic links are not allowed"
        )
    repo_root = Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()
    run = run.resolve()
    approval_receipt = approval_receipt.resolve()
    if "\n" in str(approval_receipt) or "\r" in str(approval_receipt):
        raise ValueError("Task-approval receipt path must not contain line breaks")
    policy = policies["approval_validation"]
    if not run.is_dir() or not approval_receipt.is_file():
        raise ValueError("Run and task-approval receipt must exist")
    if policy["require_external_run"] and build_stage_context.is_within(run, repo_root):
        raise ValueError("Portable run must be outside the Git checkout")
    if policy["require_external_approval_receipt"] and build_stage_context.is_within(
        approval_receipt,
        repo_root,
    ):
        raise ValueError("Task-approval receipt must be outside the Git checkout")
    if policy["require_approval_receipt_outside_run"] and build_stage_context.is_within(
        approval_receipt,
        run,
    ):
        raise ValueError("Task-approval receipt must be outside the portable run")
    artifact_names = list(policies["artifact"]["artifacts"])
    if any((run / name).is_symlink() for name in artifact_names):
        raise ValueError("Run artifact symbolic links are not allowed")
    contract = validate_artifacts.validate_directory(run, policies["artifact"], False)
    if not contract["valid"]:
        result["failures"].append(failure("run_contract", "Run does not satisfy the contract."))
        return result
    receipt_bytes = approval_receipt.read_bytes()
    if len(receipt_bytes) > policies["approval"]["max_approval_receipt_bytes"]:
        result["failures"].append(failure("max_receipt_bytes", "Receipt exceeds the byte limit."))
        return result
    if sha256_bytes(receipt_bytes) != expected_sha256:
        result["failures"].append(
            failure("receipt_sha256", "Receipt does not match its expected SHA-256.")
        )
        return result
    artifacts = {name: validate_artifacts.parse_artifact(run / name) for name in artifact_names}
    value = json.loads(receipt_bytes.decode("utf-8-sig"))
    result["failures"].extend(
        validate_receipt_value(value, run, approval_receipt, artifacts, policies)
    )
    if not isinstance(value, dict):
        return result
    task = artifacts["task.md"]
    result.update(
        task_approved=task.frontmatter["status"] == policies["approval"]["approved_status"],
        approver_declaration=value.get("approver_declaration"),
        initialization_receipt_sha256=value.get("initialization_receipt_sha256"),
        issue=int(task.frontmatter["issue"]),
        risk=task.frontmatter["risk"],
        base_commit=task.frontmatter["base_commit"],
        pre_approval_run_snapshot_sha256=value.get("pre_approval_run_snapshot_sha256"),
        post_approval_run_snapshot_sha256=apply_stage_output.run_snapshot_sha256(
            run,
            artifact_names,
        ),
        pre_task_sha256=value.get("pre_task_sha256"),
        post_task_sha256=sha256_bytes((run / "task.md").read_bytes()),
    )
    readiness = check_stage_readiness.check_readiness(
        run,
        policies["approval"]["readiness_stage"],
        policies["artifact"],
        policies["readiness"],
    )
    result["research_ready"] = readiness["ready"]
    if not result["task_approved"] or not result["research_ready"]:
        result["failures"].append(
            failure("approved_state", "Current task is not approved and research-ready.")
        )
    secrets = build_stage_context.detect_secrets(
        [
            build_stage_context.content_record(name, (run / name).read_text(encoding="utf-8-sig"))
            for name in artifact_names
        ]
        + [
            build_stage_context.content_record(
                "approver",
                str(result["approver_declaration"] or ""),
            )
        ],
        policies["diff"],
    )
    if secrets:
        result["approver_declaration"] = None
        result["failures"].append(
            failure(
                "high_confidence_secret",
                "Run or approver declaration contains a high-confidence secret signature.",
            )
        )
    head = diff_policy.run_git(repo_root, "rev-parse", "HEAD").decode("ascii").strip()
    status = diff_policy.run_git_with_environment(
        repo_root,
        {"GIT_OPTIONAL_LOCKS": "0"},
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if policy["require_repo_head_match"] and head != result["base_commit"]:
        result["failures"].append(failure("repo_head_match", "Repository HEAD differs from base."))
    if policy["require_clean_worktree"] and status:
        result["failures"].append(failure("clean_worktree", "Repository worktree must be clean."))
    if result["failures"]:
        return result
    validator_bindings = initialize_portable_run.binding_records(policy["validator_bindings"])
    refreshed_bindings = initialize_portable_run.binding_records(policy["validator_bindings"])
    if (
        approval_receipt.read_bytes() != receipt_bytes
        or apply_stage_output.run_snapshot_sha256(run, artifact_names)
        != result["post_approval_run_snapshot_sha256"]
        or diff_policy.run_git(repo_root, "rev-parse", "HEAD").decode("ascii").strip() != head
        or diff_policy.run_git_with_environment(
            repo_root,
            {"GIT_OPTIONAL_LOCKS": "0"},
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )
        != status
        or not exact_equal(refreshed_bindings, validator_bindings)
    ):
        result["failures"].append(
            failure("state_changed", "Receipt, run, repository, or validator changed.")
        )
        return result
    result.update(valid=True, validator_bindings=validator_bindings)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--approval-receipt", type=Path, required=True)
    parser.add_argument("--approval-receipt-sha256", required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "VALID" if result["valid"] else "INVALID"
    lines = [
        f"task-approval-validation: {status}",
        f"task_approved={str(result['task_approved']).lower()}",
        f"research_ready={str(result['research_ready']).lower()}",
        "authorized=false",
    ]
    lines.extend(f"- {item['rule']}: {item['message']}" for item in result["failures"])
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = validate(
            args.repo,
            args.run,
            args.approval_receipt,
            args.approval_receipt_sha256,
            load_policies(),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"task-approval-validation: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
