#!/usr/bin/env python3
"""Check and explicitly approve one exact plan without starting implementation."""

from __future__ import annotations

import argparse
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
import validate_stage_application


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_DIR = REPO_ROOT / ".agent" / "policies"
STATUS_LINE = re.compile(rb"(?m)^status: awaiting_approval(\r?)$")


def load_approval_policy(
    path: Path,
    artifact_contract: dict[str, Any],
    readiness_policy: dict[str, Any],
) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "version",
        "confirmation_prefix",
        "max_approver_chars",
        "max_plan_approval_receipt_bytes",
        "require_external_run",
        "require_valid_plan_application",
        "require_external_approval_receipt",
        "require_approval_receipt_outside_run",
        "require_absent_approval_receipt",
        "require_clean_worktree",
        "require_repo_head_match",
        "current_status",
        "approved_status",
        "readiness_stage",
        "purpose",
        "mode",
        "bindings",
    }
    if set(policy) != required:
        raise ValueError("Plan-approval policy fields do not match the contract")
    if (
        not isinstance(policy["version"], int)
        or isinstance(policy["version"], bool)
        or policy["version"] != 3
    ):
        raise ValueError(f"Unsupported plan-approval policy version: {policy['version']}")
    if policy["purpose"] != "portable_plan_approval" or policy["mode"] != "exact-local-approval-only":
        raise ValueError("purpose and mode must match the plan-approval contract")
    if policy["confirmation_prefix"] != "APPROVE-EXACT-PLAN":
        raise ValueError("confirmation_prefix must match the pilot contract")
    if (
        not isinstance(policy["max_approver_chars"], int)
        or isinstance(policy["max_approver_chars"], bool)
        or policy["max_approver_chars"] < 1
    ):
        raise ValueError("max_approver_chars must be a positive integer")
    if (
        not isinstance(policy["max_plan_approval_receipt_bytes"], int)
        or isinstance(policy["max_plan_approval_receipt_bytes"], bool)
        or policy["max_plan_approval_receipt_bytes"] < 1
    ):
        raise ValueError("max_plan_approval_receipt_bytes must be a positive integer")
    for field in (
        "require_external_run",
        "require_valid_plan_application",
        "require_external_approval_receipt",
        "require_approval_receipt_outside_run",
        "require_absent_approval_receipt",
        "require_clean_worktree",
        "require_repo_head_match",
    ):
        if policy[field] is not True:
            raise ValueError(f"{field} must explicitly be true during the pilot")
    plan_statuses = artifact_contract["artifacts"]["plan.md"]["allowed_statuses"]
    if (
        policy["current_status"] != "awaiting_approval"
        or policy["approved_status"] != "approved"
        or policy["current_status"] not in plan_statuses
        or policy["approved_status"] not in plan_statuses
    ):
        raise ValueError("Plan approval must transition awaiting_approval to approved")
    if policy["readiness_stage"] != "plan" or policy["readiness_stage"] not in readiness_policy["stages"]:
        raise ValueError("Plan approval readiness_stage must be plan")
    if (
        not isinstance(policy["bindings"], list)
        or not policy["bindings"]
        or not all(isinstance(binding, str) for binding in policy["bindings"])
        or len(policy["bindings"]) != len(set(policy["bindings"]))
    ):
        raise ValueError("bindings must be a non-empty unique list")
    return policy


def load_policies() -> dict[str, Any]:
    artifact = validate_artifacts.load_contract(POLICY_DIR / "artifact-contract.json")
    readiness = check_stage_readiness.load_readiness_policy(
        POLICY_DIR / "stage-readiness.json",
        artifact,
    )
    application_policies = apply_stage_output.load_policies()
    return {
        "artifact": artifact,
        "readiness": readiness,
        "diff": application_policies["diff"],
        "approval": load_approval_policy(
            POLICY_DIR / "plan-approval.json",
            artifact,
            readiness,
        ),
    }


