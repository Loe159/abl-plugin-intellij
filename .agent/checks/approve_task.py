#!/usr/bin/env python3
"""Check and explicitly approve one exact initialized portable task."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

import apply_stage_output
import build_stage_context
import check_stage_readiness
import diff_policy
import initialize_portable_run
import validate_artifacts
import validate_portable_run_initialization


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_DIR = REPO_ROOT / ".agent" / "policies"
POLICY_PATH = POLICY_DIR / "task-approval.json"
STATUS_LINE = re.compile(rb"(?m)^status: awaiting_approval(\r?)$")
FALSE_FIELDS = initialize_portable_run.FALSE_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "portable_task_approval",
    "mode": "exact-local-approval-only",
    "confirmation_prefix": "APPROVE-EXACT-TASK",
    "max_approver_chars": 100,
    "max_approval_receipt_bytes": 30000,
    "require_external_run": True,
    "require_external_receipt": True,
    "require_receipt_outside_run": True,
    "require_external_approval_receipt": True,
    "require_approval_receipt_outside_run": True,
    "require_absent_approval_receipt": True,
    "require_clean_worktree": True,
    "require_repo_head_match": True,
    "current_status": "awaiting_approval",
    "approved_status": "approved",
    "readiness_stage": "research",
    "bindings": [
        ".agent/checks/approve_task.py",
        ".agent/checks/apply_stage_output.py",
        ".agent/checks/build_stage_context.py",
        ".agent/checks/check_stage_readiness.py",
        ".agent/checks/diff_policy.py",
        ".agent/checks/initialize_portable_run.py",
        ".agent/checks/validate_artifacts.py",
        ".agent/checks/validate_disposable_worktree.py",
        ".agent/checks/validate_portable_run_initialization.py",
        ".agent/policies/task-approval.json",
        ".agent/policies/portable-run-initialization.json",
        ".agent/policies/artifact-contract.json",
        ".agent/policies/diff-policy.json",
        ".agent/policies/stage-readiness.json",
        ".agent/policies/portable-run-initialization-validation.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Task-approval policy does not match the pilot contract")
    return policy


def load_policies() -> dict[str, Any]:
    initialization = validate_portable_run_initialization.load_policies()
    return {
        **initialization,
        "approval": load_policy(),
    }


def failure(rule: str, message: str) -> dict[str, str]:
    return {"rule": rule, "message": message}


def base_result() -> dict[str, Any]:
    return {
        "approvable": False,
        "task_approved": False,
        "run_mutated": False,
        **{field: False for field in FALSE_FIELDS},
        "research_ready": False,
        "approver_declaration": None,
        "issue": None,
        "risk": None,
        "base_commit": None,
        "receipt_sha256": None,
        "run_snapshot_sha256": None,
        "task_sha256": None,
        "approval_bindings_sha256": None,
        "approval_receipt": None,
        "approval_receipt_sha256": None,
        "approval_receipt_size_bytes": None,
        "pre_approval_run_snapshot_sha256": None,
        "post_approval_run_snapshot_sha256": None,
        "pre_task_sha256": None,
        "post_task_sha256": None,
        "receipt_written": False,
        "rollback_attempted": False,
        "rollback_succeeded": False,
        "required_confirmation": None,
        "failures": [],
    }


def approval_bindings(policy: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    records = initialize_portable_run.binding_records(policy["bindings"])
    content = (json.dumps(records, sort_keys=True) + "\n").encode("utf-8")
    return records, hashlib.sha256(content).hexdigest()


def snapshot_with_task(run: Path, artifact_names: list[str], task_bytes: bytes) -> str:
    snapshot = b"".join(
        name.encode("utf-8")
        + b"\0"
        + apply_stage_output.sha256_bytes(
            task_bytes if name == "task.md" else (run / name).read_bytes()
        ).encode("ascii")
        + b"\n"
        for name in sorted(artifact_names)
    )
    return apply_stage_output.sha256_bytes(snapshot)


def assess_approval(
    repo: Path,
    run: Path,
    receipt: Path,
    receipt_sha256: str,
    approval_receipt: Path,
    approver: str,
    policies: dict[str, Any],
) -> dict[str, Any]:
    result = base_result()
    approval = policies["approval"]
    approver = apply_stage_output.validate_reviewer(approver, approval["max_approver_chars"])
    if build_stage_context.detect_secrets(
        [build_stage_context.content_record("approver", approver)],
        policies["diff"],
    ):
        raise ValueError("Approver declaration contains a high-confidence secret signature")
    validation = validate_portable_run_initialization.validate(
        repo,
        run,
        receipt,
        receipt_sha256,
        policies,
    )
    if not validation["valid"]:
        result["failures"].append(
            failure("initialization_validation", "Initialized run receipt is not valid.")
        )
        result["failures"].extend(validation["failures"])
        return result
    repo_root = Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()
    run = run.resolve()
    approval_receipt = approval_receipt.resolve()
    if "\n" in str(approval_receipt) or "\r" in str(approval_receipt):
        raise ValueError("Task-approval receipt path must not contain line breaks")
    if approval_receipt.is_symlink():
        raise ValueError("Task-approval receipt symbolic links are not allowed")
    if approval["require_external_approval_receipt"] and build_stage_context.is_within(
        approval_receipt,
        repo_root,
    ):
        raise ValueError("Task-approval receipt must be outside the Git checkout")
    if approval["require_approval_receipt_outside_run"] and build_stage_context.is_within(
        approval_receipt,
        run,
    ):
        raise ValueError("Task-approval receipt must be outside the portable run")
    if approval["require_absent_approval_receipt"] and approval_receipt.exists():
        raise ValueError("Task-approval receipt already exists")
    if not approval_receipt.parent.is_dir():
        raise ValueError("Task-approval receipt parent must be an existing directory")
    artifact_names = list(policies["artifact"]["artifacts"])
    artifacts = {name: validate_artifacts.parse_artifact(run / name) for name in artifact_names}
    task = artifacts["task.md"]
    task_bytes = (run / "task.md").read_bytes()
    if task.frontmatter["status"] != approval["current_status"]:
        result["failures"].append(
            failure("current_status", "Task status is not awaiting_approval.")
        )
        return result
    candidate_task = approved_task_bytes(task_bytes)
    pre_snapshot = validation["run_snapshot_sha256"]
    post_snapshot = snapshot_with_task(run, artifact_names, candidate_task)
    pre_task_sha256 = apply_stage_output.sha256_bytes(task_bytes)
    post_task_sha256 = apply_stage_output.sha256_bytes(candidate_task)
    result.update(
        approver_declaration=approver,
        issue=int(task.frontmatter["issue"]),
        risk=task.frontmatter["risk"],
        base_commit=task.frontmatter["base_commit"],
        receipt_sha256=receipt_sha256,
        run_snapshot_sha256=pre_snapshot,
        task_sha256=pre_task_sha256,
        approval_receipt=str(approval_receipt),
        pre_approval_run_snapshot_sha256=pre_snapshot,
        post_approval_run_snapshot_sha256=post_snapshot,
        pre_task_sha256=pre_task_sha256,
        post_task_sha256=post_task_sha256,
    )
    _, bindings_sha256 = approval_bindings(approval)
    result["approval_bindings_sha256"] = bindings_sha256
    result["required_confirmation"] = (
        f"{approval['confirmation_prefix']} approver={approver} issue={result['issue']} "
        f"risk={result['risk']} base_commit={result['base_commit']} "
        f"receipt_sha256={receipt_sha256} run_snapshot_sha256={result['run_snapshot_sha256']} "
        f"task_sha256={result['task_sha256']} "
        f"post_run_snapshot_sha256={post_snapshot} post_task_sha256={post_task_sha256} "
        f"approval_bindings_sha256={result['approval_bindings_sha256']} "
        f"approval_receipt={approval_receipt}"
    )
    result["approvable"] = not result["failures"]
    return result


def approved_task_bytes(task_bytes: bytes) -> bytes:
    approved, count = STATUS_LINE.subn(rb"status: approved\1", task_bytes)
    if count != 1:
        raise ValueError("Task must contain exactly one awaiting_approval status line")
    return approved


def validate_candidate_run(run: Path, candidate_task: bytes, contract: dict[str, Any]) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        candidate = Path(temp_dir) / "run"
        candidate.mkdir()
        for name in contract["artifacts"]:
            content = candidate_task if name == "task.md" else (run / name).read_bytes()
            (candidate / name).write_bytes(content)
        validation = validate_artifacts.validate_directory(candidate, contract, False)
    if not validation["valid"]:
        raise ValueError("Approved candidate run does not satisfy the artifact contract")


def approve(
    args: argparse.Namespace,
    policies: dict[str, Any],
    assessment: dict[str, Any],
) -> dict[str, Any]:
    if args.confirm != assessment["required_confirmation"]:
        assessment["failures"].append(
            failure("confirmation_mismatch", "Confirmation does not match the current exact task.")
        )
        assessment["approvable"] = False
        return assessment
    refreshed = assess_approval(
        args.repo,
        args.run,
        args.receipt,
        args.receipt_sha256,
        args.approval_receipt,
        args.approver,
        policies,
    )
    if not refreshed["approvable"] or args.confirm != refreshed["required_confirmation"]:
        refreshed["failures"].append(failure("state_changed", "Task approval state changed."))
        refreshed["approvable"] = False
        return refreshed
    run = args.run.resolve()
    receipt = args.receipt.resolve()
    approval_receipt = args.approval_receipt.resolve()
    artifact_names = list(policies["artifact"]["artifacts"])
    task_path = run / "task.md"
    task_bytes = task_path.read_bytes()
    _, current_bindings_sha256 = approval_bindings(policies["approval"])
    if (
        apply_stage_output.run_snapshot_sha256(run, artifact_names)
        != refreshed["run_snapshot_sha256"]
        or apply_stage_output.sha256_bytes(task_bytes) != refreshed["task_sha256"]
        or apply_stage_output.sha256_bytes(receipt.read_bytes()) != refreshed["receipt_sha256"]
        or current_bindings_sha256 != refreshed["approval_bindings_sha256"]
    ):
        refreshed["failures"].append(
            failure(
                "state_changed",
                "Run, task, receipt, or approval controls changed immediately before approval.",
            )
        )
        refreshed["approvable"] = False
        return refreshed
    candidate = approved_task_bytes(task_bytes)
    validate_candidate_run(run, candidate, policies["artifact"])
    bindings, _bindings_sha256 = approval_bindings(policies["approval"])
    receipt_value = {
        "task_approval_receipt_version": policies["approval"]["version"],
        "purpose": policies["approval"]["purpose"],
        "mode": policies["approval"]["mode"],
        **{field: False for field in FALSE_FIELDS},
        "task_approved": True,
        "research_ready": True,
        "approver_declaration": refreshed["approver_declaration"],
        "issue": refreshed["issue"],
        "risk": refreshed["risk"],
        "base_commit": refreshed["base_commit"],
        "run": str(run),
        "initialization_receipt_sha256": refreshed["receipt_sha256"],
        "confirmation_sha256": apply_stage_output.sha256_bytes(
            args.confirm.encode("utf-8")
        ),
        "pre_approval_run_snapshot_sha256": refreshed["pre_approval_run_snapshot_sha256"],
        "post_approval_run_snapshot_sha256": refreshed["post_approval_run_snapshot_sha256"],
        "pre_task_sha256": refreshed["pre_task_sha256"],
        "post_task_sha256": refreshed["post_task_sha256"],
        "bindings": bindings,
    }
    approval_receipt_bytes = (
        json.dumps(receipt_value, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if len(approval_receipt_bytes) > policies["approval"]["max_approval_receipt_bytes"]:
        raise ValueError("Task-approval receipt exceeds max_approval_receipt_bytes")
    task_mutated = False
    receipt_written = False
    try:
        initialize_portable_run.write_exclusive(approval_receipt, approval_receipt_bytes)
        receipt_written = True
        apply_stage_output.write_atomic_existing(task_path, candidate)
        task_mutated = True
        final_validation = validate_artifacts.validate_directory(run, policies["artifact"], False)
        if not final_validation["valid"]:
            raise ValueError("Run contract unexpectedly failed after atomic task approval")
        research = check_stage_readiness.check_readiness(
            run,
            "research",
            policies["artifact"],
            policies["readiness"],
        )
        if not research["ready"]:
            raise ValueError("Research prerequisites unexpectedly remain not ready after approval")
        if (
            approval_receipt.read_bytes() != approval_receipt_bytes
            or apply_stage_output.run_snapshot_sha256(run, artifact_names)
            != refreshed["post_approval_run_snapshot_sha256"]
            or apply_stage_output.sha256_bytes(task_path.read_bytes())
            != refreshed["post_task_sha256"]
        ):
            raise ValueError(
                "Approved run or task-approval receipt changed during final validation"
            )
    except (OSError, UnicodeError, ValueError) as error:
        refreshed["rollback_attempted"] = receipt_written or task_mutated
        if task_mutated and task_path.read_bytes() == candidate:
            apply_stage_output.write_atomic_existing(task_path, task_bytes)
        if receipt_written:
            approval_receipt.unlink(missing_ok=True)
        refreshed["rollback_succeeded"] = (
            task_path.read_bytes() == task_bytes and not approval_receipt.exists()
        )
        status = "succeeded" if refreshed["rollback_succeeded"] else "failed"
        raise ValueError(f"Task approval failed; rollback {status}") from error
    refreshed.update(
        approvable=False,
        task_approved=True,
        run_mutated=True,
        research_ready=True,
        receipt_written=True,
        approval_receipt_sha256=apply_stage_output.sha256_bytes(approval_receipt_bytes),
        approval_receipt_size_bytes=len(approval_receipt_bytes),
        required_confirmation=None,
    )
    return refreshed


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--receipt-sha256", required=True)
    parser.add_argument("--approval-receipt", type=Path, required=True)
    parser.add_argument("--approver", required=True, help="Unauthenticated approver declaration")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    check_parser = subparsers.add_parser("check", help="Validate and print exact task confirmation")
    add_common_arguments(check_parser)
    approve_parser = subparsers.add_parser(
        "approve",
        help="Revalidate and approve exactly one task",
    )
    add_common_arguments(approve_parser)
    approve_parser.add_argument(
        "--confirm",
        required=True,
        help="Exact confirmation printed by check",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        policies = load_policies()
        result = assess_approval(
            args.repo,
            args.run,
            args.receipt,
            args.receipt_sha256,
            args.approval_receipt,
            args.approver,
            policies,
        )
        if args.action == "approve" and result["approvable"]:
            result = approve(args, policies, result)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"task-approval: ERROR\n- {error}", file=sys.stderr)
        return 1
    result["action"] = args.action
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if (result["approvable"] if args.action == "check" else result["task_approved"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