def failure(rule: str, message: str) -> dict[str, str]:
    return {"rule": rule, "message": message}


def base_result() -> dict[str, Any]:
    return {
        "approvable": False,
        "plan_approved": False,
        "run_mutated": False,
        "authorized": False,
        "implementation_ready": False,
        "implementation_authorized": False,
        "publication_authorized": False,
        "approver_declaration": None,
        "issue": None,
        "risk": None,
        "base_commit": None,
        "run_snapshot_sha256": None,
        "plan_sha256": None,
        "plan_application_receipt_sha256": None,
        "plan_approval_bindings_sha256": None,
        "approval_receipt": None,
        "approval_receipt_sha256": None,
        "approval_receipt_size_bytes": None,
        "pre_approval_run_snapshot_sha256": None,
        "post_approval_run_snapshot_sha256": None,
        "pre_plan_sha256": None,
        "post_plan_sha256": None,
        "receipt_written": False,
        "rollback_attempted": False,
        "rollback_succeeded": False,
        "required_confirmation": None,
        "failures": [],
    }


def approval_bindings(policy: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    records = initialize_portable_run.binding_records(policy["bindings"])
    content = (json.dumps(records, sort_keys=True) + "\n").encode("utf-8")
    return records, apply_stage_output.sha256_bytes(content)


def snapshot_with_plan(run: Path, artifact_names: list[str], plan_bytes: bytes) -> str:
    snapshot = b"".join(
        name.encode("utf-8")
        + b"\0"
        + apply_stage_output.sha256_bytes(
            plan_bytes if name == "plan.md" else (run / name).read_bytes()
        ).encode("ascii")
        + b"\n"
        for name in sorted(artifact_names)
    )
    return apply_stage_output.sha256_bytes(snapshot)


def valid_plan_application(
    repo: Path,
    run: Path,
    application_receipt: Path,
    application_receipt_sha256: str,
) -> dict[str, Any]:
    return validate_stage_application.validate(
        repo,
        run,
        application_receipt,
        application_receipt_sha256,
        validate_stage_application.load_policies(),
    )


def assess_approval(
    repo: Path,
    run: Path,
    application_receipt: Path,
    application_receipt_sha256: str,
    approval_receipt: Path,
    policies: dict[str, Any],
) -> dict[str, Any]:
    result = base_result()
    result["plan_application_receipt_sha256"] = application_receipt_sha256
    if run.is_symlink():
        raise ValueError("Run directory symbolic links are not allowed")
    repo_root = Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()
    run = run.resolve()
    approval_receipt = approval_receipt.resolve()
    if not run.is_dir():
        raise ValueError("Run artifact directory does not exist")
    if policies["approval"]["require_external_run"] and build_stage_context.is_within(run, repo_root):
        raise ValueError("Run artifact directory must be outside the Git checkout")
    if "\n" in str(approval_receipt) or "\r" in str(approval_receipt):
        raise ValueError("Plan-approval receipt path must not contain line breaks")
    if approval_receipt.is_symlink():
        raise ValueError("Plan-approval receipt symbolic links are not allowed")
    if policies["approval"]["require_external_approval_receipt"] and build_stage_context.is_within(
        approval_receipt,
        repo_root,
    ):
        raise ValueError("Plan-approval receipt must be outside the Git checkout")
    if policies["approval"]["require_approval_receipt_outside_run"] and build_stage_context.is_within(
        approval_receipt,
        run,
    ):
        raise ValueError("Plan-approval receipt must be outside the portable run")
    if policies["approval"]["require_absent_approval_receipt"] and approval_receipt.exists():
        raise ValueError("Plan-approval receipt already exists")
    if not approval_receipt.parent.is_dir():
        raise ValueError("Plan-approval receipt parent must be an existing directory")
    artifact_names = list(policies["artifact"]["artifacts"])
    if any((run / name).is_symlink() for name in artifact_names):
        raise ValueError("Run artifact symbolic links are not allowed")
    try:
        plan_application = valid_plan_application(
            repo_root,
            run,
            application_receipt,
            application_receipt_sha256,
        )
    except ValueError as error:
        plan_application = {
            "valid": False,
            "stage": None,
            "artifact": None,
            "status": None,
            "failures": [failure("plan_application", str(error))],
        }
    if policies["approval"]["require_valid_plan_application"] and not (
        plan_application["valid"]
        and plan_application["stage"] == "plan"
        and plan_application["artifact"] == "plan.md"
        and plan_application["status"] == policies["approval"]["current_status"]
    ):
        result["failures"].append(
            failure("plan_application", "Plan approval requires a valid applied-plan receipt.")
        )
        result["failures"].extend(plan_application["failures"])
    contract = validate_artifacts.validate_directory(run, policies["artifact"], False)
    if not contract["valid"]:
        result["failures"].append(failure("run_contract", "Run does not satisfy the artifact contract."))
        return result

    artifacts = {name: validate_artifacts.parse_artifact(run / name) for name in artifact_names}
    task = artifacts["task.md"]
    plan = artifacts["plan.md"]
    plan_bytes = (run / "plan.md").read_bytes()
    _bindings, bindings_sha256 = approval_bindings(policies["approval"])
    run_snapshot = apply_stage_output.run_snapshot_sha256(run, artifact_names)
    plan_sha256 = apply_stage_output.sha256_bytes(plan_bytes)
    result.update(
        issue=int(task.frontmatter["issue"]),
        risk=task.frontmatter["risk"],
        base_commit=task.frontmatter["base_commit"],
        run_snapshot_sha256=run_snapshot,
        plan_sha256=plan_sha256,
        plan_approval_bindings_sha256=bindings_sha256,
        approval_receipt=str(approval_receipt),
        pre_approval_run_snapshot_sha256=run_snapshot,
        pre_plan_sha256=plan_sha256,
    )
    if plan.frontmatter["status"] != policies["approval"]["current_status"]:
        result["failures"].append(
            failure("current_status", "Plan status is not awaiting_approval.")
        )
        return result
    candidate_plan = approved_plan_bytes(plan_bytes)
    post_snapshot = snapshot_with_plan(run, artifact_names, candidate_plan)
    post_plan_sha256 = apply_stage_output.sha256_bytes(candidate_plan)
    result.update(
        post_approval_run_snapshot_sha256=post_snapshot,
        post_plan_sha256=post_plan_sha256,
    )
    readiness = check_stage_readiness.check_readiness(
        run,
        policies["approval"]["readiness_stage"],
        policies["artifact"],
        policies["readiness"],
    )
    if not readiness["ready"]:
        result["failures"].append(
            failure("plan_prerequisites", "Plan approval prerequisites are not ready.")
        )
        result["failures"].extend(readiness["failures"])

    head = diff_policy.run_git(repo_root, "rev-parse", "HEAD").decode("ascii").strip()
    if policies["approval"]["require_repo_head_match"] and head != result["base_commit"]:
        result["failures"].append(failure("repo_head_match", "Repository HEAD differs from plan base."))
    status = diff_policy.run_git_with_environment(
        repo_root,
        {"GIT_OPTIONAL_LOCKS": "0"},
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if policies["approval"]["require_clean_worktree"] and status:
        result["failures"].append(failure("clean_worktree", "Repository worktree must be clean."))

    result["required_confirmation"] = (
        f"{policies['approval']['confirmation_prefix']} "
        f"issue={result['issue']} risk={result['risk']} base_commit={result['base_commit']} "
        f"run_snapshot_sha256={result['run_snapshot_sha256']} plan_sha256={result['plan_sha256']} "
        f"post_run_snapshot_sha256={post_snapshot} post_plan_sha256={post_plan_sha256} "
        f"plan_application_receipt_sha256={application_receipt_sha256} "
        f"plan_approval_bindings_sha256={bindings_sha256} "
        f"approval_receipt={approval_receipt}"
    )
    result["approvable"] = not result["failures"]
    return result


def approved_plan_bytes(plan_bytes: bytes) -> bytes:
    approved, count = STATUS_LINE.subn(rb"status: approved\1", plan_bytes)
    if count != 1:
        raise ValueError("Plan must contain exactly one awaiting_approval status line")
    return approved


def validate_candidate_run(run: Path, candidate_plan: bytes, contract: dict[str, Any]) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        candidate = Path(temp_dir) / "run"
        candidate.mkdir()
        for name in contract["artifacts"]:
            content = candidate_plan if name == "plan.md" else (run / name).read_bytes()
            (candidate / name).write_bytes(content)
        validation = validate_artifacts.validate_directory(candidate, contract, False)
    if not validation["valid"]:
        raise ValueError("Approved candidate run does not satisfy the artifact contract")


def approve(args: argparse.Namespace, policies: dict[str, Any], assessment: dict[str, Any]) -> dict[str, Any]:
    approver = apply_stage_output.validate_reviewer(
        args.approver,
        policies["approval"]["max_approver_chars"],
    )
    if build_stage_context.detect_secrets(
        [build_stage_context.content_record("approver", approver)],
        policies["diff"],
    ):
        raise ValueError("Approver declaration contains a high-confidence secret signature")
    if args.confirm != assessment["required_confirmation"]:
        assessment["failures"].append(
            failure("confirmation_mismatch", "Confirmation does not match the current exact plan.")
        )
        assessment["approvable"] = False
        return assessment
    refreshed = assess_approval(
        args.repo,
        args.run,
        args.application_receipt,
        args.application_receipt_sha256,
        args.approval_receipt,
        policies,
    )
    if not refreshed["approvable"] or args.confirm != refreshed["required_confirmation"]:
        refreshed["failures"].append(failure("state_changed", "Plan approval state changed."))
        refreshed["approvable"] = False
        return refreshed

    run = args.run.resolve()
    artifact_names = list(policies["artifact"]["artifacts"])
    plan_path = run / "plan.md"
    plan_bytes = plan_path.read_bytes()
    approval_receipt = args.approval_receipt.resolve()
    _bindings, current_bindings_sha256 = approval_bindings(policies["approval"])
    if (
        apply_stage_output.run_snapshot_sha256(run, artifact_names)
        != refreshed["run_snapshot_sha256"]
        or apply_stage_output.sha256_bytes(plan_bytes) != refreshed["plan_sha256"]
        or current_bindings_sha256 != refreshed["plan_approval_bindings_sha256"]
    ):
        refreshed["failures"].append(
            failure("state_changed", "Run, plan, or approval controls changed immediately before approval.")
        )
        refreshed["approvable"] = False
        return refreshed
    candidate = approved_plan_bytes(plan_bytes)
    validate_candidate_run(run, candidate, policies["artifact"])
    bindings, _bindings_sha256 = approval_bindings(policies["approval"])
    receipt_value = {
        "plan_approval_receipt_version": policies["approval"]["version"],
        "purpose": policies["approval"]["purpose"],
        "mode": policies["approval"]["mode"],
        "authorized": False,
        "implementation_authorized": False,
        "publication_authorized": False,
        "run_mutated": True,
        "plan_approved": True,
        "implementation_ready": True,
        "approver_declaration": approver,
        "issue": refreshed["issue"],
        "risk": refreshed["risk"],
        "base_commit": refreshed["base_commit"],
        "run": str(run),
        "plan_application_receipt_sha256": refreshed["plan_application_receipt_sha256"],
        "confirmation_sha256": apply_stage_output.sha256_bytes(args.confirm.encode("utf-8")),
        "pre_approval_run_snapshot_sha256": refreshed["pre_approval_run_snapshot_sha256"],
        "post_approval_run_snapshot_sha256": refreshed["post_approval_run_snapshot_sha256"],
        "pre_plan_sha256": refreshed["pre_plan_sha256"],
        "post_plan_sha256": refreshed["post_plan_sha256"],
        "bindings": bindings,
    }
    approval_receipt_bytes = (
        json.dumps(receipt_value, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if len(approval_receipt_bytes) > policies["approval"]["max_plan_approval_receipt_bytes"]:
        raise ValueError("Plan-approval receipt exceeds max_plan_approval_receipt_bytes")
    plan_mutated = False
    receipt_written = False
    try:
        initialize_portable_run.write_exclusive(approval_receipt, approval_receipt_bytes)
        receipt_written = True
        apply_stage_output.write_atomic_existing(plan_path, candidate)
        plan_mutated = True
        final_validation = validate_artifacts.validate_directory(run, policies["artifact"], False)
        if not final_validation["valid"]:
            raise ValueError("Run contract unexpectedly failed after atomic plan approval")
        implementation = check_stage_readiness.check_readiness(
            run,
            "implement",
            policies["artifact"],
            policies["readiness"],
        )
        if not implementation["ready"]:
            raise ValueError("Implementation prerequisites unexpectedly remain not ready after approval")
        if (
            approval_receipt.read_bytes() != approval_receipt_bytes
            or apply_stage_output.run_snapshot_sha256(run, artifact_names)
            != refreshed["post_approval_run_snapshot_sha256"]
            or apply_stage_output.sha256_bytes(plan_path.read_bytes())
            != refreshed["post_plan_sha256"]
        ):
            raise ValueError("Approved run or plan-approval receipt changed during final validation")
    except (OSError, UnicodeError, ValueError) as error:
        refreshed["rollback_attempted"] = receipt_written or plan_mutated
        if plan_mutated and plan_path.read_bytes() == candidate:
            apply_stage_output.write_atomic_existing(plan_path, plan_bytes)
        if receipt_written:
            approval_receipt.unlink(missing_ok=True)
        refreshed["rollback_succeeded"] = (
            plan_path.read_bytes() == plan_bytes and not approval_receipt.exists()
        )
        status = "succeeded" if refreshed["rollback_succeeded"] else "failed"
        raise ValueError(f"Plan approval failed; rollback {status}") from error
    refreshed.update(
        approvable=False,
        plan_approved=True,
        run_mutated=True,
        implementation_ready=True,
        approver_declaration=approver,
        receipt_written=True,
        approval_receipt_sha256=apply_stage_output.sha256_bytes(approval_receipt_bytes),
        approval_receipt_size_bytes=len(approval_receipt_bytes),
        required_confirmation=None,
    )
    return refreshed


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--application-receipt", type=Path, required=True)
    parser.add_argument("--application-receipt-sha256", required=True)
    parser.add_argument("--approval-receipt", type=Path, required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    check_parser = subparsers.add_parser("check", help="Validate and print exact plan confirmation")
    add_common_arguments(check_parser)
    approve_parser = subparsers.add_parser("approve", help="Revalidate and approve exactly one plan")
    add_common_arguments(approve_parser)
    approve_parser.add_argument("--approver", required=True, help="Unauthenticated approver declaration")
    approve_parser.add_argument("--confirm", required=True, help="Exact confirmation printed by check")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        policies = load_policies()
        result = assess_approval(
            args.repo,
            args.run,
            args.application_receipt,
            args.application_receipt_sha256,
            args.approval_receipt,
            policies,
        )
        if args.action == "approve" and result["approvable"]:
            result = approve(args, policies, result)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"plan-approval: ERROR\n- {error}", file=sys.stderr)
        return 1
    result["action"] = args.action
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if (result["approvable"] if args.action == "check" else result["plan_approved"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
